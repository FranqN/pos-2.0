"""Customer routes: list, create, edit, history, settle balance."""
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Customer, Sale, AuditLog, StockMovement
from ..utils import role_required

bp = Blueprint("customers", __name__)


@bp.route("/", methods=["GET"])
@login_required
def list_customers():
    search = request.args.get("q", "").strip()
    q = Customer.query.filter_by(tenant_id=current_user.tenant_id)
    if search:
        q = q.filter(
            (Customer.name.ilike(f"%{search}%")) |
            (Customer.phone.ilike(f"%{search}%"))
        )
    customers = q.order_by(Customer.name.asc()).all()
    return render_template("customers.html", customers=customers, search=search)


@bp.route("/new", methods=["POST"])
@login_required
def create_customer():
    tenant_id = current_user.tenant_id
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip() or None
    email = request.form.get("email", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    credit_limit_raw = request.form.get("credit_limit", "0").strip() or "0"

    if not name:
        flash("Customer name required.", "error")
        return redirect(url_for("customers.list_customers"))

    try:
        credit_limit = Decimal(credit_limit_raw)
    except Exception:
        credit_limit = Decimal("0")

    c = Customer(
        tenant_id=tenant_id,
        name=name,
        phone=phone,
        email=email,
        notes=notes,
        credit_limit=credit_limit,
    )
    db.session.add(c)
    db.session.commit()

    flash(f"Customer '{name}' added.", "success")
    return redirect(url_for("customers.list_customers"))


@bp.route("/<int:customer_id>/edit", methods=["POST"])
@login_required
def edit_customer(customer_id: int):
    tenant_id = current_user.tenant_id
    c = Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).first()
    if not c:
        flash("Customer not found.", "error")
        return redirect(url_for("customers.list_customers"))

    c.name = request.form.get("name", c.name).strip()
    c.phone = request.form.get("phone", "").strip() or None
    c.email = request.form.get("email", "").strip() or None
    c.notes = request.form.get("notes", "").strip() or None
    try:
        c.credit_limit = Decimal(request.form.get("credit_limit", "0") or "0")
    except Exception:
        pass

    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="customer_edit",
        entity_type="Customer",
        entity_id=str(c.id),
        detail=f"Customer '{c.name}' updated.",
        created_by=current_user.id,
    ))
    db.session.commit()
    flash(f"Customer '{c.name}' updated.", "success")
    return redirect(url_for("customers.list_customers"))


@bp.route("/<int:customer_id>/history", methods=["GET"])
@login_required
def customer_history(customer_id: int):
    tenant_id = current_user.tenant_id
    c = Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).first()
    if not c:
        flash("Customer not found.", "error")
        return redirect(url_for("customers.list_customers"))

    sales = (
        Sale.query.filter_by(tenant_id=tenant_id, customer_id=customer_id)
        .order_by(Sale.created_at.desc()).all()
    )
    total_spent = sum(Decimal(s.total or 0) for s in sales if s.status == "active")
    return render_template(
        "customer_history.html",
        customer=c,
        sales=sales,
        total_spent=total_spent,
    )


@bp.route("/<int:customer_id>/settle", methods=["POST"])
@login_required
def settle_balance(customer_id: int):
    tenant_id = current_user.tenant_id
    c = Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).with_for_update().first()
    if not c:
        flash("Customer not found.", "error")
        return redirect(url_for("customers.list_customers"))

    try:
        amount_raw = request.form.get("amount", "0").strip()
        amount = Decimal(amount_raw)
        if amount <= 0:
            raise ValueError("Settlement amount must be positive.")

        old_balance = Decimal(c.balance or 0)
        c.balance = max(Decimal("0"), old_balance - amount)

        db.session.add(AuditLog(
            tenant_id=tenant_id,
            action="customer_balance_settle",
            entity_type="Customer",
            entity_id=str(c.id),
            detail=f"Balance settled by KES {amount:,.2f}. Old: {old_balance:,.2f}, New: {c.balance:,.2f}",
            created_by=current_user.id,
        ))
        db.session.commit()
        flash(f"KES {amount:,.2f} settled for {c.name}. Remaining balance: KES {c.balance:,.2f}", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("customers.customer_history", customer_id=customer_id))


@bp.route("/<int:customer_id>/delete", methods=["POST"])
@login_required
@role_required("owner", "manager")
def delete_customer(customer_id: int):
    tenant_id = current_user.tenant_id
    c = Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).first()
    if not c:
        flash("Customer not found.", "error")
        return redirect(url_for("customers.list_customers"))
    name = c.name
    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="customer_delete",
        entity_type="Customer",
        entity_id=str(c.id),
        detail=f"Customer '{name}' deleted.",
        created_by=current_user.id,
    ))
    db.session.delete(c)
    db.session.commit()
    flash(f"Customer '{name}' deleted.", "success")
    return redirect(url_for("customers.list_customers"))
