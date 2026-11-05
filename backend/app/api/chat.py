from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db import SessionLocal
from app.llm import get_llm_client
from app.llm.base import LLMError
from app.retrieval.hybrid import RetrievalFilter
from app.schemas import ChatRequest
from app.services.answer_engine import stream_answer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _filter_from_spec(spec) -> RetrievalFilter:
    if spec is None:
        return RetrievalFilter()
    return RetrievalFilter(
        document_ids=spec.document_ids, tag_names=spec.tag_names, date_from=spec.date_from, date_to=spec.date_to
    )


@router.post("/stream")
def chat_stream(req: ChatRequest):
    from app.models import Conversation, Message

    db = SessionLocal()
    try:
        if req.conversation_id:
            conversation = db.get(Conversation, req.conversation_id)
            if conversation is None:
                raise HTTPException(status_code=404, detail="conversation not found")
        else:
            title = req.message.strip().splitlines()[0][:60] if req.message.strip() else "New conversation"
            conversation = Conversation(title=title)
            db.add(conversation)
            db.commit()

        history = [
            {"role": m.role, "content": m.content}
            for m in db.query(Message).filter_by(conversation_id=conversation.id).order_by(Message.created_at).all()
        ]

        user_message = Message(conversation_id=conversation.id, role="user", content=req.message)
        db.add(user_message)
        db.commit()

        try:
            llm = get_llm_client()
        except LLMError as exc:
            db.close()

            def error_gen():
                yield _sse("error", {"message": str(exc)})

            return StreamingResponse(error_gen(), media_type="text/event-stream")

        conversation_id = conversation.id
        show_chunks = req.show_chunks
        flt = _filter_from_spec(req.filters)
    except HTTPException:
        db.close()
        raise
    except Exception:
        db.close()
        raise

    def event_generator():
        inner_db = db
        try:
            yield _sse("start", {"conversation_id": conversation_id})
            final_payload = None
            for event in stream_answer(
                inner_db, llm, history, req.message, flt, req.use_subquestions, req.allow_general_knowledge
            ):
                etype = event["type"]
                if etype == "meta":
                    payload = dict(event)
                    if not show_chunks:
                        payload["retrieved"] = [
                            {k: v for k, v in r.items() if k not in ("text",)} for r in payload["retrieved"]
                        ]
                    yield _sse("meta", payload)
                elif etype == "delta":
                    yield _sse("delta", {"text": event["text"]})
                elif etype == "done":
                    final_payload = event
                    yield _sse("done", {
                        "citations": event["citations"],
                        "not_found": event["not_found"],
                        "used_general_knowledge": event["used_general_knowledge"],
                    })

            if final_payload is not None:
                assistant_message = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=final_payload["full_text"],
                    citations=final_payload["citations"],
                    not_found=final_payload["not_found"],
                    used_general_knowledge=final_payload["used_general_knowledge"],
                )
                inner_db.add(assistant_message)
                inner_db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat stream failed")
            yield _sse("error", {"message": str(exc)})
        finally:
            inner_db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
