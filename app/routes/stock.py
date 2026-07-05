"""Stock management routes: adjustments, purchases, suppliers."""
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Product, StockMovement, Supplier, Purchase, PurchaseItem, AuditLog
from ..utils import role_required

bp = Blueprint("stock", __name__)


# ───────────────────────── Stock Adjustments ──────────────────────────

@bp.route("/adjustments", methods=["GET"])
@login_required
@role_required("owner", "manager", "stock_manager")
def adjustments():
    tenant_id = current_user.tenant_id
    products = (
        Product.query.filter_by(tenant_id=tenant_id, active=True)
        .order_by(Product.name.asc()).all()
    )
    recent_movements = (
        StockMovement.query
        .filter_by(tenant_id=tenant_id)
        .filter(StockMovement.movement_type == "adjustment")
        .order_by(StockMovement.created_at.desc())
        .limit(30).all()
    )
    return render_template(
        "stock_adjustments.html",
        products=products,
        recent_movements=recent_movements,
    )


@bp.route("/adjustments/apply", methods=["POST"])
@login_required
@role_required("owner", "manager", "stock_manager")
def apply_adjustment():
    tenant_id = current_user.tenant_id
    product_id = request.form.get("product_id", type=int)
    delta = request.form.get("quantity_delta", type=int)
    notes = request.form.get("notes", "").strip() or "Manual stock adjustment"

    if not product_id or delta is None:
        flash("Product and quantity delta are required.", "error")
        return redirect(url_for("stock.adjustments"))

    try:
        product = Product.query.filter_by(id=product_id, tenant_id=tenant_id).with_for_update().first()
        if not product:
            raise ValueError("Product not found.")
        new_stock = int(product.stock_on_hand) + delta
        if new_stock < 0:
            raise ValueError(f"Adjustment would result in negative stock ({new_stock}). Current: {product.stock_on_hand}")

        product.stock_on_hand = new_stock

        db.session.add(StockMovement(
            tenant_id=tenant_id,
            product_id=product.id,
            movement_type="adjustment",
            quantity_delta=delta,
            notes=notes,
            created_by=current_user.id,
        ))
        db.session.add(AuditLog(
            tenant_id=tenant_id,
            action="stock_adjustment",
            entity_type="Product",
            entity_id=str(product.id),
            detail=f"Adjusted '{product.name}' by {delta:+d}. New stock: {new_stock}. Note: {notes}",
            created_by=current_user.id,
        ))
        db.session.commit()
        flash(f"Stock adjusted for '{product.name}'. New stock: {new_stock}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("stock.adjustments"))


# ───────────────────────── Suppliers ──────────────────────────

@bp.route("/suppliers", methods=["GET"])
@login_required
@role_required("owner", "manager", "stock_manager")
def suppliers():
    tenant_id = current_user.tenant_id
    all_suppliers = Supplier.query.filter_by(tenant_id=tenant_id).order_by(Supplier.name.asc()).all()
    return render_template("suppliers.html", suppliers=all_suppliers)


@bp.route("/suppliers/new", methods=["POST"])
@login_required
@role_required("owner", "manager", "stock_manager")
def create_supplier():
    tenant_id = current_user.tenant_id
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip() or None
    email = request.form.get("email", "").strip() or None
    contact_person = request.form.get("contact_person", "").strip() or None

    if not name:
        flash("Supplier name is required.", "error")
        return redirect(url_for("stock.suppliers"))

    s = Supplier(tenant_id=tenant_id, name=name, phone=phone, email=email, contact_person=contact_person)
    db.session.add(s)
    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="supplier_create",
        entity_type="Supplier",
        entity_id="new",
        detail=f"Supplier '{name}' created.",
        created_by=current_user.id,
    ))
    db.session.commit()
    flash(f"Supplier '{name}' added.", "success")
    return redirect(url_for("stock.suppliers"))


@bp.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
@login_required
@role_required("owner", "manager")
def delete_supplier(supplier_id: int):
    tenant_id = current_user.tenant_id
    s = Supplier.query.filter_by(id=supplier_id, tenant_id=tenant_id).first()
    if not s:
        flash("Supplier not found.", "error")
        return redirect(url_for("stock.suppliers"))
    db.session.delete(s)
    db.session.commit()
    flash("Supplier deleted.", "success")
    return redirect(url_for("stock.suppliers"))


# ───────────────────────── Purchases ──────────────────────────

@bp.route("/purchases", methods=["GET"])
@login_required
@role_required("owner", "manager", "stock_manager")
def purchases():
    tenant_id = current_user.tenant_id
    all_purchases = (
        Purchase.query.filter_by(tenant_id=tenant_id)
        .order_by(Purchase.created_at.desc()).limit(100).all()
    )
    suppliers = Supplier.query.filter_by(tenant_id=tenant_id).order_by(Supplier.name.asc()).all()
    products = Product.query.filter_by(tenant_id=tenant_id, active=True).order_by(Product.name.asc()).all()
    return render_template("purchases.html", purchases=all_purchases, suppliers=suppliers, products=products)


@bp.route("/purchases/new", methods=["POST"])
@login_required
@role_required("owner", "manager", "stock_manager")
def create_purchase():
    tenant_id = current_user.tenant_id
    supplier_id_raw = request.form.get("supplier_id")
    supplier_id = int(supplier_id_raw) if supplier_id_raw else None
    ref_number = request.form.get("ref_number", "").strip() or None

    # Parse line items
    lines = []
    i = 0
    while True:
        pid = request.form.get(f"product_id_{i}")
        qty = request.form.get(f"qty_{i}")
        cost = request.form.get(f"unit_cost_{i}")
        if not pid:
            break
        if pid and qty and cost:
            try:
                lines.append((int(pid), int(qty), Decimal(cost)))
            except (ValueError, Exception):
                pass
        i += 1

    if not lines:
        flash("No valid line items. Please add at least one product.", "error")
        return redirect(url_for("stock.purchases"))

    try:
        # Use tenant lock to safely generate sequential purchase number
        from ..models import Tenant
        tenant = Tenant.query.filter_by(id=tenant_id).with_for_update().first()
        if not tenant:
            raise ValueError("Tenant not found.")
        purchase_number = ref_number if ref_number else f"PO-{tenant.next_sale_sequence:05d}"
        # We do NOT increment next_sale_sequence for purchases — use a separate approach
        # Use timestamp-based unique suffix to avoid collision
        if not ref_number:
            from datetime import datetime as _dt
            purchase_number = f"PO-{_dt.utcnow().strftime('%Y%m%d%H%M%S')}"

        purchase = Purchase(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            purchase_number=purchase_number,
            total=Decimal("0"),
            created_by=current_user.id,
        )
        db.session.add(purchase)
        db.session.flush()

        total = Decimal("0")
        for pid, qty, unit_cost in lines:
            product = Product.query.filter_by(id=pid, tenant_id=tenant_id).with_for_update().first()
            if not product:
                raise ValueError(f"Product ID {pid} not found.")
            line_total = unit_cost * qty
            total += line_total

            db.session.add(PurchaseItem(
                purchase_id=purchase.id,
                product_id=pid,
                quantity=qty,
                unit_cost=unit_cost,
                line_total=line_total,
            ))

            # Increment stock
            product.stock_on_hand = int(product.stock_on_hand) + qty
            db.session.add(StockMovement(
                tenant_id=tenant_id,
                product_id=pid,
                movement_type="purchase",
                quantity_delta=qty,
                notes=f"Purchase {purchase_number}",
                created_by=current_user.id,
            ))

        purchase.total = total

        db.session.add(AuditLog(
            tenant_id=tenant_id,
            action="purchase_received",
            entity_type="Purchase",
            entity_id=str(purchase.id),
            detail=f"Purchase {purchase_number} received. Total: KES {total:,.2f}",
            created_by=current_user.id,
        ))
        db.session.commit()
        flash(f"Purchase {purchase_number} recorded successfully. Stock updated.", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("stock.purchases"))


@bp.route("/inventory", methods=["GET"])
@login_required
@role_required("owner", "manager", "stock_manager")
def inventory():
    """Full inventory valuation report."""
    tenant_id = current_user.tenant_id
    products = (
        Product.query.filter_by(tenant_id=tenant_id)
        .order_by(Product.category.asc(), Product.name.asc()).all()
    )
    total_value = sum(
        Decimal(str(p.stock_on_hand)) * Decimal(str(p.cost))
        for p in products if p.active
    )
    total_retail = sum(
        Decimal(str(p.stock_on_hand)) * Decimal(str(p.price))
        for p in products if p.active
    )
    return render_template(
        "inventory.html",
        products=products,
        total_value=total_value,
        total_retail=total_retail,
    )
