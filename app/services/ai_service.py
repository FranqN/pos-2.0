from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import Product, Sale, SaleItem, StockMovement, User


def ai_reorder_suggestions(tenant_id: int, limit: int = 8):
    """Deterministic reorder suggestions based on stock levels and 14-day sales velocity."""
    low = Product.query.filter(
        Product.tenant_id == tenant_id,
        Product.active == True,
        Product.stock_on_hand <= Product.reorder_level
    ).all()

    # 14 days window
    cutoff = datetime.utcnow() - timedelta(days=14)

    # Calculate actual quantity sold per product in last 14 days
    sales_data = (
        db.session.query(SaleItem.product_id, func.sum(SaleItem.quantity).label("total_qty"))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.tenant_id == tenant_id,
            Sale.status == "active",
            Sale.created_at >= cutoff
        )
        .group_by(SaleItem.product_id)
        .all()
    )

    velocity = {pid: float(qty) / 14.0 for pid, qty in sales_data}

    suggestions = []
    for p in low:
        v = velocity.get(p.id, 0.0)
        # Suggest bringing stock back to reorder_level + 10, scaled by the 14-day daily velocity (e.g. 7 days of supply)
        recommended = max(int(p.reorder_level) + 10, int(v * 7.0) + 1)
        suggestions.append({
            "product_id": p.id,
            "name": p.name,
            "stock": p.stock_on_hand,
            "reorder_level": p.reorder_level,
            "recommended": recommended,
            "unit_price": str(p.price),
            "velocity": round(v, 2),
            "why": f"Stock ({p.stock_on_hand}) <= reorder level ({p.reorder_level}). Daily velocity: {v:.2f} units/day."
        })

    return suggestions[:limit]


def ai_anomaly_detection(tenant_id: int) -> list[dict]:
    """Detects unusual system events or business metrics in the last 24 hours."""
    anomalies = []
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)

    # 1. High discount alerts (>20% of subtotal)
    high_discounts = Sale.query.filter(
        Sale.tenant_id == tenant_id,
        Sale.status == "active",
        Sale.created_at >= cutoff_24h,
        Sale.discount > 0
    ).all()

    for sale in high_discounts:
        if sale.subtotal > 0 and (sale.discount / sale.subtotal) > Decimal("0.20"):
            pct = int((sale.discount / sale.subtotal) * 100)
            cashier = db.session.get(User, sale.created_by)
            cashier_name = cashier.full_name if cashier else "Unknown"
            anomalies.append({
                "type": "high_discount",
                "severity": "warning",
                "message": f"Invoice {sale.sale_number} has a high discount of {pct}% (KES {sale.discount}) applied by {cashier_name}."
            })

    # 2. Cashier refund/void spikes (more than 2 in the last 24h)
    reverted_sales = db.session.query(
        Sale.created_by,
        func.count(Sale.id).label("cnt")
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.status.in_(["voided", "refunded"]),
        Sale.created_at >= cutoff_24h
    ).group_by(Sale.created_by).all()

    for cashier_id, count in reverted_sales:
        if count >= 2:
            cashier = db.session.get(User, cashier_id)
            cashier_name = cashier.full_name if cashier else "Unknown"
            anomalies.append({
                "type": "refund_spike",
                "severity": "danger",
                "message": f"Cashier {cashier_name} performed {count} voids/refunds in the last 24 hours (Threshold: 2)."
            })

    # 3. Large negative stock adjustments
    neg_adjustments = StockMovement.query.filter(
        StockMovement.tenant_id == tenant_id,
        StockMovement.movement_type == "adjustment",
        StockMovement.quantity_delta < -5,
        StockMovement.created_at >= cutoff_24h
    ).all()

    for move in neg_adjustments:
        prod = db.session.get(Product, move.product_id)
        prod_name = prod.name if prod else "Unknown Product"
        cashier = db.session.get(User, move.created_by)
        cashier_name = cashier.full_name if cashier else "Unknown"
        anomalies.append({
            "type": "negative_adjustment",
            "severity": "warning",
            "message": f"Large negative stock adjustment of {move.quantity_delta} for '{prod_name}' by {cashier_name}."
        })

    return anomalies

