"""Receipt printing and PDF export routes."""
from decimal import Decimal
from flask import Blueprint, render_template, abort, make_response
from flask_login import login_required, current_user
from ..models import Sale, Tenant

bp = Blueprint("receipt", __name__)


@bp.route("/<int:sale_id>", methods=["GET"])
@login_required
def view_receipt(sale_id: int):
    from ..extensions import db
    tenant_id = current_user.tenant_id
    sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).first()
    if not sale:
        abort(404)
    tenant = db.session.get(Tenant, tenant_id)

    paid = (
        Decimal(sale.cash_amount or 0) +
        Decimal(sale.mpesa_amount or 0) +
        Decimal(sale.card_amount or 0)
    )
    change = max(Decimal("0"), paid - Decimal(sale.total or 0))
    currency = tenant.currency if tenant else "KES"

    return render_template(
        "receipt.html",
        sale=sale,
        tenant=tenant,
        paid=paid,
        change=change,
        currency=currency,
    )


@bp.route("/<int:sale_id>/pdf", methods=["GET"])
@login_required
def download_receipt_pdf(sale_id: int):
    """Generate a printable PDF receipt using ReportLab."""
    from reportlab.lib.pagesizes import A6
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from io import BytesIO
    from ..extensions import db

    tenant_id = current_user.tenant_id
    sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).first()
    if not sale:
        abort(404)
    tenant = db.session.get(Tenant, tenant_id)

    paid = (
        Decimal(sale.cash_amount or 0) +
        Decimal(sale.mpesa_amount or 0) +
        Decimal(sale.card_amount or 0)
    )
    change = max(Decimal("0"), paid - Decimal(sale.total or 0))
    currency = tenant.currency if tenant else "KES"

    buf = BytesIO()
    w, h = A6
    c = canvas.Canvas(buf, pagesize=A6)

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 20 * mm, tenant.name if tenant else "Enterprise POS")
    c.setFont("Helvetica", 9)
    if tenant and tenant.address:
        c.drawCentredString(w / 2, h - 26 * mm, tenant.address)
    if tenant and tenant.phone:
        c.drawCentredString(w / 2, h - 31 * mm, f"Tel: {tenant.phone}")

    # Invoice info
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, h - 40 * mm, f"Invoice: {sale.sale_number}")
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, h - 46 * mm, f"Date: {sale.created_at.strftime('%Y-%m-%d %H:%M')}")
    if sale.customer_id and sale.customer:
        c.drawString(10 * mm, h - 52 * mm, f"Customer: {sale.customer.name}")

    # Items
    y = h - 62 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y, "Item")
    c.drawRightString(w - 10 * mm, y, "Total")
    y -= 4 * mm
    c.line(10 * mm, y, w - 10 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica", 8)
    for item in sale.items:
        c.drawString(10 * mm, y, f"{item.name_snapshot} x{item.quantity}")
        c.drawRightString(w - 10 * mm, y, f"{currency} {float(item.line_total):,.2f}")
        y -= 5 * mm

    # Totals
    y -= 2 * mm
    c.line(10 * mm, y, w - 10 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, y, "Subtotal:")
    c.drawRightString(w - 10 * mm, y, f"{currency} {float(sale.subtotal):,.2f}")
    if sale.discount and float(sale.discount) > 0:
        y -= 5 * mm
        c.drawString(10 * mm, y, "Discount:")
        c.drawRightString(w - 10 * mm, y, f"-{currency} {float(sale.discount):,.2f}")
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, y, "TOTAL:")
    c.drawRightString(w - 10 * mm, y, f"{currency} {float(sale.total):,.2f}")

    # Payment
    y -= 7 * mm
    c.setFont("Helvetica", 8)
    if float(sale.cash_amount or 0) > 0:
        c.drawString(10 * mm, y, f"Cash: {currency} {float(sale.cash_amount):,.2f}")
        y -= 4 * mm
    if float(sale.mpesa_amount or 0) > 0:
        c.drawString(10 * mm, y, f"M-Pesa: {currency} {float(sale.mpesa_amount):,.2f}")
        y -= 4 * mm
    if float(sale.card_amount or 0) > 0:
        c.drawString(10 * mm, y, f"Card: {currency} {float(sale.card_amount):,.2f}")
        y -= 4 * mm
    if float(change) > 0:
        c.drawString(10 * mm, y, f"Change: {currency} {float(change):,.2f}")
        y -= 4 * mm

    # Footer
    y -= 6 * mm
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, y, "Thank you for your business!")
    c.drawCentredString(w / 2, y - 4 * mm, f"Status: {sale.payment_status.upper()}")

    c.save()
    buf.seek(0)

    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=receipt_{sale.sale_number}.pdf"
    return response
