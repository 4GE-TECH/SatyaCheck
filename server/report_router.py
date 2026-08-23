"""SatyaCheck — Report Router

Generates incident report packets (JSON + PDF) formatted for 1930 / Chakshu portal submission.

C owns this file.
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

import config
from contracts import IncidentReportPacket, ReasonCode, ScreeningResponse
from server.database import ScreeningResult, get_db

log = logging.getLogger("satyacheck.report")
router = APIRouter(prefix="/api/report", tags=["report"])


def _build_report_packet(response: ScreeningResponse, report_id: str) -> IncidentReportPacket:
    """Assemble the incident report packet from a ScreeningResponse."""
    playbooks = [rc_to_pb for rc_to_pb in response.script.playbooks]
    return IncidentReportPacket(
        report_id=report_id,
        audio_sha256=response.audio_sha256,
        trust_score=response.fusion.trust_score,
        band=response.fusion.band,
        caller_metadata=response.script.details.get("caller_metadata") or {},  # type: ignore[arg-type]
        transcript_full=response.transcript.text,
        evidence_reason_codes=response.fusion.reason_codes,
        matched_playbooks=playbooks,
        recommended_complaint_category="Financial Fraud / Impersonation",
        pdf_report_path=None,
    )


def _generate_pdf(packet: IncidentReportPacket, output_path: Path) -> bool:
    """Generate a PDF incident report using reportlab. Returns True on success."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            HRFlowable,
        )

        doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        elements = []

        # ── Header ────────────────────────────────────────────────────
        elements.append(Paragraph("<b>SatyaCheck — Incident Evidence Report</b>", styles["Title"]))
        elements.append(Paragraph("For submission to: 1930 / Chakshu National Cybercrime Portal (I4C, MHA)", styles["Normal"]))
        elements.append(Spacer(1, 0.4*cm))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        elements.append(Spacer(1, 0.3*cm))

        # ── Summary table ─────────────────────────────────────────────
        band_color = {
            "high_risk": colors.red,
            "suspicious": colors.orange,
            "caution": colors.goldenrod,
            "verified": colors.green,
            "unverified": colors.grey,
            "insufficient": colors.lightgrey,
        }.get(packet.band.value, colors.grey)

        summary_data = [
            ["Report ID", packet.report_id],
            ["Created At", packet.created_at],
            ["Audio SHA-256", packet.audio_sha256[:32] + "…"],
            ["Trust Score", f"{packet.trust_score:.1f} / 100"],
            ["Classification", packet.band.value.replace("_", " ").upper()],
            ["Complaint Category", packet.recommended_complaint_category],
        ]
        table = Table(summary_data, colWidths=[5*cm, 12*cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (1, 4), (1, 4), band_color),
            ("TEXTCOLOR", (1, 4), (1, 4), colors.white if band_color in (colors.red, colors.orange) else colors.black),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))

        # ── Transcript ────────────────────────────────────────────────
        elements.append(Paragraph("<b>Verbatim Transcript</b>", styles["Heading2"]))
        transcript_text = packet.transcript_full or "<em>(No transcript available)</em>"
        elements.append(Paragraph(transcript_text[:2000], styles["Normal"]))
        elements.append(Spacer(1, 0.4*cm))

        # ── Evidence reason codes ─────────────────────────────────────
        elements.append(Paragraph("<b>Evidence Points</b>", styles["Heading2"]))
        for rc in packet.evidence_reason_codes:
            elements.append(Paragraph(
                f"<b>[{rc.code}]</b> {rc.explanation}",
                styles["Normal"],
            ))
            if rc.citation_url:
                elements.append(Paragraph(
                    f"  → Source: {rc.citation_title or rc.citation_url} — {rc.citation_url}",
                    styles["Normal"],
                ))
            elements.append(Spacer(1, 0.15*cm))

        # ── Matched playbooks ─────────────────────────────────────────
        if packet.matched_playbooks:
            elements.append(Spacer(1, 0.3*cm))
            elements.append(Paragraph("<b>Official Fraud Advisories Matched</b>", styles["Heading2"]))
            for pb in packet.matched_playbooks:
                elements.append(Paragraph(
                    f"• <b>{pb.title}</b> ({pb.source_agency}) — {pb.source_url}",
                    styles["Normal"],
                ))
            elements.append(Spacer(1, 0.3*cm))

        # ── Footer ────────────────────────────────────────────────────
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        elements.append(Spacer(1, 0.2*cm))
        elements.append(Paragraph(
            "Generated by SatyaCheck (satyacheck.ai) — Assistant report, not a legal determination. "
            "All audio processing is performed locally; no audio leaves the device.",
            ParagraphStyle("footer", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
        ))

        doc.build(elements)
        return True

    except Exception as e:
        log.error(f"PDF generation failed: {e}")
        return False


@router.get(
    "/{session_id}",
    response_model=IncidentReportPacket,
    summary="Get incident report packet (JSON)",
)
async def get_report_json(
    session_id: str,
    db: Session = Depends(get_db),
) -> IncidentReportPacket:
    result = (
        db.query(ScreeningResult)
        .filter(ScreeningResult.session_id == session_id, ScreeningResult.is_final == True)
        .order_by(ScreeningResult.id.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    response = ScreeningResponse.model_validate_json(result.response_json)
    report_id = f"RPT_{session_id[:12].upper()}"
    packet = _build_report_packet(response, report_id)
    return packet


@router.get(
    "/{session_id}/pdf",
    summary="Download PDF incident report",
    response_class=FileResponse,
)
async def get_report_pdf(
    session_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    if not config.ENABLE_PDF_REPORTS:
        raise HTTPException(status_code=501, detail="PDF reports are disabled.")

    result = (
        db.query(ScreeningResult)
        .filter(ScreeningResult.session_id == session_id, ScreeningResult.is_final == True)
        .order_by(ScreeningResult.id.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    response = ScreeningResponse.model_validate_json(result.response_json)
    report_id = f"RPT_{session_id[:12].upper()}"
    packet = _build_report_packet(response, report_id)

    pdf_path = config.REPORTS_DIR / f"{report_id}.pdf"
    success = _generate_pdf(packet, pdf_path)
    if not success:
        raise HTTPException(status_code=500, detail="PDF generation failed.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"satyacheck_{report_id}.pdf",
    )
