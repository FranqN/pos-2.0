import csv
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from flask import Blueprint, render_template, request, Response
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db
from ..models import Sale, Product, User, AuditLog, Tenant
from ..utils import role_required

bp = Blueprint("reports", __name__)


@bp.route("/daily", methods=["GET"])
@login_required
@role_required("owner", "manager")
def daily_report():
    tenant_id = current_user.tenant_id

    # Filter params for Sales History
    date_filter = request.args.get("date_filter", "")
    cashier_filter = request.args.get("cashier_filter", "")
    status_filter = request.args.get("status_filter", "")

    # Base query for today's metrics
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Summary Metrics (Active Sales only)
    active_sales_today = Sale.query.filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= today_start,
        Sale.status == "active"
    )

    total_sales = active_sales_today.with_entities(func.coalesce(func.sum(Sale.total), 0)).scalar()
    tx_count = active_sales_today.count()

    # Voids/Refunds count today
    reverted_count = Sale.query.filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= today_start,
        Sale.status.in_(["voided", "refunded"])
    ).count()

    # Payment split today
    payment_splits = active_sales_today.with_entities(
        func.coalesce(func.sum(Sale.cash_amount), 0).label("cash"),
        func.coalesce(func.sum(Sale.mpesa_amount), 0).label("mpesa"),
        func.coalesce(func.sum(Sale.card_amount), 0).label("card")
    ).first()

    cash_total = payment_splits.cash if payment_splits else 0
    mpesa_total = payment_splits.mpesa if payment_splits else 0
    card_total = payment_splits.card if payment_splits else 0

    # VAT collected today (if VAT enabled)
    tenant = db.session.get(Tenant, tenant_id)
    vat_total = Decimal("0.00")
    if tenant and tenant.vat_enabled and tenant.vat_rate > 0:
        # total contains VAT. VAT = total - (total / (1 + rate/100))
        rate_factor = Decimal("1.00") + (Decimal(tenant.vat_rate) / Decimal("100.00"))
        vat_total = Decimal(total_sales) - (Decimal(total_sales) / rate_factor)

    # Cashier breakdown today
    cashier_breakdown = (
        db.session.query(User.full_name, func.coalesce(func.sum(Sale.total), 0).label("sales_sum"))
        .join(Sale, Sale.created_by == User.id)
        .filter(Sale.tenant_id == tenant_id, Sale.created_at >= today_start, Sale.status == "active")
        .group_by(User.full_name)
        .all()
    )

    # Top product stock status (low stock list)
    low_stock_products = (
        Product.query.filter(Product.tenant_id == tenant_id, Product.active == True)
        .filter(Product.stock_on_hand <= Product.reorder_level)
        .order_by(Product.stock_on_hand.asc())
        .limit(5)
        .all()
    )

    # Sales history with filters + pagination
    history_query = Sale.query.filter(Sale.tenant_id == tenant_id)

    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d")
            history_query = history_query.filter(
                Sale.created_at >= target_date,
                Sale.created_at < target_date + timedelta(days=1)
            )
        except ValueError:
            pass
    if cashier_filter:
        history_query = history_query.join(User, Sale.created_by == User.id).filter(
            User.full_name.ilike(f"%{cashier_filter}%")
        )
    if status_filter:
        history_query = history_query.filter(Sale.status == status_filter)

    page = request.args.get("page", 1, type=int)
    per_page = 25
    total_history = history_query.count()
    sales_history = history_query.order_by(Sale.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total_history + per_page - 1) // per_page)

    # Cashier list for dropdown filters
    cashiers = User.query.filter_by(tenant_id=tenant_id).all()

    # System audit logs
    audit_logs = (
        AuditLog.query.filter_by(tenant_id=tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    from ..services.ai_service import ai_anomaly_detection
    anomalies = ai_anomaly_detection(tenant_id)

    # Profit calculation for today's active sales
    profit_today = Decimal("0.00")
    for sale in Sale.query.filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= today_start,
        Sale.status == "active"
    ).all():
        for item in sale.items:
            product = db.session.get(Product, item.product_id)
            if product:
                cost = Decimal(str(product.cost or 0))
                profit_today += (Decimal(str(item.unit_price)) - cost) * item.quantity

    return render_template(
        "daily_report.html",
        total_sales=total_sales,
        tx_count=tx_count,
        reverted_count=reverted_count,
        cash_total=cash_total,
        mpesa_total=mpesa_total,
        card_total=card_total,
        vat_total=vat_total,
        cashier_breakdown=cashier_breakdown,
        low_stock_products=low_stock_products,
        sales_history=sales_history,
        cashiers=cashiers,
        audit_logs=audit_logs,
        anomalies=anomalies,
        date_filter=date_filter,
        cashier_filter=cashier_filter,
        status_filter=status_filter,
        profit_today=profit_today,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        total_history=total_history,
    )


@bp.route("/export-csv", methods=["GET"])
@login_required
@role_required("owner", "manager")
def export_csv():
    tenant_id = current_user.tenant_id
    sales = Sale.query.filter_by(tenant_id=tenant_id).order_by(Sale.created_at.desc()).all()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow([
        "Invoice Number", "Date", "Customer", "Subtotal", "Discount", "Total",
        "Payment Status", "Cash Paid", "M-Pesa Paid", "Card Paid", "Status"
    ])

    for s in sales:
        cust_name = s.customer.name if s.customer else "Walk-in"
        cw.writerow([
            s.sale_number,
            s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            cust_name,
            s.subtotal,
            s.discount,
            s.total,
            s.payment_status,
            s.cash_amount,
            s.mpesa_amount,
            s.card_amount,
            s.status
        ])

    response = Response(si.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=sales_history_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return response


