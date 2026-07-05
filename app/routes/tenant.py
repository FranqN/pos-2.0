import os
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Tenant, User
from ..utils import role_required

bp = Blueprint("tenant", __name__)


@bp.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        address = request.form.get("address", "").strip()

        admin_email = request.form.get("admin_email", "").strip().lower()
        admin_password = request.form.get("admin_password", "")

        logo = request.files.get("logo")
        logo_filename = None

        if not name:
            flash("Business name is required.", "error")
            return render_template("tenant_create.html")
        if not admin_email or not admin_password:
            flash("Admin email and password are required.", "error")
            return render_template("tenant_create.html")

        tenant = Tenant(name=name, phone=phone, email=email, address=address)
        db.session.add(tenant)
        db.session.flush()  # get tenant.id

        if logo and logo.filename:
            os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
            filename = secure_filename(logo.filename)
            # simple unique name
            filename = f"tenant_{tenant.id}_{filename}"
            logo.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
            tenant.logo_filename = filename

        try:
            admin = User(tenant_id=tenant.id, email=admin_email, full_name="Owner", role="owner")
            admin.set_password(admin_password)
            db.session.add(admin)

            # Persist logo + tenant + admin in a single transaction.
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to create store. Please try again.", "error")
            return render_template("tenant_create.html")

        flash("Tenant created. Please login.", "success")
        return redirect(url_for("auth.login"))


    return render_template("tenant_create.html")


@bp.route("/dashboard", methods=["GET", "POST"])
@login_required
@role_required("owner", "manager")
def dashboard():
    from decimal import Decimal
    from ..models import AuditLog

    tenant_id = current_user.tenant_id
    tenant = db.session.get(Tenant, tenant_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        address = request.form.get("address", "").strip()
        currency = request.form.get("currency", "KES").strip()

        vat_enabled = request.form.get("vat_enabled") == "y"
        vat_rate_raw = request.form.get("vat_rate", "0")
        try:
            vat_rate = Decimal(vat_rate_raw or "0")
        except Exception:
            vat_rate = Decimal("0")

        # Save M-Pesa Settings
        mpesa_simulate = request.form.get("mpesa_simulate") == "y"
        mpesa_shortcode = request.form.get("mpesa_shortcode", "").strip() or None
        mpesa_consumer_key = request.form.get("mpesa_consumer_key", "").strip() or None
        mpesa_consumer_secret = request.form.get("mpesa_consumer_secret", "").strip() or None
        mpesa_passkey = request.form.get("mpesa_passkey", "").strip() or None

        logo = request.files.get("logo")

        if not name:
            flash("Business name is required.", "error")
            return redirect(url_for("tenant.dashboard"))

        tenant.name = name
        tenant.phone = phone
        tenant.email = email
        tenant.address = address
        tenant.currency = currency
        tenant.vat_enabled = vat_enabled
        tenant.vat_rate = vat_rate
        
        tenant.mpesa_simulate = mpesa_simulate
        tenant.mpesa_shortcode = mpesa_shortcode
        tenant.mpesa_consumer_key = mpesa_consumer_key
        tenant.mpesa_consumer_secret = mpesa_consumer_secret
        tenant.mpesa_passkey = mpesa_passkey

        if logo and logo.filename:
            os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
            filename = secure_filename(logo.filename)
            filename = f"tenant_{tenant.id}_{filename}"
            logo.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
            tenant.logo_filename = filename

        db.session.add(AuditLog(
            tenant_id=tenant_id,
            action="tenant_settings_update",
            entity_type="Tenant",
            entity_id=str(tenant.id),
            detail="Business settings, VAT, and M-Pesa configurations updated.",
            created_by=current_user.id
        ))

        db.session.commit()
        flash("Store settings updated successfully.", "success")
        return redirect(url_for("tenant.dashboard"))

    users = User.query.filter_by(tenant_id=tenant_id).order_by(User.full_name.asc()).all()
    audit_logs = AuditLog.query.filter_by(tenant_id=tenant_id).order_by(AuditLog.created_at.desc()).limit(20).all()

    return render_template("tenant_dashboard.html", tenant=tenant, users=users, audit_logs=audit_logs)


@bp.route("/users/new", methods=["POST"])
@login_required
@role_required("owner", "manager")
def create_user():
    from ..models import AuditLog
    tenant_id = current_user.tenant_id
    email = request.form.get("email", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "cashier").strip()

    if not email or not password or not full_name:
        flash("All staff details are required.", "error")
        return redirect(url_for("tenant.dashboard"))

    existing = User.query.filter_by(tenant_id=tenant_id, email=email).first()
    if existing:
        flash("Staff member with this email already exists.", "error")
        return redirect(url_for("tenant.dashboard"))

    user = User(
        tenant_id=tenant_id,
        email=email,
        full_name=full_name,
        role=role
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="user_create",
        entity_type="User",
        entity_id=str(user.id),
        detail=f"Staff account '{full_name}' ({role}) created.",
        created_by=current_user.id
    ))

    db.session.commit()
    flash(f"Staff account '{full_name}' added successfully.", "success")
    return redirect(url_for("tenant.dashboard"))


@bp.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@role_required("owner")
def delete_user(user_id: int):
    from ..models import AuditLog
    tenant_id = current_user.tenant_id
    user = User.query.filter_by(id=user_id, tenant_id=tenant_id).first()

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("tenant.dashboard"))

    if user.id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("tenant.dashboard"))

    if user.role == "owner" and current_user.role != "owner":
        flash("Unauthorized to delete another owner account.", "error")
        return redirect(url_for("tenant.dashboard"))

    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="user_delete",
        entity_type="User",
        entity_id=str(user.id),
        detail=f"Staff account '{user.full_name}' ({user.role}) deleted.",
        created_by=current_user.id
    ))

    db.session.delete(user)
    db.session.commit()

    flash("Staff account deleted.", "success")
    return redirect(url_for("tenant.dashboard"))


