"""
AI-CON PDF Export Module.
Generates a structured, professional PDF report containing college shortlist,
popularity/reputation score, cutoffs, ROI estimates, and key institutional metrics.
"""

import io
from typing import List, Dict, Any, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


def generate_college_list_pdf(
    query_title: str,
    colleges: List[Dict[str, Any]],
    user_context: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Generate PDF byte stream for a list of colleges with their details.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    header_style = ParagraphStyle(
        'DocHeader',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica-Bold',
        spaceAfter=4,
    )
    subheader_style = ParagraphStyle(
        'DocSubHeader',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#2563EB'),
        fontName='Helvetica-Bold',
        spaceAfter=12,
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#475569'),
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0F172A'),
    )
    cell_regular = ParagraphStyle(
        'CellRegular',
        parent=styles['Normal'],
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#334155'),
    )
    cell_header = ParagraphStyle(
        'CellHeader',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        fontName='Helvetica-Bold',
        textColor=colors.white,
    )

    story = []

    # Title & Branding Banner
    story.append(Paragraph("AI-CON Admission Consultant — College Shortlist Report", header_style))
    story.append(Paragraph("Grounded Official MHT-CET Admission Intelligence | Directorate of Higher Education, Maharashtra", subheader_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563EB'), spaceAfter=10))

    # Context / Filter Summary Box
    context_text = f"<b>Query / Target:</b> {query_title}<br/>"
    if user_context:
        ctx_parts = []
        if user_context.get("percentile"):
            ctx_parts.append(f"<b>CET Percentile:</b> {user_context['percentile']}%")
        if user_context.get("category"):
            ctx_parts.append(f"<b>Category:</b> {user_context['category']}")
        if user_context.get("location"):
            ctx_parts.append(f"<b>Location / District:</b> {user_context['location']}")
        if user_context.get("preferred_branches"):
            ctx_parts.append(f"<b>Preferred Branches:</b> {', '.join(user_context['preferred_branches'])}")
        if ctx_parts:
            context_text += " &nbsp;|&nbsp; ".join(ctx_parts)
    
    story.append(Paragraph(context_text, meta_style))
    story.append(Spacer(1, 14))

    # College Summary Table
    table_data = [
        [
            Paragraph("Rank", cell_header),
            Paragraph("College Name & Code", cell_header),
            Paragraph("Location / Autonomy", cell_header),
            Paragraph("Branch & Cutoff", cell_header),
            Paragraph("Popularity & ROI", cell_header),
        ]
    ]

    for idx, c in enumerate(colleges, 1):
        name_str = f"<b>{c.get('institute_name', 'Unknown Institute')}</b>"
        code_str = f"<br/><font color='#64748B'>Code: {c.get('institute_code') or 'N/A'}</font>"
        
        loc_str = f"{c.get('district') or c.get('city') or 'Maharashtra'}<br/>"
        loc_str += f"<font color='#2563EB'>{c.get('autonomy_type') or c.get('institution_type') or 'Affiliated'}</font>"
        
        cutoff_info = ""
        if c.get("cutoff_percentile") is not None:
            cutoff_info = f"<b>{c['cutoff_percentile']}%</b>"
            if c.get("closing_rank"):
                cutoff_info += f" (Rank {c['closing_rank']})"
            cutoff_info += f"<br/><font color='#475569'>{c.get('branch', 'Engineering')}</font>"
        elif c.get("cutoffs"):
            # If multiple cutoffs passed
            top_cut = c["cutoffs"][0]
            cutoff_info = f"<b>{top_cut.get('closing_percentile')}%</b><br/><font color='#475569'>{top_cut.get('branch')}</font>"
        else:
            cutoff_info = "<font color='#64748B'>Cutoffs in detailed records</font>"

        if c.get("popularity_score") is not None:
            pop_str = f"<b>Pop: {c['popularity_score']}/100</b><br/>"
        else:
            pop_str = "<b>Pop: N/A</b><br/><font color='#64748B' size='6'>Unverified</font><br/>"
        roi_val = c.get("roi_tier") or "Not computable"
        pop_str += f"<font color='#059669'>ROI: {roi_val}</font><br/>"
        if c.get("median_package"):
            pop_str += f"<font color='#475569'>Median: {c.get('median_package')}</font>"

        table_data.append([
            Paragraph(str(idx), cell_bold),
            Paragraph(name_str + code_str, cell_regular),
            Paragraph(loc_str, cell_regular),
            Paragraph(cutoff_info, cell_regular),
            Paragraph(pop_str, cell_regular),
        ])

    col_widths = [0.4 * inch, 2.8 * inch, 1.4 * inch, 1.6 * inch, 1.3 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))

    story.append(t)
    story.append(Spacer(1, 16))

    # Notes & Statutory Compliance Footer
    disclaimer = (
        "<b>Notice & Compliance:</b> All cutoff figures, institute codes, and reservation quotas are grounded in "
        "verified Maharashtra CET Cell Centralized Admission Process (CAP) official datasets. Popularity data and "
        "ROI estimates are marked N/A or 'Not computable' when official choice-form preferences or audited fee/placement reports "
        "are unpublished in CAP cutoff bulletins. No cutoffs or admissions are guaranteed."
    )
    story.append(Paragraph(disclaimer, ParagraphStyle('Disc', parent=styles['Normal'], fontSize=7.5, leading=10, textColor=colors.HexColor('#64748B'))))

    doc.build(story)
    return buffer.getvalue()

