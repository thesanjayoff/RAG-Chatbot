from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ConversationCreate, ConversationUpdate

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _message_to_dict(m) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "citations": m.citations,
        "not_found": m.not_found,
        "used_general_knowledge": m.used_general_knowledge,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _conversation_to_dict(c, with_messages: bool = False) -> dict:
    out = {
        "id": c.id,
        "title": c.title,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if with_messages:
        out["messages"] = [_message_to_dict(m) for m in c.messages]
    return out


@router.get("")
def list_conversations(db: Session = Depends(get_db)):
    from app.models import Conversation

    rows = db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
    return [_conversation_to_dict(c) for c in rows]


@router.get("/search")
def search_conversations(q: str, db: Session = Depends(get_db)):
    from app.models import Conversation, Message

    like = f"%{q}%"
    conv_ids = {
        row[0]
        for row in db.query(Message.conversation_id).filter(Message.content.ilike(like)).all()
    }
    rows = (
        db.query(Conversation)
        .filter(or_(Conversation.title.ilike(like), Conversation.id.in_(conv_ids)))
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [_conversation_to_dict(c) for c in rows]


@router.post("")
def create_conversation(body: ConversationCreate, db: Session = Depends(get_db)):
    from app.models import Conversation

    conv = Conversation(title=body.title)
    db.add(conv)
    db.commit()
    return _conversation_to_dict(conv)


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    from app.models import Conversation

    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _conversation_to_dict(conv, with_messages=True)


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: str, body: ConversationUpdate, db: Session = Depends(get_db)):
    from app.models import Conversation

    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    conv.title = body.title
    db.commit()
    return _conversation_to_dict(conv)


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    from app.models import Conversation

    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    db.delete(conv)
    db.commit()
    return {"status": "deleted"}
