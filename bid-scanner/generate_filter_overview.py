"""Generate a management-level PDF overview of the FCU bid filtering pipeline."""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from datetime import date

CHARCOAL = colors.HexColor("#1C1C1E")
GOLD     = colors.HexColor("#C8922A")
CREAM    = colors.HexColor("#F5F0E8")
LIGHT_GRAY = colors.HexColor("#F2F2F2")
MID_GRAY   = colors.HexColor("#CCCCCC")

OUT = "output/bid_filter_overview.pdf"


def build():
    doc = SimpleDocTemplate(
        OUT,
        pagesize=letter,
        leftMargin=0.85*inch,
        rightMargin=0.85*inch,
        topMargin=0.85*inch,
        bottomMargin=0.85*inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20,
                                 textColor=CHARCOAL, spaceAfter=4, leading=24)
    subtitle_style = ParagraphStyle("subtitle", fontName="Helvetica", fontSize=11,
                                    textColor=GOLD, spaceAfter=2)
    date_style = ParagraphStyle("date", fontName="Helvetica", fontSize=9,
                                textColor=colors.HexColor("#888888"), spaceAfter=16)
    section_style = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12,
                                   textColor=CHARCOAL, spaceBefore=14, spaceAfter=4)
    step_label_style = ParagraphStyle("step_label", fontName="Helvetica-Bold", fontSize=10,
                                      textColor=GOLD)
    body_style = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5,
                                textColor=CHARCOAL, leading=14, spaceAfter=4)
    note_style = ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8.5,
                                textColor=colors.HexColor("#555555"), leading=12)
    footer_style = ParagraphStyle("footer", fontName="Helvetica", fontSize=8,
                                  textColor=colors.HexColor("#AAAAAA"), alignment=TA_CENTER)

    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph("FCU Bid Monitoring System", title_style))
    story.append(Paragraph("How We Filter &amp; Score Bids — Management Overview", subtitle_style))
    story.append(Paragraph(f"Generated {date.today().strftime('%B %d, %Y')}", date_style))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=14))

    # ── Sources ──────────────────────────────────────────────────────────────
    story.append(Paragraph("Sources We Monitor (5 Portals)", section_style))

    sources = [
        ["Portal", "Type", "Coverage"],
        ["SAM.gov", "Federal", "Federal contracts — California only"],
        ["PlanetBids", "City / County", "30 LA-area agency portals"],
        ["BidNet Direct", "Statewide", "CA public solicitations"],
        ["OpenGov", "City portals", "8 cities: Bell, Redondo, Manhattan Beach, Pasadena, Santa Monica, Sacramento, SF, Alameda"],
        ["Cal eProcure + Caltrans CCOP", "State of CA", "CA state contracts + Caltrans all districts"],
    ]

    src_table = Table(sources, colWidths=[1.6*inch, 1.2*inch, 3.8*inch])
    src_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), CHARCOAL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 9),
        ("BACKGROUND",  (0, 1), (-1, -1), LIGHT_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 1), (-1, -1), CHARCOAL),
        ("GRID",        (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(src_table)
    story.append(Spacer(1, 14))

    # ── Pipeline ─────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY, spaceAfter=10))
    story.append(Paragraph("The Filtering Pipeline", section_style))

    steps = [
        (
            "Step 1 — Geography",
            "Every portal is pre-filtered to California only before we pull any data. No national or out-of-state noise ever enters the system."
        ),
        (
            "Step 2 — Keyword Search",
            "We run 7 search terms against each portal:\n"
            "flooring · carpet · resilient flooring · window covering · blinds · LVT vinyl · tile installation\n"
            "Only bids matching at least one term are retrieved."
        ),
        (
            "Step 3 — Status Filter",
            "For PlanetBids and OpenGov, any bid already marked closed, canceled, awarded, or rejected is dropped immediately. We only work open bids."
        ),
        (
            "Step 4 — Relevance Check",
            "Every surviving bid title is checked against a broader list of 30+ flooring-specific terms "
            "(VCT, vinyl plank, hardwood, epoxy floor, ceramic tile, shades, linoleum, etc.) to catch variations the keyword search may have missed. "
            "Flooring installation, wholesale supply (furnish-only), and floor-care maintenance (strip & wax, carpet cleaning, "
            "blind cleaning/repair, on-call flooring repair) all count. Only services with no floor-covering component "
            "(janitorial, pest control, landscaping, glass washing) are dropped.\n\n"
            "Optional AI second pass: if enabled, an AI model reviews construction-type bids "
            "(e.g. \"Gymnasium Renovation\") that didn't match the term list, to judge whether flooring is the primary scope. "
            "Each bid is flagged Relevant: Yes / No."
        ),
        (
            "Step 5 — Winnability Score (after document parsing)",
            "Once bid documents are downloaded and parsed, each bid is scored 0–100 from three factors: "
            "how far the job site is from the Chatsworth shop, how many days are left to bid, and the award method "
            "(best-value work scores higher than pure low-bid). A bid missing any of those inputs is marked "
            "NEEDS REVIEW instead of scored."
        ),
        (
            "Step 6 — New-Bid Email Digest",
            "Only bids that are Relevant AND brand new (not already in our database) trigger the email alert. "
            "Bids we've already seen do not re-notify the team."
        ),
    ]

    for label, body in steps:
        story.append(Paragraph(label, step_label_style))
        story.append(Paragraph(body.replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 6))

    # ── Score table ──────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY, spaceAfter=10))
    story.append(Paragraph("Winnability Scoring Breakdown", section_style))
    story.append(Paragraph(
        "After the bid documents are parsed, each bid is scored 0–100 from three factors — "
        "how far the job is, how much time is left to bid, and how the contract is awarded:",
        body_style
    ))

    score_rows = [
        ["Factor", "Score Impact"],
        ["Job site ≤ 45 min from the Chatsworth shop", "60"],
        ["Job site ≤ 75 min (central LA / Ventura county)", "48"],
        ["Job site ≤ 110 min (South Bay / north Orange County)", "32"],
        ["Job site > 110 min (deep Orange County / San Diego)", "16"],
        ["21+ days left to bid", "+30"],
        ["10–13 days left to bid", "+15"],
        ["Under 4 days left to bid", "+0"],
        ["Best-value / qualifications award (favors FCU)", "+10"],
        ["Low-bid-only award (pure price fight)", "−6"],
        ["Flooring is only a minor part of a larger project", "NO-GO"],
    ]

    def impact_color(val):
        if val.startswith("+") or val[0].isdigit():
            return colors.HexColor("#1A6B2E")
        if val.startswith("−") or val == "NO-GO":
            return colors.HexColor("#A00000")
        return CHARCOAL

    score_table_data = []
    for i, row in enumerate(score_rows):
        score_table_data.append(row)

    score_table = Table(score_table_data, colWidths=[4.8*inch, 1.4*inch])
    score_style = [
        ("BACKGROUND",    (0, 0), (-1, 0), CHARCOAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("TEXTCOLOR",     (0, 1), (0, -1), CHARCOAL),
        ("ALIGN",         (1, 0), (1, -1), "CENTER"),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
    ]
    # Color the impact column per row
    for i, row in enumerate(score_rows[1:], start=1):
        c = impact_color(row[1])
        score_style.append(("TEXTCOLOR", (1, i), (1, i), c))
        score_style.append(("FONTNAME",  (1, i), (1, i), "Helvetica-Bold"))

    score_table.setStyle(TableStyle(score_style))
    story.append(score_table)

    story.append(Spacer(1, 10))

    # Verdict key
    verdict_data = [
        ["Verdict", "Score Range", "Meaning"],
        ["GO",     "58 – 100", "Worth estimating — assign to Joanne"],
        ["MAYBE",  "33 – 57",  "Review case by case — Ben / Joanne call"],
        ["NO-GO",  "0 – 32",   "Skip — below our threshold"],
        ["NEEDS REVIEW", "—",  "Missing an input (location / due date / scope) — a person must look"],
    ]
    verdict_table = Table(verdict_data, colWidths=[1.2*inch, 1.4*inch, 4.0*inch])
    verdict_colors = [
        colors.HexColor("#1A6B2E"),
        colors.HexColor("#7A5A00"),
        colors.HexColor("#A00000"),
        colors.HexColor("#555555"),
    ]
    verdict_style = [
        ("BACKGROUND",    (0, 0), (-1, 0), CHARCOAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("TEXTCOLOR",     (0, 1), (0, -1), CHARCOAL),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("FONTNAME",      (0, 1), (0, -1), "Helvetica-Bold"),
    ]
    for i, c in enumerate(verdict_colors, start=1):
        verdict_style.append(("TEXTCOLOR", (0, i), (0, i), c))
    verdict_table.setStyle(TableStyle(verdict_style))
    story.append(verdict_table)

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY, spaceAfter=6))
    story.append(Paragraph(
        "Floor Covering Unlimited, Inc. — Internal Use Only — AI Bid Monitoring System",
        footer_style
    ))

    doc.build(story)
    print(f"✓ PDF saved → {OUT}")


if __name__ == "__main__":
    import os
    os.makedirs("output", exist_ok=True)
    build()
