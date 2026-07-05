from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import db
from ..models import User, Tenant, AuditLog

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        tenant_id_raw = request.form.get("tenant_id", "").strip()

        if not tenant_id_raw:
            flash("Select or create a tenant first.", "error")
            return redirect(url_for("tenant.create"))

        try:
            tenant_id = int(tenant_id_raw)
        except ValueError:
            flash("Invalid tenant selection.", "error")
            tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
            return render_template("login.html", tenants=tenants)

        user = (
            User.query.filter_by(tenant_id=tenant_id, email=email)
            .first()
        )
        if not user:
            flash("Account not found for selected store.", "error")
            tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
            return render_template("login.html", tenants=tenants)

        if not user.check_password(password):
            flash("Incorrect password.", "error")
            tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
            return render_template("login.html", tenants=tenants)


        login_user(user)

        # Track last login time
        user.last_login_at = datetime.utcnow()
        db.session.add(AuditLog(
            tenant_id=user.tenant_id,
            action="user_login",
            entity_type="User",
            entity_id=str(user.id),
            detail=f"User '{user.full_name}' ({user.role}) logged in.",
            created_by=user.id,
        ))
        db.session.commit()

        return redirect(url_for("analytics.home_dashboard"))

    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    return render_template("login.html", tenants=tenants)


@bp.route("/logout")
@login_required
def logout():
    if current_user.is_authenticated:
        try:
            db.session.add(AuditLog(
                tenant_id=current_user.tenant_id,
                action="user_logout",
                entity_type="User",
                entity_id=str(current_user.id),
                detail=f"User '{current_user.full_name}' logged out.",
                created_by=current_user.id,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
    logout_user()
    return redirect(url_for("auth.login"))
