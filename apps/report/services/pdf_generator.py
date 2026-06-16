"""E7.12 — ReportLab 기반 면접 리포트 PDF 생성 서비스.

FinalReport.summary JSONB를 A4 PDF로 변환한다.
한글 폰트: NanumGothic (시스템에 없으면 Helvetica fallback).
"""

import io
import logging
import os
from datetime import datetime

logger = logging.getLogger("feedback_ai.pdf_generator")

# 한글 폰트 경로 (환경마다 다를 수 있음 — settings.NANUM_FONT_PATH 로 오버라이드 가능)
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    os.path.join(os.path.dirname(__file__), "fonts", "NanumGothic.ttf"),
]


def _get_font_path() -> str | None:
    """시스템에서 한글 폰트 경로를 탐색한다."""
    from django.conf import settings
    custom = getattr(settings, "NANUM_FONT_PATH", None)
    if custom and os.path.exists(custom):
        return custom
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _register_korean_font() -> tuple[str, bool]:
    """한글 폰트를 ReportLab에 등록한다.

    Returns:
        (font_name, used_fallback). 폰트를 못 찾아 Helvetica로 폴백하면
        used_fallback=True. 호출부는 이 플래그로 한글 깨짐을 사용자에게 고지한다.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path = _get_font_path()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("NanumGothic", font_path))
            logger.info("한글 폰트 등록 완료: %s", font_path)
            return "NanumGothic", False
        except Exception as e:
            logger.error("한글 폰트 등록 실패 (%s): %s", font_path, str(e))
    logger.error(
        "한글 폰트 미발견 — Helvetica 폴백 (한글 깨짐). settings.NANUM_FONT_PATH 지정 또는 "
        "폰트 동봉 필요. 후보 경로=%s", _FONT_CANDIDATES,
    )
    return "Helvetica", True


def _safe(value, default="—") -> str:
    """None/빈 값을 대시로 변환."""
    if value is None or value == "":
        return default
    return str(value)


def generate_report_pdf(report) -> bytes:
    """FinalReport 인스턴스를 PDF bytes로 변환한다.

    Args:
        report: apps.report.models.FinalReport 인스턴스.

    Returns:
        PDF 바이트 (application/pdf 응답에 직접 사용 가능).
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )

    font_name, font_fallback = _register_korean_font()

    # ── 스타일 정의 ────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    brand_green = colors.HexColor("#08CB00")
    brand_dark = colors.HexColor("#253900")
    accent_red = colors.HexColor("#E5342B")

    def make_style(name, parent="Normal", **kwargs):
        return ParagraphStyle(name, parent=styles[parent], fontName=font_name, **kwargs)

    title_style = make_style("ReportTitle", fontSize=22, textColor=brand_dark,
                              spaceAfter=6, leading=28, alignment=1)
    subtitle_style = make_style("ReportSubtitle", fontSize=11, textColor=colors.grey,
                                 spaceAfter=4, alignment=1)
    section_style = make_style("SectionHeader", fontSize=14, textColor=brand_dark,
                                spaceBefore=14, spaceAfter=6, leading=18,
                                borderPad=4)
    body_style = make_style("Body", fontSize=10, spaceAfter=4, leading=15)
    tag_style = make_style("Tag", fontSize=9, textColor=colors.white,
                            backColor=brand_green, spaceAfter=2, leading=12)
    score_label_style = make_style("ScoreLabel", fontSize=10, textColor=colors.grey)
    score_value_style = make_style("ScoreValue", fontSize=20, textColor=brand_dark,
                                    leading=24, spaceAfter=2)
    table_header_style = make_style("TableHeader", fontSize=9, textColor=colors.white)
    table_cell_style = make_style("TableCell", fontSize=9, leading=13)

    # ── 데이터 추출 ────────────────────────────────────────────────────
    summary = report.summary or {}
    metadata = summary.get("evaluation_metadata", {})
    score_summary = summary.get("score_summary", {})
    score_detail = summary.get("score_detail", {})
    dyn_tags = summary.get("dynamically_triggered_tags", {})
    persona_feedback = score_summary.get("persona_feedback", {})
    metrics = score_summary.get("metrics", {})

    overall_score = report.overall_score or 0
    persona_label = persona_feedback.get("persona_label", "—")
    interview_type = _safe(metadata.get("interview_type"))
    interview_mode = _safe(metadata.get("interview_mode"))
    generated_at = report.generated_at.strftime("%Y년 %m월 %d일") if report.generated_at else "—"
    summary_text = _safe(metadata.get("summary_text"))

    # ── PDF 빌드 ───────────────────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )
    story = []

    # 커버 헤더
    story.append(Paragraph("CAREER.ZIP", title_style))
    story.append(Paragraph("면접 종합 평가 리포트", subtitle_style))
    story.append(Paragraph(f"생성일: {generated_at}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=brand_green, spaceAfter=10))

    # 종합 점수 박스
    score_table_data = [[
        Paragraph("종합 점수", score_label_style),
        Paragraph("면접 유형", score_label_style),
        Paragraph("모드", score_label_style),
        Paragraph("페르소나", score_label_style),
    ], [
        Paragraph(f"{overall_score}점", score_value_style),
        Paragraph(interview_type, body_style),
        Paragraph(interview_mode, body_style),
        Paragraph(persona_label, body_style),
    ]]
    score_table = Table(score_table_data, colWidths=["25%", "25%", "25%", "25%"])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand_dark),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.HexColor("#F0FFF0")]),
        ("BOX", (0, 0), (-1, -1), 1, brand_green),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 12))

    # AI 종합 코멘트
    if summary_text and summary_text != "—":
        story.append(Paragraph("■ AI 종합 코멘트", section_style))
        story.append(Paragraph(summary_text, body_style))

    # 페르소나 피드백
    if persona_feedback:
        story.append(Paragraph("■ 페르소나별 피드백", section_style))
        intro = persona_feedback.get("intro", "")
        closing = persona_feedback.get("closing", "")
        if intro:
            story.append(Paragraph(f"• {intro}", body_style))
        if closing:
            story.append(Paragraph(f"• {closing}", body_style))

    # 5축 점수
    story.append(Paragraph("■ 평가 축별 점수", section_style))
    metric_labels = {
        "bei_logic_score": "BEI 논리 점수",
        "cbi_competency_score": "CBI 역량 점수",
        "grounding_score": "실무 근거 점수",
        "speech_delivery_score": "발화 전달력",
        "technical_score": "기술 깊이 (SBERT)",
    }
    metric_rows = [
        [Paragraph("평가 축", table_header_style), Paragraph("점수", table_header_style)]
    ]
    for key, label in metric_labels.items():
        val = metrics.get(key, 0)
        metric_rows.append([
            Paragraph(label, table_cell_style),
            Paragraph(f"{val:.1f}점", table_cell_style),
        ])
    metric_table = Table(metric_rows, colWidths=["70%", "30%"])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand_dark),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FFF9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 10))

    # 강점 태그
    strength_tags = dyn_tags.get("strength_tags", [])
    if strength_tags:
        story.append(Paragraph("■ 강점 태그 Top 5", section_style))
        for tag in strength_tags[:5]:
            name = _safe(tag.get("tag_name"))
            desc = _safe(tag.get("description"), "")
            story.append(Paragraph(f"[강점] {name}  {desc}", body_style))

    # 약점 태그
    weakness_tags = dyn_tags.get("weakness_tags", [])
    if weakness_tags:
        story.append(Paragraph("■ 개선 필요 태그 Top 5", section_style))
        for tag in weakness_tags[:5]:
            name = _safe(tag.get("tag_name"))
            desc = _safe(tag.get("description"), "")
            story.append(Paragraph(f"[개선] {name}  {desc}", body_style))

    # 개선 권고
    improvements = score_detail.get("improvement", [])
    if improvements:
        story.append(Paragraph("■ 개선 권고사항", section_style))
        for rec in improvements:
            story.append(Paragraph(f"• {_safe(rec)}", body_style))

    # 질문별 평가 테이블
    questions = score_detail.get("questions", [])
    if questions:
        story.append(Paragraph("■ 질문별 AI 평가", section_style))
        q_headers = [
            Paragraph("No.", table_header_style),
            Paragraph("유형", table_header_style),
            Paragraph("질문", table_header_style),
            Paragraph("점수", table_header_style),
            Paragraph("주요 개선포인트", table_header_style),
        ]
        q_rows = [q_headers]
        for i, q in enumerate(questions, start=1):
            q_rows.append([
                Paragraph(str(i), table_cell_style),
                Paragraph(_safe(q.get("question_type")), table_cell_style),
                Paragraph(_safe(q.get("question_text", ""))[:60] + ("…" if len(q.get("question_text", "")) > 60 else ""), table_cell_style),
                Paragraph(f"{q.get('score', 0)}점", table_cell_style),
                Paragraph(_safe(q.get("improvement_action", ""))[:60], table_cell_style),
            ])
        q_table = Table(q_rows, colWidths=["6%", "10%", "34%", "8%", "42%"])
        q_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), brand_dark),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (1, -1), "CENTER"),
            ("ALIGN", (3, 0), (3, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FFF9")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(q_table)

    # 발화 진단
    speech_diag = score_detail.get("speech_diagnostics", {})
    if speech_diag:
        story.append(Paragraph("■ 발화 진단", section_style))
        total_filler = speech_diag.get("total_filler_count", 0)
        avg_filler = speech_diag.get("avg_fillers_per_answer", 0)
        dist = speech_diag.get("filler_word_distribution", {})
        story.append(Paragraph(f"• 총 필러워드 감지 횟수: {total_filler}회 (답변당 평균 {avg_filler}회)", body_style))
        if dist:
            top_fillers = ", ".join(f"'{w}'({c}회)" for w, c in sorted(dist.items(), key=lambda x: -x[1])[:5])
            story.append(Paragraph(f"• 주요 필러워드: {top_fillers}", body_style))

    # 푸터
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Paragraph(
        f"본 리포트는 CAREER.ZIP AI 평가 시스템에 의해 자동 생성되었습니다. | {generated_at}",
        make_style("Footer", fontSize=8, textColor=colors.grey, alignment=1),
    ))
    if font_fallback:
        story.append(Paragraph(
            "※ 서버에 한글 폰트가 없어 일부 한글이 정상 표기되지 않을 수 있습니다.",
            make_style("FontWarn", fontSize=8, textColor=accent_red, alignment=1),
        ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
