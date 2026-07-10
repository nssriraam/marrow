"""
Marrow — PDF Report Generator (Stakeholder Handoff)

Generates polished, enterprise-ready PDF reports from scan results
using ReportLab. Designed for one-click export from the dashboard
so FinOps/SecOps teams can share findings with leadership without
requiring access to the live platform.

Report contents:
    - Executive summary (LLM-generated or deterministic)
    - Resource-level action table with justifications
    - Projected monthly and annual savings
    - Risk reduction metrics
    - Confidence scores per recommendation

Text wrapping is handled via ReportLab Paragraph objects to
prevent overflow on long justification strings.
"""

import io
import html
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from app import models
from app.reasoner import ACTION_STYLES

def generate_report(scan_id: int = None) -> io.BytesIO:
    """
    Generates a PDF report for the specified scan.
    If scan_id is None, uses the most recent scan.
    Returns a BytesIO buffer containing the PDF data.
    """
    with models.get_connection() as db:
        if scan_id is None:
            scan = db.execute("SELECT * FROM scans ORDER BY timestamp DESC LIMIT 1").fetchone()
            if not scan:
                raise ValueError("No scans found in the database.")
            scan_id = scan["id"]
        else:
            scan = db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
            if not scan:
                raise ValueError(f"Scan ID {scan_id} not found.")
        
        scan = dict(scan)

        recs = db.execute("SELECT * FROM recommendations WHERE scan_id = ? ORDER BY priority_score DESC", (scan_id,)).fetchall()

    # Calculate summary metrics
    total_savings = sum(r["monthly_savings_usd"] for r in recs)
    
    # Initialize PDF buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=25
    )
    
    h2_style = styles["Heading2"]
    h2_style.textColor = colors.HexColor("#1e293b")
    h2_style.fontSize = 15
    h2_style.spaceAfter = 12
    h2_style.fontName = "Helvetica-Bold"
    
    normal_style = styles["Normal"]
    normal_style.textColor = colors.HexColor("#334155")
    
    # Custom styles for table cells to allow wrapping
    wrap_style = ParagraphStyle(
        'WrapStyle',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1e293b")
    )
    
    # Header Section
    elements.append(Paragraph(f'<font face="Helvetica-Bold">MARROW</font>&nbsp;<font color="#0f172a" size="18">&mdash;</font>&nbsp;<font face="Helvetica" color="#475569">Cloud Optimization & Security Report</font>', title_style))
    raw_date = scan['timestamp']
    formatted_date = raw_date[:16].replace('T', ' ') if 'T' in raw_date else raw_date
    elements.append(Paragraph(f"<b>Scan ID:</b> #{scan['id']} &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; <b>Date:</b> {formatted_date}", subtitle_style))
    
    # Executive Summary Section
    elements.append(Paragraph("Executive Summary", h2_style))
    if scan.get("executive_summary"):
        elements.append(Paragraph(html.escape(scan["executive_summary"]), normal_style))
        elements.append(Spacer(1, 15))
        
    summary_data = [
        ["Total Resources Scanned", str(scan["resource_count"])],
        ["Total Monthly Spend", f"${scan['total_monthly_cost']:.2f}"],
        ["Identified Monthly Savings", f"${total_savings:.2f}"],
        ["Total Risk Score", str(scan["total_risk_score"])]
    ]
    
    summary_table = Table(summary_data, colWidths=[150, 150])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#f6f8fa")),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#24292f")),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#d0d7de"))
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 30))
    
    # Recommendations Section
    elements.append(Paragraph("Detailed Recommendations", h2_style))
    
    # Table Header
    table_data = [["Resource ID", "Action", "Savings/mo", "Risk Reduction", "Priority", "Justification"]]
    
    for r in recs:
        # Match colors from ACTION_STYLES if present
        action_name = r['action'] or 'ignore'
        action_color_hex = ACTION_STYLES.get(action_name, ACTION_STYLES.get('ignore', {})).get("color", "#000000")
        
        # Colorize the action text in PDF using HTML markup supported by ReportLab Paragraph
        action_para = Paragraph(f'<font color="{action_color_hex}"><b>{action_name.upper()}</b></font>', wrap_style)
        
        justification_para = Paragraph(html.escape(r['justification']), wrap_style)
        resource_para = Paragraph(html.escape(r['resource_id']), wrap_style)
        risk_para = Paragraph(html.escape(str(r['risk_reduction'])), wrap_style)
        
        savings_str = f"+${r['monthly_savings_usd']:.0f}" if r['monthly_savings_usd'] > 0 else "-"
        
        table_data.append([
            resource_para,
            action_para,
            savings_str,
            risk_para,
            str(r['priority_score']),
            justification_para
        ])
    
    # We use landscape letter which is 792 points wide. Left+Right margins = 60. Usable width = 732.
    col_widths = [120, 90, 70, 110, 50, 292]
    
    rec_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    rec_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#24292f")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'), # align savings right
        ('ALIGN', (4,0), (4,-1), 'CENTER'), # align priority center
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor("#d0d7de")),
        ('VALIGN', (0,0), (-1,-1), 'TOP')
    ]))
    
    elements.append(rec_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
