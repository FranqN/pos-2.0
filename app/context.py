from flask import g
from flask_login import current_user

from .extensions import db
from .models import Tenant, Product


def get_tenant_context():
    if not current_user.is_authenticated:
        return {
            "tenant_name": None,
            "tenant_logo": None,
            "tenant_currency": "KES",
            "low_stock_count": 0,
        }
    tenant = db.session.get(Tenant, current_user.tenant_id)
    if not tenant:
        return {
            "tenant_name": None,
            "tenant_logo": None,
            "tenant_currency": "KES",
            "low_stock_count": 0,
        }

    # Count products at or below reorder level for the nav badge
    low_stock_count = Product.query.filter(
        Product.tenant_id == current_user.tenant_id,
        Product.active == True,
        Product.stock_on_hand <= Product.reorder_level,
    ).count()

    return {
        "tenant_name": tenant.name,
        "tenant_logo": tenant.logo_filename,
        "tenant_currency": tenant.currency or "KES",
        "low_stock_count": low_stock_count,
    }
