"""Analytics API endpoints for Chart.js dashboard."""
from datetime import datetime, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from ..extensions import db
from ..models import Sale, SaleItem, Product
from ..utils import role_required

bp = Blueprint("analytics", __name__)


@bp.route("/revenue-trend", methods=["GET"])
@login_required
@role_required("owner", "manager")
def revenue_trend():
    """Last 30 days revenue per day."""
    tenant_id = current_user.tenant_id
    days = 30
    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.session.query(
            func.date(Sale.created_at).label("day"),
            func.coalesce(func.sum(Sale.total), 0).label("revenue")
        )
        .filter(Sale.tenant_id == tenant_id, Sale.status == "active", Sale.created_at >= cutoff)
        .group_by(func.date(Sale.created_at))
        .order_by(func.date(Sale.created_at).asc())
        .all()
    )

    labels = [str(r.day) for r in rows]
    data = [float(r.revenue) for r in rows]

    return jsonify({"labels": labels, "data": data})


@bp.route("/top-products", methods=["GET"])
@login_required
@role_required("owner", "manager")
def top_products():
    """Top 10 products by qty sold last 30 days."""
    tenant_id = current_user.tenant_id
    cutoff = datetime.utcnow() - timedelta(days=30)

    rows = (
        db.session.query(
            SaleItem.name_snapshot,
            func.sum(SaleItem.quantity).label("total_qty"),
            func.sum(SaleItem.line_total).label("total_revenue")
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.tenant_id == tenant_id, Sale.status == "active", Sale.created_at >= cutoff)
        .group_by(SaleItem.name_snapshot)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(10)
        .all()
    )

    return jsonify({
        "labels": [r.name_snapshot for r in rows],
        "qty": [int(r.total_qty) for r in rows],
        "revenue": [float(r.total_revenue) for r in rows],
    })


@bp.route("/payment-split", methods=["GET"])
@login_required
@role_required("owner", "manager")
def payment_split():
    """Total payment method split all time."""
    tenant_id = current_user.tenant_id
    row = (
        db.session.query(
            func.coalesce(func.sum(Sale.cash_amount), 0).label("cash"),
            func.coalesce(func.sum(Sale.mpesa_amount), 0).label("mpesa"),
            func.coalesce(func.sum(Sale.card_amount), 0).label("card"),
        )
        .filter(Sale.tenant_id == tenant_id, Sale.status == "active")
        .first()
    )

    return jsonify({
        "labels": ["Cash", "M-Pesa", "Card"],
        "data": [float(row.cash), float(row.mpesa), float(row.card)],
    })


@bp.route("/dashboard", methods=["GET"])
@login_required
@role_required("owner", "manager")
def analytics_dashboard():
    return render_template("analytics.html")


@bp.route("/dashboard-stats", methods=["GET"])
@login_required
@role_required("owner", "manager", "cashier")
def dashboard_stats():
    """KPIs for the home dashboard page."""
    tenant_id = current_user.tenant_id
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    def sales_sum(start, end):
        row = db.session.query(
            func.coalesce(func.sum(Sale.total), 0).label("total"),
            func.count(Sale.id).label("count")
        ).filter(
            Sale.tenant_id == tenant_id,
            Sale.status == "active",
            Sale.created_at >= start,
            Sale.created_at < end,
        ).first()
        return float(row.total), int(row.count)

    today_revenue, today_tx = sales_sum(today_start, datetime.utcnow())
    yesterday_revenue, yesterday_tx = sales_sum(yesterday_start, today_start)

    avg_order = (today_revenue / today_tx) if today_tx > 0 else 0

    # Top 5 products today
    top_products = (
        db.session.query(
            SaleItem.name_snapshot,
            func.sum(SaleItem.quantity).label("qty")
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.tenant_id == tenant_id,
            Sale.status == "active",
            Sale.created_at >= today_start,
        )
        .group_by(SaleItem.name_snapshot)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(5)
        .all()
    )

    # Profit today
    profit_today = Decimal("0")
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

    # Low stock count
    low_stock = Product.query.filter(
        Product.tenant_id == tenant_id,
        Product.active == True,
        Product.stock_on_hand <= Product.reorder_level
    ).count()

    return jsonify({
        "today_revenue": today_revenue,
        "yesterday_revenue": yesterday_revenue,
        "today_tx": today_tx,
        "yesterday_tx": yesterday_tx,
        "avg_order": round(avg_order, 2),
        "profit_today": float(profit_today),
        "low_stock": low_stock,
        "top_products": [{"name": r.name_snapshot, "qty": int(r.qty)} for r in top_products],
    })


@bp.route("/home", methods=["GET"])
@login_required
def home_dashboard():
    """Main home dashboard accessible to all roles."""
    return render_template("dashboard.html")
