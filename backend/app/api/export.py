from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/api/export", tags=["export"])


def _conversation_to_markdown(conv) -> str:
    lines = [f"# {conv.title}", "", f"_Exported {datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
    for m in conv.messages:
        speaker = "You" if m.role == "user" else "Assistant"
        lines.append(f"## {speaker}")
        lines.append("")
        lines.append(m.content)
        lines.append("")
        if m.citations:
            lines.append("**Sources:**")
            for c in m.citations:
                page = f", p.{c['page_start']}" if c.get("page_start") else ""
                lines.append(f"- [{c['number']}] {c['filename']}{page} — _{c['section'] or ''}_")
            lines.append("")
    return "\n".join(lines)


@router.get("/conversation/{conversation_id}")
def export_conversation(conversation_id: str, format: str = Query("markdown", pattern="^(markdown|pdf)$"), db: Session = Depends(get_db)):
    from app.models import Conversation

    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    markdown = _conversation_to_markdown(conv)

    if format == "markdown":
        return Response(
            content=markdown,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{_safe_name(conv.title)}.md"'},
        )

    pdf_bytes = _markdown_to_pdf(conv.title, conv.messages)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_safe_name(conv.title)}.pdf"'},
    )


def _safe_name(title: str) -> str:
    return "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "conversation"


def _markdown_to_pdf(title: str, messages) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER)
    styles = getSampleStyleSheet()
    flow = [Paragraph(escape(title), styles["Title"]), Spacer(1, 12)]

    for m in messages:
        speaker = "You" if m.role == "user" else "Assistant"
        flow.append(Paragraph(f"<b>{speaker}</b>", styles["Heading3"]))
        body = escape(m.content).replace("\n", "<br/>")
        flow.append(Paragraph(body, styles["BodyText"]))
        if m.citations:
            src_lines = []
            for c in m.citations:
                page = f", p.{c['page_start']}" if c.get("page_start") else ""
                src_lines.append(f"[{c['number']}] {escape(c['filename'])}{page}")
            flow.append(Paragraph("<i>Sources: " + "; ".join(src_lines) + "</i>", styles["Italic"]))
        flow.append(Spacer(1, 10))

    doc.build(flow)
    return buf.getvalue()
