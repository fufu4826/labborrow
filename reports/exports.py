"""Excel and PDF response builders for reports."""
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle


def _period(date_from, date_to):
    return f"{date_from:%d/%m/%Y} - {date_to:%d/%m/%Y}"


def _local_value(value):
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value).replace(tzinfo=None)
        return value
    return value


def _response(content, kind, fmt, date_from, date_to, content_type):
    filename = f"{kind}_{date_from:%Y-%m-%d}_{date_to:%Y-%m-%d}.{fmt}"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def to_xlsx(title, headers, rows, date_from, date_to, kind="report"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = str(title)[:31]
    sheet.append([title])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
    sheet["A1"].font = Font(bold=True, size=16)
    sheet.append([_ ("Period"), _period(date_from, date_to)])
    sheet["A2"].font = Font(bold=True)
    sheet.append(headers)
    for cell in sheet[3]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in rows:
        sheet.append([_local_value(value) for value in row])
    for row in sheet.iter_rows(min_row=4):
        for cell in row:
            if isinstance(cell.value, datetime):
                cell.number_format = "dd/mm/yyyy hh:mm"
            elif isinstance(cell.value, date):
                cell.number_format = "dd/mm/yyyy"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for column in sheet.columns:
        letter = get_column_letter(column[0].column)
        width = min(max(max((len(str(cell.value or "")) for cell in column), default=10) + 2, 12), 48)
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "A4"
    buffer = BytesIO()
    workbook.save(buffer)
    return _response(buffer.getvalue(), kind, "xlsx", date_from, date_to,
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _register_fonts():
    regular_name = "THSarabunPSK"
    bold_name = "THSarabunPSK-Bold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        fonts_dir = Path(__file__).resolve().parent / "fonts"
        pdfmetrics.registerFont(TTFont(regular_name, str(fonts_dir / "THSarabunPSK.ttf")))
        pdfmetrics.registerFont(TTFont(bold_name, str(fonts_dir / "THSarabunPSK-Bold.ttf")))
        pdfmetrics.registerFontFamily(regular_name, normal=regular_name, bold=bold_name,
                                      italic=regular_name, boldItalic=bold_name)
    return regular_name, bold_name


def to_pdf(title, headers, rows, date_from, date_to, kind="report"):
    font, bold_font = _register_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm,
                            topMargin=14 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName=bold_font,
                                 fontSize=20, leading=24, alignment=TA_LEFT)
    meta_style = ParagraphStyle("ReportMeta", parent=styles["Normal"], fontName=font,
                                fontSize=14, leading=17)
    cell_style = ParagraphStyle("ReportCell", parent=styles["Normal"], fontName=font,
                                fontSize=14, leading=16)
    head_style = ParagraphStyle("ReportHead", parent=cell_style, fontName=bold_font,
                                alignment=TA_CENTER)
    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    story = [Paragraph(str(title), title_style),
             Paragraph(f"{_('Period')}: {_period(date_from, date_to)} &nbsp; | &nbsp; "
                       f"{_('Generated')}: {generated}", meta_style)]
    table_data = [[Paragraph(str(value), head_style) for value in headers]]
    for row in rows:
        table_data.append([Paragraph(_pdf_text(value), cell_style) for value in row])
    page_width = landscape(A4)[0] - doc.leftMargin - doc.rightMargin
    column_width = page_width / max(len(headers), 1)
    table = Table(table_data, colWidths=[column_width] * len(headers), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#6c757d")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    def draw_page(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 12)
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 7 * mm, f"{_('Page')} {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return _response(buffer.getvalue(), kind, "pdf", date_from, date_to, "application/pdf")


def _pdf_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = _local_value(value).strftime("%d/%m/%Y %H:%M")
    elif isinstance(value, date):
        value = value.strftime("%d/%m/%Y")
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
