"""
Official PDF document generation using reportlab (pure Python, no system
dependencies needed — reliable across any deployment target).

Uses a bundled Noto Sans Ethiopic font (app/fonts/) so Amharic renders as
real glyphs — this font also covers Latin script, so it's used uniformly
for all text (English + Amharic) to avoid font-switching bugs.

Performance Plan -> 4 or 5 pages (5th only when the rich evaluation form
extra_fields were submitted):
  1. Cover: employee identity + plan period/title
  2. Goals / checklist
  2b. Extended evaluation (institutional details + 6-month/yearly score tables)
  3. Review & remarks (decision reason, Technical Committee comment)
  4. Approval: Prepared by / Approved by signatures + QR verification

Leave Request -> 2 or 3 pages (3rd only when extra_fields were submitted):
  1. Employee identity + leave details + reason
  1b. Contact info & HR audit / delegation
  2. Decision + Prepared by / Approved by signatures + QR verification
"""
import hashlib
import io
import os

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import settings

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "generated_documents")
os.makedirs(DOCS_DIR, exist_ok=True)

FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")
FONT_NAME = "NotoEthiopic"
FONT_BOLD_NAME = "NotoEthiopic-Bold"
_font_path = os.path.join(FONT_DIR, "NotoSansEthiopic-Regular.ttf")
_font_bold_path = os.path.join(FONT_DIR, "NotoSansEthiopic-Bold.ttf")
if os.path.exists(_font_path) and FONT_NAME not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FONT_NAME, _font_path))
FONT = FONT_NAME if os.path.exists(_font_path) else FONT
if os.path.exists(_font_bold_path) and FONT_BOLD_NAME not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, _font_bold_path))
FONT_BOLD = FONT_BOLD_NAME if os.path.exists(_font_bold_path) else FONT
pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)

PAGE_W, PAGE_H = A4
INDIGO = colors.HexColor("#4338CA")
VIOLET = colors.HexColor("#7C3AED")
FUCHSIA = colors.HexColor("#C026D3")
BLUE = colors.HexColor("#2563EB")
EMERALD = colors.HexColor("#059669")
AMBER = colors.HexColor("#D97706")
DANGER = colors.HexColor("#DC2626")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E0DEF7")
TINT = colors.HexColor("#F5F3FF")
INK = colors.HexColor("#1E1B2E")

MARGIN = 18 * mm

STATUS_TONE = {
    "approved": EMERALD, "director_approved": EMERALD, "hr_approved": EMERALD, "super_admin_approved": EMERALD,
    "rejected": DANGER, "director_rejected": DANGER, "hr_rejected": DANGER, "super_admin_rejected": DANGER,
    "submitted": BLUE, "escalated": AMBER, "pending_hr": AMBER, "pending_director": AMBER, "pending_super_admin": AMBER,
}


def _lerp_color(c1: colors.Color, c2: colors.Color, t: float) -> colors.Color:
    return colors.Color(c1.red + (c2.red - c1.red) * t, c1.green + (c2.green - c1.green) * t, c1.blue + (c2.blue - c1.blue) * t)


def _gradient_rect(c: canvas.Canvas, x: float, y: float, w: float, h: float, c1: colors.Color, c2: colors.Color, steps: int = 48):
    strip = w / steps
    for i in range(steps):
        c.setFillColor(_lerp_color(c1, c2, i / (steps - 1)))
        c.rect(x + i * strip, y, strip + 0.6, h, fill=1, stroke=0)


def _rounded_card(c: canvas.Canvas, x: float, y: float, w: float, h: float, fill: colors.Color, stroke: colors.Color = None):
    c.setFillColor(fill)
    if stroke:
        c.setStrokeColor(stroke)
        c.roundRect(x, y, w, h, 3.5 * mm, fill=1, stroke=1)
    else:
        c.roundRect(x, y, w, h, 3.5 * mm, fill=1, stroke=0)


def _status_pill(c: canvas.Canvas, x: float, y: float, text: str, tone: colors.Color):
    w = pdfmetrics.stringWidth(text, FONT, 9) + 8 * mm
    c.setFillColor(tone)
    c.roundRect(x, y, w, 6.5 * mm, 3.2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 9)
    c.drawCentredString(x + w / 2, y + 2.1 * mm, text)
    return w


def _verification_code(entity_type: str, entity_id: str) -> str:
    raw = f"{entity_type}:{entity_id}:{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


def _qr_reader(payload: str):
    from reportlab.lib.utils import ImageReader
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


AMHARIC_TITLES = {
    "Performance Plan": "የአፈጻጸም ዕቅድ",
    "Leave / Break Request": "የፍቃድ ጥያቄ",
}


def _header(c: canvas.Canvas, title: str, page_label: str):
    band_h = 30 * mm
    _gradient_rect(c, 0, PAGE_H - band_h, PAGE_W, band_h, INDIGO, FUCHSIA)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 8.5)
    c.drawString(MARGIN, PAGE_H - 8 * mm, "SDP INTERNAL PERFORMANCE & WORKFLOW MANAGEMENT SYSTEM")
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 8 * mm, page_label)
    c.setFont(FONT_BOLD, 19)
    c.drawString(MARGIN, PAGE_H - 18.5 * mm, title)
    c.setFont(FONT, 10.5)
    c.drawString(MARGIN, PAGE_H - 25 * mm, AMHARIC_TITLES.get(title, ""))


def _footer(c: canvas.Canvas, page_num: int, total_pages: int):
    c.setFillColor(MUTED)
    c.setFont(FONT, 8)
    c.drawCentredString(PAGE_W / 2, 12 * mm, f"Page {page_num} of {total_pages} — Generated by SDP System")


def _field(c: canvas.Canvas, x: float, y: float, label: str, value: str, width: float = 160 * mm, bold: bool = False):
    _rounded_card(c, x, y - 12 * mm, width, 12.5 * mm, TINT)
    c.setFillColor(VIOLET)
    c.setFont(FONT_BOLD, 7.5)
    c.drawString(x + 4 * mm, y - 4 * mm, label.upper())
    c.setFillColor(INK)
    c.setFont(FONT_BOLD if bold else FONT, 11.5 if bold else 10.5)
    c.drawString(x + 4 * mm, y - 9.5 * mm, (value or "-")[:75])


def _wrap_lines(text: str, font: str, size: float, max_width: float, max_lines: int = 8) -> list[str]:
    """Word-wrap text to fit max_width, instead of hard-slicing by character
    count (which used to cut official evaluation text off mid-word). Caps at
    max_lines as a last-resort safety limit for pathologically long input —
    the last line gets an ellipsis in that case rather than silently
    dropping content with no indication anything was cut."""
    from reportlab.lib.utils import simpleSplit
    lines = simpleSplit(text or "-", font, size, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while pdfmetrics.stringWidth(last + "…", font, size) > max_width and len(last) > 1:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines or ["-"]


def _wrapped_card_field(c: canvas.Canvas, x: float, y: float, label: str, value: str,
                         width: float, font_size: float = 9.5, max_lines: int = 6) -> float:
    """A labeled field whose value wraps across as many lines as it actually
    needs (card height grows to fit), instead of a fixed-height box that
    truncated anything past ~100 characters. Returns the y position directly
    below the card, so the caller can stack the next field without overlap."""
    lines = _wrap_lines(str(value) if value else "-", FONT, font_size, width - 8 * mm, max_lines)
    line_h = font_size * 0.42 * mm + 2 * mm
    card_h = 9 * mm + line_h * len(lines)
    _rounded_card(c, x, y - card_h, width, card_h, TINT)
    c.setFillColor(VIOLET)
    c.setFont(FONT_BOLD, 8)
    c.drawString(x + 4 * mm, y - 6 * mm, label.upper())
    c.setFillColor(INK)
    c.setFont(FONT, font_size)
    line_y = y - 6 * mm - line_h
    for line in lines:
        c.drawString(x + 4 * mm, line_y, line)
        line_y -= line_h
    return y - card_h


def _blank_field(c: canvas.Canvas, x: float, y: float, label: str, width: float = 160 * mm):
    """A labeled blank line — for the 'no text, fill in your own' style pages."""
    _rounded_card(c, x, y - 14.5 * mm, width, 15 * mm, colors.white, LINE)
    c.setFillColor(VIOLET)
    c.setFont(FONT_BOLD, 7.5)
    c.drawString(x + 4 * mm, y - 4.5 * mm, label.upper())


def _decode_signature(data_url: str | None):
    """Decode a base64 data URL (data:image/png;base64,....) into an
    ImageReader reportlab can draw, or None if invalid/absent."""
    if not data_url or "," not in data_url:
        return None
    try:
        import base64
        from reportlab.lib.utils import ImageReader
        header, b64data = data_url.split(",", 1)
        raw = base64.b64decode(b64data)
        return ImageReader(io.BytesIO(raw))
    except Exception:
        return None


def _signature_block(c: canvas.Canvas, x: float, y: float, label: str, name: str | None, signature_data_url: str | None = None, width: float = 75 * mm):
    SIG_H = 34 * mm
    _rounded_card(c, x, y - SIG_H, width, SIG_H, TINT, LINE)
    c.setFillColor(INDIGO)
    c.setFont(FONT_BOLD, 9)
    c.drawString(x + 5 * mm, y - 6 * mm, label.upper())

    sig_reader = _decode_signature(signature_data_url)
    if sig_reader is not None:
        try:
            c.drawImage(sig_reader, x + 5 * mm, y - 17 * mm, width=width - 10 * mm, height=10 * mm,
                        preserveAspectRatio=True, anchor='sw', mask='auto')
        except Exception:
            pass

    c.setStrokeColor(colors.HexColor("#9CA3AF"))
    c.line(x + 5 * mm, y - 18 * mm, x + width - 5 * mm, y - 18 * mm)
    c.setFillColor(INK)
    c.setFont(FONT, 10)
    c.drawString(x + 5 * mm, y - 23 * mm, f"Name: {name or '_______________'}")
    c.setFillColor(MUTED)
    c.setFont(FONT, 8.5)
    if sig_reader is None:
        c.drawString(x + 5 * mm, y - 27.5 * mm, "Signature: ___________________")
    else:
        c.drawString(x + 5 * mm, y - 27.5 * mm, "Signature: captured digitally above")
    c.drawString(x + 5 * mm, y - 31.5 * mm, "Date: ___________________")


def _qr_and_code(c: canvas.Canvas, entity_type: str, entity_id: str, x: float, y: float):
    code = _verification_code(entity_type, entity_id)
    reader = _qr_reader(f"SDP-VERIFY|{entity_id}|{code}")
    c.drawImage(reader, x, y, width=24 * mm, height=24 * mm)
    c.setFillColor(MUTED)
    c.setFont(FONT, 7)
    c.drawString(x, y - 4 * mm, f"Verify: {code}")


def _card_field_height(num_lines: int, font_size: float) -> float:
    line_h = font_size * 0.42 * mm + 2 * mm
    return 9 * mm + line_h * num_lines


def _cell_para(text: str, size: float = 8.5, color: colors.Color = None):
    """A table-cell Paragraph that word-wraps within its column instead of
    being silently sliced to a fixed character count and cut off mid-word."""
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    style = ParagraphStyle(
        "cell", fontName=FONT, fontSize=size, leading=size * 1.25,
        textColor=color or INK,
    )
    escaped = (str(text) if text not in (None, "") else "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(escaped, style)


def _section_title(c: canvas.Canvas, x: float, y: float, text: str):
    c.setFillColor(INDIGO)
    c.setFont(FONT_BOLD, 10.5)
    c.drawString(x, y, text.upper())
    c.setStrokeColor(LINE)
    c.line(x, y - 2.5 * mm, PAGE_W - MARGIN, y - 2.5 * mm)


# --------------------------------------------------------------- Watermark
# Every page of the "official record" gets a translucent diagonal stamp
# reflecting where the document currently stands in the workflow — a
# document still awaiting a decision is visually distinct from a finalized
# one, so nobody mistakes a mid-flight PDF for the final official record.
DRAFT_STATUSES = {"submitted", "escalated", "pending_hr", "in_review"}
APPROVED_STATUSES = {"approved", "director_approved", "hr_approved"}
REJECTED_STATUSES = {"rejected", "director_rejected", "hr_rejected"}


def _watermark(c: canvas.Canvas, status_value: str):
    if status_value in APPROVED_STATUSES:
        text, tone = "APPROVED", EMERALD
    elif status_value in REJECTED_STATUSES:
        text, tone = "REJECTED", DANGER
    else:
        text, tone = "DRAFT — PENDING DECISION", MUTED

    c.saveState()
    try:
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(38)
        c.setFillColor(tone)
        c.setFillAlpha(0.055)
        c.setFont(FONT, 34 if len(text) > 12 else 60)
        c.drawCentredString(0, 0, text)
    finally:
        c.restoreState()


def _official_seal(c: canvas.Canvas, x: float, y: float, status_value: str):
    """A small corner seal on the final approval page — the enterprise-doc
    equivalent of a rubber stamp: green check for approved, red cross for
    rejected, amber clock while still in flight."""
    if status_value in APPROVED_STATUSES:
        label, tone, mark = "OFFICIAL RECORD — APPROVED", EMERALD, "\u2713"
    elif status_value in REJECTED_STATUSES:
        label, tone, mark = "OFFICIAL RECORD — REJECTED", DANGER, "\u2717"
    else:
        label, tone, mark = "AWAITING DECISION", AMBER, "\u25cf"

    w = pdfmetrics.stringWidth(label, FONT, 9) + 16 * mm
    c.saveState()
    c.setStrokeColor(tone)
    c.setLineWidth(1.1)
    c.roundRect(x, y, w, 9 * mm, 4.5 * mm, fill=0, stroke=1)
    c.setFillColor(tone)
    c.setFont(FONT, 11)
    c.drawString(x + 4 * mm, y + 2.6 * mm, mark)
    c.setFont(FONT_BOLD, 8.5)
    c.drawString(x + 10 * mm, y + 2.9 * mm, label)
    c.restoreState()


# --------------------------------------------------------------------- Plans
def _plan_render(c: canvas.Canvas, plan, employee, decider_name, tc_comment, ef, has_extra, has_narrative, total_pages: int) -> int:
    """Draws the whole document and returns how many pages it actually used.
    Every section transition is decided by real, exact measurement (table
    wrapOn heights, wrapped-text line counts) against the real remaining
    space on the page — not a fixed page-per-section layout and not a
    fudge-factor estimate. Sections pack onto the same page whenever they
    genuinely fit, and only break to a new page when they don't, so the
    document is always exactly as long as its content actually requires.
    Called twice by the caller: once against a throwaway canvas purely to
    count final pages, once for real once that count is known (needed for
    an accurate "Page X of Y" footer, which can't be known until layout is
    resolved)."""
    FOOTER_ZONE = 16 * mm
    state = {"page_num": 1, "label": "Cover & Goals"}

    def new_page(label):
        _header(c, "Performance Plan", label)
        _watermark(c, plan.status.value)
        state["label"] = label
        return PAGE_H - 45 * mm

    def ensure_room(y, needed_h, label_if_new_page):
        if y - needed_h < FOOTER_ZONE:
            _footer(c, state["page_num"], total_pages)
            state["page_num"] += 1
            c.showPage()
            return new_page(label_if_new_page)
        return y

    y = new_page("Cover & Goals")

    # --- Cover identity fields ---
    _field(c, MARGIN, y, "Employee Name", ef.get("empName") or employee.full_name); y -= 13.5 * mm
    _field(c, MARGIN, y, "Role", employee.role.value.replace("_", " ").title()); y -= 13.5 * mm
    _field(c, MARGIN, y, "Position", ef.get("jobTitle") or employee.position); y -= 13.5 * mm
    period_label = "6 Months" if plan.period.value == "6_months" else "1 Year (Mandatory)"
    _field(c, MARGIN, y, "Plan Period", period_label); y -= 13.5 * mm
    _field(c, MARGIN, y, "Plan Title", plan.title, bold=True); y -= 13.5 * mm
    _status_pill(c, MARGIN, y - 6.5 * mm, plan.status.value.replace("_", " ").title(), STATUS_TONE.get(plan.status.value, MUTED))
    c.setFillColor(MUTED); c.setFont(FONT, 8)
    c.drawString(MARGIN, y - 13 * mm, f"Submitted on {plan.created_at.strftime('%Y-%m-%d')}")
    y -= 20 * mm

    # --- Goals + Notes ---
    _section_title(c, MARGIN, y, "Goals to be Achieved"); y -= 10 * mm
    c.setFillColor(INK)
    goals = plan.goals or []
    if goals:
        for i, goal in enumerate(goals, start=1):
            text = goal.get("text") if isinstance(goal, dict) else str(goal)
            weight = goal.get("weight") if isinstance(goal, dict) else None
            score = goal.get("score") if isinstance(goal, dict) else None
            suffix = f"  ({score}/{weight}%)" if weight not in (None, "") else ""
            lines = _wrap_lines(f"{text}{suffix}", FONT, 10, PAGE_W - 2 * MARGIN - 8 * mm, max_lines=3)
            y = ensure_room(y, 5.5 * mm * len(lines) + 3.5 * mm, "Goals (cont.)")
            c.setFillColor(INK); c.setFont(FONT, 10)
            c.drawString(MARGIN, y, f"{i}.")
            for line in lines:
                c.setFillColor(INK); c.setFont(FONT, 10)
                c.drawString(MARGIN + 8 * mm, y, line)
                y -= 5.5 * mm
            y -= 3.5 * mm
    else:
        _blank_field(c, MARGIN, y, "Goal 1"); y -= 14 * mm
        _blank_field(c, MARGIN, y, "Goal 2"); y -= 14 * mm
        _blank_field(c, MARGIN, y, "Goal 3")
    y -= 10 * mm
    notes_lines = _wrap_lines(plan.notes or "-", FONT, 10, PAGE_W - 2 * MARGIN, max_lines=4)
    y = ensure_room(y, 8 * mm + 5 * mm * len(notes_lines), "Goals (cont.)")
    c.setFillColor(INK); c.setFont(FONT, 11)
    c.drawString(MARGIN, y, "Notes:")
    y -= 8 * mm
    for line in notes_lines:
        c.setFillColor(INK); c.setFont(FONT, 10)
        c.drawString(MARGIN, y, line)
        y -= 5 * mm
    y -= 8 * mm  # breathing room before whatever section follows on this page

    # --- Extended Evaluation (institutional details + scoring tables) ---
    if has_extra:
        details = [
            ("Grade", ef.get("grade")), ("Directorate", ef.get("directorate")),
            ("Supervisor", ef.get("supervisorName")), ("Budget Year", ef.get("budgetYear")),
            ("Evaluation Type", ef.get("evalType")),
        ]
        details_h = 8 * mm + ((len(details) + 1) // 2) * 14 * mm + 12 * mm
        y = ensure_room(y, details_h, "Extended Evaluation")
        _section_title(c, MARGIN, y, "Institutional & Role Details"); y -= 8 * mm
        col_x = [MARGIN, MARGIN + 90 * mm]
        col_w = 86 * mm
        for i, (label, value) in enumerate(details):
            cx = col_x[i % 2]
            if i % 2 == 0 and i > 0:
                y -= 14 * mm
            c.setFillColor(MUTED); c.setFont(FONT_BOLD, 7.5)
            c.drawString(cx, y, label.upper())
            c.setFillColor(INK); c.setFont(FONT, 10)
            line = _wrap_lines(str(value) if value else "-", FONT, 10, col_w, max_lines=1)[0]
            c.drawString(cx, y - 5 * mm, line)
        y -= 12 * mm

        six_month_rows = ef.get("sixMonthScores") or []
        if six_month_rows:
            table_rows = [["#", "Objective", "Weight", "Achieved", "Score"]]
            for i, row in enumerate(six_month_rows, start=1):
                table_rows.append([
                    str(i), _cell_para(row.get("objective", "")), str(row.get("weight", "")),
                    _cell_para(row.get("done", "")), str(row.get("score", "")),
                ])
            col_widths = [15 * mm, 75 * mm, 20 * mm, 40 * mm, 20 * mm]
            from reportlab.platypus import Table, TableStyle
            table = Table(table_rows, colWidths=col_widths)
            table.setStyle(_table_style())
            tw, th = table.wrapOn(c, sum(col_widths), 1000)
            y = ensure_room(y, 8 * mm + th + 18 * mm, "Extended Evaluation (cont.)")
            _section_title(c, MARGIN, y, "6-Month Performance Scoring"); y -= 8 * mm
            table.drawOn(c, MARGIN, y - th)
            y -= th + 8 * mm
            total_score = ef.get("totalScore")
            if total_score:
                c.setFillColor(INK); c.setFont(FONT, 10)
                c.drawRightString(PAGE_W - MARGIN, y, f"Total Score: {total_score}%")
                y -= 10 * mm

        yearly_rows = ef.get("yearlyScores") or []
        if yearly_rows:
            table_rows = [["#", "Metric", "1st Half", "2nd Half", "Avg"]]
            for i, row in enumerate(yearly_rows, start=1):
                table_rows.append([
                    str(i), _cell_para(row.get("metric", "")), str(row.get("half1", "")),
                    str(row.get("half2", "")), str(row.get("avg", "")),
                ])
            col_widths = [15 * mm, 75 * mm, 25 * mm, 25 * mm, 20 * mm]
            from reportlab.platypus import Table
            table = Table(table_rows, colWidths=col_widths)
            table.setStyle(_table_style())
            tw, th = table.wrapOn(c, sum(col_widths), 1000)
            y = ensure_room(y, 8 * mm + th + 8 * mm, "Extended Evaluation (cont.)")
            _section_title(c, MARGIN, y, "Yearly Comparison"); y -= 8 * mm
            table.drawOn(c, MARGIN, y - th)
            y -= th + 8 * mm

        rating = ef.get("rating")
        if rating:
            y = ensure_room(y, 10 * mm, "Extended Evaluation (cont.)")
            c.setFillColor(INDIGO); c.setFont(FONT, 10)
            c.drawString(MARGIN, y, f"Overall Rating: {rating}")
            y -= 10 * mm

    # --- Narrative Review ---
    narrative_fields = [
        ("6-Month Improvement Action Plan", "improvementPlan"),
        ("Key Achievements This Year", "achievements"),
        ("Challenges Faced", "challenges"),
        ("Training / Capacity-Building Needs", "trainingNeeds"),
    ]
    if has_narrative:
        for label, key in narrative_fields:
            val = ef.get(key)
            if not val:
                continue
            lines = _wrap_lines(str(val), FONT, 9.5, PAGE_W - 2 * MARGIN - 8 * mm, max_lines=8)
            needed = _card_field_height(len(lines), 9.5) + 8 * mm
            y = ensure_room(y, needed, "Narrative Review")
            y = _wrapped_card_field(c, MARGIN, y, label, val, PAGE_W - 2 * MARGIN, font_size=9.5, max_lines=8)
            y -= 8 * mm

    # --- Review & Remarks ---
    tc_lines = _wrap_lines(tc_comment or "-", FONT, 10, PAGE_W - 2 * MARGIN - 8 * mm, max_lines=5)
    remarks_head_h = 20 * mm + _card_field_height(len(tc_lines), 10) + 10 * mm
    y = ensure_room(y, remarks_head_h, "Review & Remarks")
    _field(c, MARGIN, y, "Decision Reason", plan.decision_reason or "-"); y -= 20 * mm
    y = _wrapped_card_field(c, MARGIN, y, "Technical Committee Comment", tc_comment or "-",
                             PAGE_W - 2 * MARGIN, font_size=10, max_lines=5)
    y -= 10 * mm
    for label, key in [("Strengths", "strengths"), ("Weaknesses / Improvement", "weaknesses"),
                        ("Supervisor Comments", "supervisorComments"), ("Employee Feedback", "employeeComments")]:
        val = ef.get(key)
        if not val:
            continue
        lines = _wrap_lines(str(val), FONT, 9.5, PAGE_W - 2 * MARGIN - 8 * mm, max_lines=4)
        needed = _card_field_height(len(lines), 9.5) + 8 * mm
        y = ensure_room(y, needed, "Review & Remarks (cont.)")
        y = _wrapped_card_field(c, MARGIN, y, label, val, PAGE_W - 2 * MARGIN, font_size=9.5, max_lines=4)
        y -= 8 * mm

    # --- Approval & Signatures ---
    APPROVAL_H = 34 * mm + 4 * mm + 24 * mm + 4 * mm  # signature card + gap + QR (drawn upward from its y) + verify label
    y = ensure_room(y, APPROVAL_H, "Approval")
    prepared_name = ef.get("prep_name") or employee.full_name
    approved_name = ef.get("app_name") or decider_name
    _signature_block(c, MARGIN, y, "Prepared by (Employee)", prepared_name, plan.prepared_signature)
    _signature_block(c, PAGE_W - MARGIN - 75 * mm, y, "Approved by (Team Leader / Director)", approved_name, plan.decided_signature)
    # QR is drawn with its bottom-left at the given y and extends 24mm
    # *upward* — so this must sit a full 24mm + gap below the signature
    # card's bottom edge (y - 34mm), not just offset from the card's top.
    _qr_and_code(c, "performance_plan", str(plan.id), MARGIN, y - 34 * mm - 4 * mm - 24 * mm)
    _official_seal(c, PAGE_W - MARGIN - 68 * mm, y - 34 * mm - 4 * mm - 24 * mm, plan.status.value)

    _footer(c, state["page_num"], total_pages)
    c.showPage()
    return state["page_num"]


def _table_style():
    from reportlab.platypus import TableStyle
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INDIGO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ])


def generate_performance_plan_pdf(plan, employee, decider_name: str | None, tc_comment: str | None) -> str:
    filename = f"performance_plan_{plan.id}.pdf"
    path = os.path.join(DOCS_DIR, filename)
    ef = plan.extra_fields or {}
    has_extra = bool(ef)
    has_narrative = any(
        ef.get(k) for k in ("improvementPlan", "achievements", "challenges", "trainingNeeds")
    )

    # First pass: render to a throwaway in-memory canvas purely to find out
    # how many pages the real content actually needs (exact, not guessed —
    # every page break above is decided by real measurement). Second pass
    # draws for real now that the true count is known, so the "Page X of Y"
    # footer is always accurate.
    scratch_buffer = io.BytesIO()
    scratch_canvas = canvas.Canvas(scratch_buffer, pagesize=A4)
    real_total_pages = _plan_render(scratch_canvas, plan, employee, decider_name, tc_comment,
                                     ef, has_extra, has_narrative, total_pages=1)

    c = canvas.Canvas(path, pagesize=A4)
    _plan_render(c, plan, employee, decider_name, tc_comment, ef, has_extra, has_narrative,
                 total_pages=real_total_pages)
    c.save()
    return path


# ------------------------------------------------------------------- Leaves
def _leave_render(c: canvas.Canvas, leave, employee, decider_name, ef, has_extra, total_pages: int) -> int:
    """Same dynamic-flow approach as _plan_render: every section transition
    is decided by real measurement against real remaining space, not a
    fixed page-per-section layout. Called twice by the caller — once to
    measure the true page count, once to draw for real."""
    FOOTER_ZONE = 16 * mm
    state = {"page_num": 1}

    def new_page(label):
        _header(c, "Leave / Break Request", label)
        _watermark(c, leave.status.value)
        return PAGE_H - 45 * mm

    def ensure_room(y, needed_h, label_if_new_page):
        if y - needed_h < FOOTER_ZONE:
            _footer(c, state["page_num"], total_pages)
            state["page_num"] += 1
            c.showPage()
            return new_page(label_if_new_page)
        return y

    y = new_page("Details")

    _field(c, MARGIN, y, "Name", ef.get("fullName") or employee.full_name); y -= 13.5 * mm
    _field(c, MARGIN, y, "Role", employee.role.value.replace("_", " ").title()); y -= 13.5 * mm
    _field(c, MARGIN, y, "Position", ef.get("jobTitle") or employee.position); y -= 13.5 * mm
    days_label = "1 Month (30 days)" if leave.days == 30 else f"{leave.days} days"
    _field(c, MARGIN, y, "Leave Type", leave.leave_type.value.title(), bold=True); y -= 13.5 * mm
    _field(c, MARGIN, y, "Duration", days_label); y -= 13.5 * mm
    _field(c, MARGIN, y, "Start Date", leave.start_date.strftime("%Y-%m-%d")); y -= 13.5 * mm
    _field(c, MARGIN, y, "End Date", leave.end_date.strftime("%Y-%m-%d")); y -= 13.5 * mm
    reason_lines = _wrap_lines(leave.reason or "-", FONT, 10, PAGE_W - 2 * MARGIN - 8 * mm, max_lines=5)
    y = ensure_room(y, _card_field_height(len(reason_lines), 10), "Details (cont.)")
    y = _wrapped_card_field(c, MARGIN, y, "Reason for Leave", leave.reason or "-",
                             PAGE_W - 2 * MARGIN, font_size=10, max_lines=5)
    y -= 8 * mm

    if has_extra:
        contact_fields = [
            ("Department", ef.get("department")), ("Job Title", ef.get("jobTitle")),
            ("Phone", ef.get("phone")), ("Contact Address During Leave", ef.get("contactAddress")),
        ]
        block_h = 8 * mm + len(contact_fields) * 13.5 * mm
        y = ensure_room(y, block_h, "Contact & HR Audit")
        _section_title(c, MARGIN, y, "Contact Information"); y -= 8 * mm
        for label, value in contact_fields:
            _field(c, MARGIN, y, label, value); y -= 13.5 * mm
        y -= 6 * mm

        delegation_fields = [
            ("Delegated Employee", ef.get("delegateName")), ("Delegate Confirmation", ef.get("delegateSign")),
            ("Remaining Leave Balance", ef.get("leaveBalance")), ("HR Officer", ef.get("hrOfficer")),
        ]
        block_h = 8 * mm + len(delegation_fields) * 13.5 * mm
        y = ensure_room(y, block_h, "Contact & HR Audit (cont.)")
        _section_title(c, MARGIN, y, "Work Delegation & HR Audit"); y -= 8 * mm
        for label, value in delegation_fields:
            _field(c, MARGIN, y, label, str(value) if value else None); y -= 13.5 * mm
        y -= 8 * mm

    decision_lines = _wrap_lines(leave.decision_reason or "-", FONT, 10, PAGE_W - 2 * MARGIN - 8 * mm, max_lines=4)
    APPROVAL_H = 22 * mm + _card_field_height(len(decision_lines), 10) + 15 * mm + 34 * mm + 4 * mm + 24 * mm + 4 * mm
    y = ensure_room(y, APPROVAL_H, "Decision & Approval")
    _status_pill(c, MARGIN, y - 6.5 * mm, leave.status.value.replace("_", " ").title(), STATUS_TONE.get(leave.status.value, MUTED))
    y -= 22 * mm
    y = _wrapped_card_field(c, MARGIN, y, "Decision Reason", leave.decision_reason or "-",
                             PAGE_W - 2 * MARGIN, font_size=10, max_lines=4)
    y -= 15 * mm
    prepared_name = ef.get("reqName") or employee.full_name
    approved_name = ef.get("appName") or decider_name
    _signature_block(c, MARGIN, y, "Prepared by (Employee)", prepared_name, leave.prepared_signature)
    _signature_block(c, PAGE_W - MARGIN - 75 * mm, y, "Approved by", approved_name, leave.decided_signature)
    _qr_and_code(c, "leave_request", str(leave.id), MARGIN, y - 34 * mm - 4 * mm - 24 * mm)
    _official_seal(c, PAGE_W - MARGIN - 68 * mm, y - 34 * mm - 4 * mm - 24 * mm, leave.status.value)

    _footer(c, state["page_num"], total_pages)
    c.showPage()
    return state["page_num"]


def generate_leave_pdf(leave, employee, decider_name: str | None) -> str:
    filename = f"leave_request_{leave.id}.pdf"
    path = os.path.join(DOCS_DIR, filename)
    ef = leave.extra_fields or {}
    has_extra = bool(ef)

    scratch_buffer = io.BytesIO()
    scratch_canvas = canvas.Canvas(scratch_buffer, pagesize=A4)
    real_total_pages = _leave_render(scratch_canvas, leave, employee, decider_name, ef, has_extra, total_pages=1)

    c = canvas.Canvas(path, pagesize=A4)
    _leave_render(c, leave, employee, decider_name, ef, has_extra, total_pages=real_total_pages)
    c.save()
    return path
