from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from rest_framework import serializers

from apps.bookings.models import BookingStatus, PaymentStatus
from apps.payments.models import Invoice, InvoiceSequence


def _financial_year(day):
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


@transaction.atomic
def issue_invoice(booking):
    booking = type(booking).objects.select_for_update().select_related("customer", "customer__customer_profile", "service").get(id=booking.id)
    existing = Invoice.objects.filter(booking=booking).first()
    if existing:
        return existing
    if booking.payment_status != PaymentStatus.PAID and booking.booking_status != BookingStatus.COMPLETED:
        raise serializers.ValidationError("Invoice is available after full payment or service completion.")

    issued_at = timezone.now()
    financial_year = _financial_year(issued_at.date())
    sequence, _ = InvoiceSequence.objects.select_for_update().get_or_create(financial_year=financial_year)
    sequence.current_number += 1
    sequence.save(update_fields=["current_number"])
    tax = booking.tax_amount or Decimal("0.00")
    cgst = (tax / 2).quantize(Decimal("0.01"))
    profile = getattr(booking.customer, "customer_profile", None)
    customer_name = (getattr(profile, "display_name", "") or "").strip() or " ".join(
        part for part in (booking.customer.first_name, booking.customer.last_name) if part
    ).strip() or booking.customer.phone_number
    return Invoice.objects.create(
        booking=booking,
        invoice_number=f"PS/{financial_year}/{sequence.current_number:06d}",
        financial_year=financial_year,
        seller_name=settings.BUSINESS_LEGAL_NAME,
        seller_gstin=settings.BUSINESS_GSTIN,
        seller_address=settings.BUSINESS_ADDRESS,
        customer_name=customer_name,
        customer_phone=booking.customer.phone_number,
        taxable_value=booking.subtotal - booking.discount_amount,
        cgst_amount=cgst,
        sgst_amount=tax - cgst,
        total_amount=booking.total_amount,
        issued_at=issued_at,
    )


def render_invoice_pdf(invoice):
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    width, height = A4
    document_title = "TAX INVOICE" if invoice.seller_gstin else "PAYMENT RECEIPT"
    document.setTitle(f"{document_title.title()} {invoice.invoice_number}")
    document.setFont("Helvetica-Bold", 20)
    document.drawString(48, height - 58, document_title)
    document.setFont("Helvetica-Bold", 13)
    document.drawString(48, height - 88, invoice.seller_name)
    document.setFont("Helvetica", 9)
    document.drawString(48, height - 104, invoice.seller_address[:90])
    if invoice.seller_gstin:
        document.drawString(48, height - 120, f"GSTIN: {invoice.seller_gstin}")
    document.drawRightString(width - 48, height - 88, invoice.invoice_number)
    document.drawRightString(width - 48, height - 104, invoice.issued_at.strftime("%d %b %Y"))

    document.line(48, height - 140, width - 48, height - 140)
    document.setFont("Helvetica-Bold", 10)
    document.drawString(48, height - 165, "Billed to")
    document.setFont("Helvetica", 10)
    document.drawString(48, height - 182, invoice.customer_name)
    document.drawString(48, height - 198, invoice.customer_phone)
    document.drawString(48, height - 214, f"Booking: {invoice.booking.booking_number}")

    y = height - 255
    document.setFont("Helvetica-Bold", 10)
    document.drawString(48, y, "Service")
    document.drawRightString(width - 48, y, "Amount")
    document.line(48, y - 8, width - 48, y - 8)
    document.setFont("Helvetica", 10)
    document.drawString(48, y - 30, invoice.booking.service.name[:70])
    document.drawRightString(width - 48, y - 30, f"INR {invoice.taxable_value:.2f}")
    totals = [
        ("CGST", invoice.cgst_amount),
        ("SGST", invoice.sgst_amount),
        ("IGST", invoice.igst_amount),
        ("Total", invoice.total_amount),
    ]
    totals_y = y - 70
    for label, amount in totals:
        document.setFont("Helvetica-Bold" if label == "Total" else "Helvetica", 10)
        document.drawRightString(width - 140, totals_y, label)
        document.drawRightString(width - 48, totals_y, f"INR {amount:.2f}")
        totals_y -= 18
    document.setFont("Helvetica", 8)
    document.drawString(48, 48, "Computer-generated invoice. No signature is required.")
    document.showPage()
    document.save()
    return output.getvalue()
