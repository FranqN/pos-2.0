from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


class Tenant(db.Model):
    __tablename__ = "tenants"
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.String(250))

    # file stored in static/uploads
    logo_filename = db.Column(db.String(250))

    currency = db.Column(db.String(10), default="KES")
    vat_enabled = db.Column(db.Boolean, default=False)
    vat_rate = db.Column(db.Numeric(6, 3), default=0)
    next_sale_sequence = db.Column(db.Integer, default=1, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # M-Pesa Settings
    mpesa_shortcode = db.Column(db.String(50))
    mpesa_consumer_key = db.Column(db.String(250))
    mpesa_consumer_secret = db.Column(db.String(250))
    mpesa_passkey = db.Column(db.String(250))
    mpesa_simulate = db.Column(db.Boolean, default=True, nullable=False)

    users = db.relationship("User", backref="tenant", lazy=True)
    products = db.relationship("Product", backref="tenant", lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    full_name = db.Column(db.String(160))
    password_hash = db.Column(db.String(255), nullable=False)

    # roles: owner, manager, cashier, stock_manager, viewer
    role = db.Column(db.String(40), default="cashier")
    last_login_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("tenant_id", "email", name="uq_tenant_email"),)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(80), index=True)
    barcode = db.Column(db.String(80), index=True)

    category = db.Column(db.String(120), default="General")
    image_filename = db.Column(db.String(250))

    price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    stock_on_hand = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=0)

    active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)

    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    notes = db.Column(db.String(500))

    balance = db.Column(db.Numeric(14, 2), default=0)
    credit_limit = db.Column(db.Numeric(14, 2), default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sales = db.relationship("Sale", backref="customer", lazy=True)


class Supplier(db.Model):
    __tablename__ = "suppliers"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(150))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)

    sale_number = db.Column(db.String(40), nullable=False, index=True)
    sale_type = db.Column(db.String(30), default="counter")  # counter / layaway / refund

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)

    subtotal = db.Column(db.Numeric(12, 2), default=0)
    discount = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)

    payment_status = db.Column(db.String(20), default="unpaid")
    status = db.Column(db.String(30), default="active", nullable=False)

    cash_amount = db.Column(db.Numeric(12, 2), default=0)
    mpesa_amount = db.Column(db.Numeric(12, 2), default=0)
    card_amount = db.Column(db.Numeric(12, 2), default=0)

    # M-Pesa checkout information
    mpesa_phone = db.Column(db.String(50))
    mpesa_checkout_id = db.Column(db.String(100))
    mpesa_receipt_number = db.Column(db.String(50))

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship("SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan")
    cashier = db.relationship("User", foreign_keys=[created_by])


class SaleItem(db.Model):
    __tablename__ = "sale_items"
    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    name_snapshot = db.Column(db.String(200), nullable=False)
    sku_snapshot = db.Column(db.String(80))

    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    line_discount = db.Column(db.Numeric(12, 2), default=0)

    line_total = db.Column(db.Numeric(12, 2), default=0)

    product = db.relationship("Product", foreign_keys=[product_id])


class Purchase(db.Model):
    __tablename__ = "purchases"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)
    purchase_number = db.Column(db.String(40), nullable=False, index=True)
    total = db.Column(db.Numeric(12, 2), default=0)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship("PurchaseItem", backref="purchase", lazy=True, cascade="all, delete-orphan")
    supplier = db.relationship("Supplier", foreign_keys=[supplier_id])


class PurchaseItem(db.Model):
    __tablename__ = "purchase_items"
    id = db.Column(db.Integer, primary_key=True)

    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    unit_cost = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    line_total = db.Column(db.Numeric(12, 2), default=0)

    product = db.relationship("Product", foreign_keys=[product_id])


class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    movement_type = db.Column(db.String(30), nullable=False)  # purchase / sale / adjustment / return
    quantity_delta = db.Column(db.Integer, nullable=False)

    notes = db.Column(db.String(500))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    product = db.relationship("Product", foreign_keys=[product_id])


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.String(80))
    detail = db.Column(db.String(500))

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[created_by])
