"""Receipt views: HTML display + PDF download."""
import io
import logging
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect

logger = logging.getLogger(__name__)


def _get_school(request):
    school = getattr(request.user, "school", None)
    if school:
        return school
    if request.user.is_superuser or getattr(request.user, "is_super_admin", False):
        from schools.models import School
        sid = request.session.get("current_school_id")
        if sid:
            return School.objects.filter(pk=sid).first()
    return None


def _get_payment(pk, user, school):
    """Find payment across FeePayment / StudentPayment models."""
    from django.apps import apps
    for model_name in ("FeePayment", "StudentPayment", "Payment"):
        try:
            Model = apps.get_model("finance", model_name)
            obj = Model.objects.filter(pk=pk).first()
            if obj:
                return obj
        except Exception:
            pass
    for model_name in ("FeePayment", "StudentPayment", "Payment"):
        try:
            Model = apps.get_model("operations", model_name)
            obj = Model.objects.filter(pk=pk).first()
            if obj:
                return obj
        except Exception:
            pass
    return None


@login_required
def receipt_view(request, payment_id):
    """HTML receipt page."""
    school = _get_school(request)
    payment = _get_payment(payment_id, request.user, school)
    if not payment:
        from django.http import Http404
        raise Http404("Payment not found")
    return render(request, "operations/receipt.html", {"payment": payment, "school": school})


@login_required
def receipt_pdf_view(request, payment_id):
    """Download PDF receipt."""
    school = _get_school(request)
    payment = _get_payment(payment_id, request.user, school)
    if not payment:
        return HttpResponse("Payment not found", status=404)

    try:
        pdf_bytes = _build_receipt_pdf(payment, school)
    except Exception as exc:
        logger.exception("Receipt PDF failed for payment %s: %s", payment_id, exc)
        return HttpResponse(f"PDF generation failed: {exc}", status=500, content_type="text/plain")

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt_{payment_id}.pdf"'
    return response


def _build_receipt_pdf(payment, school):
    """Build PDF bytes for a payment receipt."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5,
                             rightMargin=1.5*cm, leftMargin=1.5*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("N", parent=styles["Normal"], fontSize=9, leading=13)
    center = ParagraphStyle("C", parent=normal, alignment=TA_CENTER)
    heading = ParagraphStyle("H", parent=styles["Heading2"], fontSize=12,
                              textColor=colors.HexColor("#1e3a5f"), alignment=TA_CENTER)

    school_name = school.name if school else "School"
    elements = []
    elements.append(Paragraph(school_name.upper(), heading))
    if school and school.address:
        elements.append(Paragraph(school.address, center))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1e3a5f")))
    elements.append(Paragraph("OFFICIAL RECEIPT", ParagraphStyle("RC", parent=heading, fontSize=11,
                               spaceAfter=4, spaceBefore=4)))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 8))

    # Details grid
    currency = school.currency if school and hasattr(school, "currency") and school.currency else "GHS"
    student_name = ""
    if hasattr(payment, "student") and payment.student:
        student_name = payment.student.user.get_full_name() or str(payment.student)

    fee_type = ""
    if hasattr(payment, "get_fee_type_display"):
        try:
            fee_type = payment.get_fee_type_display()
        except Exception:
            fee_type = getattr(payment, "fee_type", "")

    paid_at = getattr(payment, "paid_at", None) or getattr(payment, "created_at", None)
    paid_at_str = paid_at.strftime("%d %b %Y %H:%M") if paid_at else "N/A"

    info = [
        ["Receipt No.:", f"#{payment.id}", "Date:", paid_at_str],
        ["Student:", student_name, "Fee Type:", fee_type],
    ]
    info_table = Table(info, colWidths=[2.5*cm, 4*cm, 2.5*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#1e3a5f")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f7f9fc"), colors.white]),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10))

    # Amount
    amount = float(getattr(payment, "amount", 0) or 0)
    amount_data = [
        [Paragraph("<b>Description</b>", normal), Paragraph("<b>Amount</b>", normal)],
        [Paragraph(fee_type or "Payment", normal), Paragraph(f"<b>{currency} {amount:,.2f}</b>",
              ParagraphStyle("Amt", parent=normal, fontSize=11, textColor=colors.HexColor("#1e3a5f")))],
    ]
    amount_table = Table(amount_data, colWidths=[8*cm, 5*cm])
    amount_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4f8")]),
    ]))
    elements.append(amount_table)
    elements.append(Spacer(1, 10))

    # Status
    status = getattr(payment, "status", "paid")
    status_color = colors.HexColor("#16a34a") if status == "paid" else colors.HexColor("#ca8a04")
    status_text = "PAYMENT CONFIRMED" if status == "paid" else "PENDING"
    elements.append(Paragraph(f"✓ {status_text}", ParagraphStyle(
        "ST", parent=center, fontSize=11, textColor=status_color, spaceBefore=4
    )))

    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    from datetime import date
    elements.append(Paragraph(
        f"Thank you for your payment. Official receipt from {school_name}. "
        f"Generated {date.today().strftime('%d %b %Y')} by Mastex SchoolOS.",
        ParagraphStyle("FT", parent=center, fontSize=7.5, textColor=colors.HexColor("#aaaaaa"), spaceBefore=4)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
