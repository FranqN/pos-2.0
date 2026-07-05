from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Product, Sale, SaleItem, StockMovement, Customer, Tenant, AuditLog
from ..services.ai_service import ai_reorder_suggestions
from ..services.mpesa_service import initiate_stk_push, check_stk_status, process_callback_simulation

bp = Blueprint("pos", __name__)


@bp.route("/checkout", methods=["GET"])
@login_required
def checkout():
    tenant_id = current_user.tenant_id
    products = (
        Product.query.filter_by(tenant_id=tenant_id, active=True)
        .order_by(Product.name.asc())
        .all()
    )
    customers = (
        Customer.query.filter_by(tenant_id=tenant_id)
        .order_by(Customer.name.asc())
        .all()
    )

    # AI suggestions (safe)
    reorder = ai_reorder_suggestions(tenant_id)

    return render_template(
        "checkout.html", products=products, customers=customers, reorder=reorder
    )


@bp.route("/sale", methods=["POST"])
@login_required
def create_sale():
    tenant_id = current_user.tenant_id

    # Cart lines: product_id -> qty
    lines: list[tuple[int, int]] = []
    i = 0
    while True:
        pid = request.form.get(f"product_id_{i}")
        qty = request.form.get(f"qty_{i}")
        if not pid:
            break
        if not qty:
            i += 1
            continue
        try:
            qty_i = int(qty)
            if qty_i > 0:
                lines.append((int(pid), qty_i))
        except ValueError:
            pass
        i += 1

    if not lines:
        flash("Cart is empty.", "error")
        return redirect(url_for("pos.checkout"))

    customer_id_raw = request.form.get("customer_id")
    customer_id = int(customer_id_raw) if customer_id_raw else None

    discount = Decimal(request.form.get("discount", "0") or "0")
    cash_amount = Decimal(request.form.get("cash_amount", "0") or "0")
    mpesa_amount = Decimal(request.form.get("mpesa_amount", "0") or "0")
    card_amount = Decimal(request.form.get("card_amount", "0") or "0")

    # Start database-locked transaction block to prevent concurrency issues
    try:
        # Lock tenant row to generate invoice number sequence safely
        tenant = Tenant.query.filter_by(id=tenant_id).with_for_update().first()
        if not tenant:
            flash("Tenant context error.", "error")
            return redirect(url_for("pos.checkout"))

        sale_number = f"INV-{tenant.next_sale_sequence:06d}"
        tenant.next_sale_sequence += 1

        # Capture M-Pesa checkout details if provided
        mpesa_phone = request.form.get("mpesa_phone", "").strip() or None
        mpesa_checkout_id = request.form.get("mpesa_checkout_id", "").strip() or None
        mpesa_receipt_number = request.form.get("mpesa_receipt_number", "").strip() or None

        sale = Sale(
            tenant_id=tenant_id,
            sale_number=sale_number,
            sale_type="counter",
            customer_id=customer_id,
            discount=discount,
            cash_amount=cash_amount,
            mpesa_amount=mpesa_amount,
            card_amount=card_amount,
            mpesa_phone=mpesa_phone,
            mpesa_checkout_id=mpesa_checkout_id,
            mpesa_receipt_number=mpesa_receipt_number,
            payment_status="unpaid",
            status="active",
            created_by=current_user.id,
        )
        db.session.add(sale)
        db.session.flush()

        subtotal = Decimal("0")

        # Query and lock products involved to ensure stock is decremented atomically
        pids = [pid for pid, _ in lines]
        locked_products = {
            p.id: p
            for p in Product.query.filter(
                Product.tenant_id == tenant_id, Product.id.in_(pids)
            ).with_for_update().all()
        }

        # Validate stock first (fail fast)
        for pid, qty in lines:
            p = locked_products.get(pid)
            if not p:
                raise ValueError("A selected product was not found.")
            if int(p.stock_on_hand) < qty:
                raise ValueError(f"Insufficient stock for {p.name}. Stock available: {p.stock_on_hand}")

        # Create items + stock movements
        for pid, qty in lines:
            p = locked_products[pid]
            line_total = Decimal(p.price) * qty
            subtotal += line_total

            item = SaleItem(
                sale_id=sale.id,
                product_id=p.id,
                name_snapshot=p.name,
                sku_snapshot=p.sku,
                unit_price=p.price,
                quantity=qty,
                line_discount=Decimal("0"),
                line_total=line_total,
            )
            db.session.add(item)

            # stock decrement
            p.stock_on_hand = int(p.stock_on_hand) - qty
            db.session.add(
                StockMovement(
                    tenant_id=tenant_id,
                    product_id=p.id,
                    movement_type="sale",
                    quantity_delta=-qty,
                    notes=f"Sale {sale.sale_number}",
                    created_by=current_user.id,
                )
            )

        total = subtotal - discount
        sale.subtotal = subtotal
        sale.total = total

        paid = cash_amount + mpesa_amount + card_amount
        if paid >= total:
            sale.payment_status = "paid"
        elif paid > 0:
            sale.payment_status = "partial"
        else:
            sale.payment_status = "unpaid"

        # Update customer credit balance
        if customer_id:
            c = Customer.query.filter_by(id=customer_id).with_for_update().first()
            if c:
                c.balance = Decimal(c.balance) + (total - paid)

        # Log checkout audit log
        audit = AuditLog(
            tenant_id=tenant_id,
            action="sale_checkout",
            entity_type="Sale",
            entity_id=str(sale.id),
            detail=f"Sale {sale.sale_number} completed. Total: {sale.total}",
            created_by=current_user.id,
        )
        db.session.add(audit)

        db.session.commit()
        flash(f"Sale completed: {sale.sale_number}", "success")
        sale_id_for_redirect = sale.id
    except Exception as e:
        db.session.rollback()
        flash(str(e), "error")
        return redirect(url_for("pos.checkout"))

    return redirect(url_for("receipt.view_receipt", sale_id=sale_id_for_redirect))


@bp.route("/void/<int:sale_id>", methods=["POST"])
@login_required
def void_sale(sale_id: int):
    tenant_id = current_user.tenant_id
    try:
        sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).with_for_update().first()
        if not sale:
            raise ValueError("Sale not found.")
        if sale.status == "voided":
            raise ValueError("Sale is already voided.")

        # Revert stock movements
        for item in sale.items:
            product = Product.query.filter_by(id=item.product_id, tenant_id=tenant_id).with_for_update().first()
            if product:
                product.stock_on_hand = int(product.stock_on_hand) + item.quantity
                db.session.add(
                    StockMovement(
                        tenant_id=tenant_id,
                        product_id=product.id,
                        movement_type="return",
                        quantity_delta=item.quantity,
                        notes=f"Void of sale {sale.sale_number}",
                        created_by=current_user.id,
                    )
                )

        # Revert customer credit balance if applicable
        if sale.customer_id:
            c = Customer.query.filter_by(id=sale.customer_id).with_for_update().first()
            if c:
                paid = Decimal(sale.cash_amount or 0) + Decimal(sale.mpesa_amount or 0) + Decimal(sale.card_amount or 0)
                net_credit = Decimal(sale.total or 0) - paid
                c.balance = Decimal(c.balance or 0) - net_credit

        sale.status = "voided"

        # Log audit
        db.session.add(
            AuditLog(
                tenant_id=tenant_id,
                action="sale_void",
                entity_type="Sale",
                entity_id=str(sale.id),
                detail=f"Sale {sale.sale_number} voided.",
                created_by=current_user.id,
            )
        )
        db.session.commit()
        flash(f"Sale {sale.sale_number} voided successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("reports.daily_report"))


@bp.route("/refund/<int:sale_id>", methods=["POST"])
@login_required
def refund_sale(sale_id: int):
    tenant_id = current_user.tenant_id
    try:
        sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).with_for_update().first()
        if not sale:
            raise ValueError("Sale not found.")
        if sale.status in ("voided", "refunded"):
            raise ValueError(f"Sale is already {sale.status}.")

        # Revert stock movements
        for item in sale.items:
            product = Product.query.filter_by(id=item.product_id, tenant_id=tenant_id).with_for_update().first()
            if product:
                product.stock_on_hand = int(product.stock_on_hand) + item.quantity
                db.session.add(
                    StockMovement(
                        tenant_id=tenant_id,
                        product_id=product.id,
                        movement_type="return",
                        quantity_delta=item.quantity,
                        notes=f"Refund of sale {sale.sale_number}",
                        created_by=current_user.id,
                    )
                )

        # Revert customer credit balance
        if sale.customer_id:
            c = Customer.query.filter_by(id=sale.customer_id).with_for_update().first()
            if c:
                paid = Decimal(sale.cash_amount or 0) + Decimal(sale.mpesa_amount or 0) + Decimal(sale.card_amount or 0)
                net_credit = Decimal(sale.total or 0) - paid
                c.balance = Decimal(c.balance or 0) - net_credit

        sale.status = "refunded"

        # Log audit
        db.session.add(
            AuditLog(
                tenant_id=tenant_id,
                action="sale_refund",
                entity_type="Sale",
                entity_id=str(sale.id),
                detail=f"Sale {sale.sale_number} refunded.",
                created_by=current_user.id,
            )
        )
        db.session.commit()
        flash(f"Sale {sale.sale_number} refunded successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("reports.daily_report"))


# ─── M-Pesa STK Push API Endpoints ───

@bp.route("/mpesa/stk-push", methods=["POST"])
@login_required
def mpesa_stk_push():
    """Initiates an M-Pesa STK Push request."""
    tenant_id = current_user.tenant_id
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    amount = data.get("amount", 0)

    if not phone:
        return jsonify({"success": False, "message": "Phone number is required."}), 400
    if not amount or float(amount) <= 0:
        return jsonify({"success": False, "message": "Amount must be greater than zero."}), 400

    result = initiate_stk_push(tenant_id, phone, float(amount))
    return jsonify(result)


@bp.route("/mpesa/query-status", methods=["GET"])
@login_required
def mpesa_query_status():
    """Checks the status of an active STK Push checkout."""
    tenant_id = current_user.tenant_id
    checkout_id = request.args.get("checkout_id", "").strip()

    if not checkout_id:
        return jsonify({"success": False, "message": "checkout_id is required."}), 400

    result = check_stk_status(tenant_id, checkout_id)
    return jsonify(result)


@bp.route("/mpesa/simulate-callback", methods=["POST"])
@login_required
def mpesa_simulate_callback():
    """Simulates a Safaricom callback for testing STK Push flows."""
    data = request.get_json(silent=True) or {}
    checkout_id = data.get("checkout_id", "").strip()
    outcome = data.get("outcome", "success").strip()  # success | insufficient_funds | cancelled

    if not checkout_id:
        return jsonify({"success": False, "message": "checkout_id is required."}), 400

    ok = process_callback_simulation(checkout_id, outcome)
    if ok:
        return jsonify({"success": True, "message": f"Simulated callback: {outcome}"})
    return jsonify({"success": False, "message": "Transaction not found."}), 404
