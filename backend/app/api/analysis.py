from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm import get_llm_client
from app.llm.base import LLMError
from app.schemas import CompareRequest, SummarizeRequest
from app.services.document_tasks import compare_documents, summarize_documents

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/summarize")
def summarize(req: SummarizeRequest, db: Session = Depends(get_db)):
    try:
        llm = get_llm_client()
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return summarize_documents(db, llm, req.document_ids)


@router.post("/compare")
def compare(req: CompareRequest, db: Session = Depends(get_db)):
    try:
        llm = get_llm_client()
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return compare_documents(db, llm, req.document_ids_a, req.document_ids_b, req.aspect)
