"""Product routes: list, create, edit, toggle active, CSV import."""
import csv
import io
import os
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Product, AuditLog
from ..utils import role_required

bp = Blueprint("products", __name__)

ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}


def _allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTS


@bp.route("/", methods=["GET"])
@login_required
def list_products():
    tenant_id = current_user.tenant_id
    search = request.args.get("q", "").strip()
    category_filter = request.args.get("cat", "").strip()
    status_filter = request.args.get("status", "active")

    q = Product.query.filter_by(tenant_id=tenant_id)
    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%")) |
            (Product.sku.ilike(f"%{search}%")) |
            (Product.barcode.ilike(f"%{search}%"))
        )
    if category_filter:
        q = q.filter(Product.category == category_filter)
    if status_filter == "active":
        q = q.filter(Product.active == True)
    elif status_filter == "inactive":
        q = q.filter(Product.active == False)

    products = q.order_by(Product.name.asc()).all()

    # All categories for filter pills
    all_categories = [
        r[0] for r in db.session.query(Product.category)
        .filter_by(tenant_id=tenant_id).distinct().order_by(Product.category.asc()).all()
        if r[0]
    ]
    return render_template(
        "products.html",
        products=products,
        all_categories=all_categories,
        search=search,
        category_filter=category_filter,
        status_filter=status_filter,
    )


@bp.route("/new", methods=["POST"])
@login_required
@role_required("owner", "manager", "stock_manager")
def create_product():
    tenant_id = current_user.tenant_id

    name = request.form.get("name", "").strip()
    price = request.form.get("price", "0").strip()
    sku = request.form.get("sku", "").strip() or None
    barcode = request.form.get("barcode", "").strip() or None
    category = request.form.get("category", "General").strip() or "General"
    stock_on_hand = int(request.form.get("stock_on_hand", "0") or "0")
    reorder_level = int(request.form.get("reorder_level", "0") or "0")
    cost = request.form.get("cost", "0").strip() or "0"

    if not name:
        flash("Product name required.", "error")
        return redirect(url_for("products.list_products"))

    # Duplicate SKU/barcode check
    if sku:
        dup = Product.query.filter_by(tenant_id=tenant_id, sku=sku).first()
        if dup:
            flash(f"SKU '{sku}' already exists for product '{dup.name}'.", "error")
            return redirect(url_for("products.list_products"))
    if barcode:
        dup = Product.query.filter_by(tenant_id=tenant_id, barcode=barcode).first()
        if dup:
            flash(f"Barcode '{barcode}' already exists for product '{dup.name}'.", "error")
            return redirect(url_for("products.list_products"))

    image_filename = None
    image_file = request.files.get("image")
    if image_file and image_file.filename and _allowed_image(image_file.filename):
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        fname = secure_filename(image_file.filename)
        fname = f"product_{tenant_id}_{fname}"
        image_file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], fname))
        image_filename = fname

    p = Product(
        tenant_id=tenant_id,
        name=name,
        sku=sku,
        barcode=barcode,
        category=category,
        price=price,
        cost=cost,
        stock_on_hand=stock_on_hand,
        reorder_level=reorder_level,
        image_filename=image_filename,
    )
    db.session.add(p)
    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="product_create",
        entity_type="Product",
        entity_id="new",
        detail=f"Product '{name}' created. Price: {price}, Stock: {stock_on_hand}",
        created_by=current_user.id,
    ))
    db.session.commit()

    flash(f"Product '{name}' added.", "success")
    return redirect(url_for("products.list_products"))


@bp.route("/<int:product_id>/edit", methods=["POST"])
@login_required
@role_required("owner", "manager", "stock_manager")
def edit_product(product_id: int):
    tenant_id = current_user.tenant_id
    p = Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()
    if not p:
        flash("Product not found.", "error")
        return redirect(url_for("products.list_products"))

    p.name = request.form.get("name", p.name).strip()
    new_sku = request.form.get("sku", "").strip() or None
    new_barcode = request.form.get("barcode", "").strip() or None
    p.category = request.form.get("category", "General").strip() or "General"
    p.reorder_level = int(request.form.get("reorder_level", p.reorder_level) or 0)

    # Duplicate SKU/barcode check (exclude current product)
    if new_sku and new_sku != p.sku:
        dup = Product.query.filter(
            Product.tenant_id == tenant_id,
            Product.sku == new_sku,
            Product.id != product_id
        ).first()
        if dup:
            flash(f"SKU '{new_sku}' already exists for product '{dup.name}'.", "error")
            return redirect(url_for("products.list_products"))
    if new_barcode and new_barcode != p.barcode:
        dup = Product.query.filter(
            Product.tenant_id == tenant_id,
            Product.barcode == new_barcode,
            Product.id != product_id
        ).first()
        if dup:
            flash(f"Barcode '{new_barcode}' already exists for product '{dup.name}'.", "error")
            return redirect(url_for("products.list_products"))

    p.sku = new_sku
    p.barcode = new_barcode

    try:
        p.price = Decimal(request.form.get("price", str(p.price)))
        p.cost = Decimal(request.form.get("cost", str(p.cost)))
    except InvalidOperation:
        flash("Invalid price or cost value.", "error")
        return redirect(url_for("products.list_products"))

    image_file = request.files.get("image")
    if image_file and image_file.filename and _allowed_image(image_file.filename):
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        fname = secure_filename(image_file.filename)
        fname = f"product_{tenant_id}_{product_id}_{fname}"
        image_file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], fname))
        p.image_filename = fname

    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action="product_edit",
        entity_type="Product",
        entity_id=str(p.id),
        detail=f"Product '{p.name}' updated. Price: {p.price}",
        created_by=current_user.id,
    ))
    db.session.commit()
    flash(f"Product '{p.name}' updated.", "success")
    return redirect(url_for("products.list_products"))


@bp.route("/<int:product_id>/toggle", methods=["POST"])
@login_required
@role_required("owner", "manager")
def toggle_product(product_id: int):
    tenant_id = current_user.tenant_id
    p = Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()
    if not p:
        flash("Product not found.", "error")
        return redirect(url_for("products.list_products"))
    p.active = not p.active
    action = "activated" if p.active else "deactivated"
    db.session.add(AuditLog(
        tenant_id=tenant_id,
        action=f"product_{action}",
        entity_type="Product",
        entity_id=str(p.id),
        detail=f"Product '{p.name}' {action}.",
        created_by=current_user.id,
    ))
    db.session.commit()
    flash(f"Product '{p.name}' {action}.", "success")
    return redirect(url_for("products.list_products"))


@bp.route("/import-csv", methods=["POST"])
@login_required
@role_required("owner", "manager", "stock_manager")
def import_csv():
    tenant_id = current_user.tenant_id
    file = request.files.get("csv_file")
    if not file or not file.filename.endswith(".csv"):
        flash("Please upload a valid CSV file.", "error")
        return redirect(url_for("products.list_products"))

    stream = io.StringIO(file.stream.read().decode("UTF-8-sig"))
    reader = csv.DictReader(stream)

    created = 0
    errors = []
    for i, row in enumerate(reader, start=2):
        name = (row.get("name") or row.get("Name") or "").strip()
        if not name:
            errors.append(f"Row {i}: 'name' is required.")
            continue
        try:
            price = Decimal(str(row.get("price") or row.get("Price") or "0").strip())
            cost = Decimal(str(row.get("cost") or row.get("Cost") or "0").strip())
            stock = int(str(row.get("stock_on_hand") or row.get("Stock") or "0").strip())
            reorder = int(str(row.get("reorder_level") or row.get("Reorder") or "0").strip())
        except Exception:
            errors.append(f"Row {i}: Invalid numeric value.")
            continue

        p = Product(
            tenant_id=tenant_id,
            name=name,
            sku=(row.get("sku") or row.get("SKU") or "").strip() or None,
            barcode=(row.get("barcode") or row.get("Barcode") or "").strip() or None,
            category=(row.get("category") or row.get("Category") or "General").strip() or "General",
            price=price,
            cost=cost,
            stock_on_hand=stock,
            reorder_level=reorder,
        )
        db.session.add(p)
        created += 1

    if created:
        db.session.add(AuditLog(
            tenant_id=tenant_id,
            action="product_csv_import",
            entity_type="Product",
            entity_id="bulk",
            detail=f"Bulk imported {created} products from CSV.",
            created_by=current_user.id,
        ))
        db.session.commit()
        flash(f"Successfully imported {created} products.", "success")
    if errors:
        for err in errors[:5]:
            flash(err, "error")

    return redirect(url_for("products.list_products"))


@bp.route("/csv-template", methods=["GET"])
@login_required
def csv_template():
    from flask import Response
    header = "name,sku,barcode,category,price,cost,stock_on_hand,reorder_level\n"
    sample = "Sample Product,SKU001,1234567890,General,150.00,80.00,50,10\n"
    resp = Response(header + sample, mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=products_template.csv"
    return resp
