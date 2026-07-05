from __future__ import annotations
from datetime import datetime
from functools import wraps
from flask import abort
from flask_login import current_user


def make_sale_number(prefix: str = "INV") -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"


def role_required(*roles: str):
    """Decorator to restrict route access to specific user roles.
    Allowed roles: owner, manager, cashier, stock_manager, viewer
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

