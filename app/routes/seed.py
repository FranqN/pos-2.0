from decimal import Decimal
from datetime import datetime, timedelta
from flask import Blueprint, redirect, url_for, flash
from ..extensions import db
from ..models import Tenant, User, Product, Customer, Sale, SaleItem, StockMovement, AuditLog

bp = Blueprint("seed", __name__)


@bp.route("/seed")
def seed():
    # Clear existing data safely
    db.session.query(AuditLog).delete()
    db.session.query(StockMovement).delete()
    db.session.query(SaleItem).delete()
    db.session.query(Sale).delete()
    db.session.query(Customer).delete()
    db.session.query(Product).delete()
    db.session.query(User).delete()
    db.session.query(Tenant).delete()
    db.session.commit()

    # 1. Tenants
    t1 = Tenant(
        name="Kenyatta General Store",
        phone="020-123456",
        email="info@kenyattageneral.co.ke",
        address="Kenyatta Avenue, Nairobi",
        currency="KES",
        vat_enabled=True,
        vat_rate=Decimal("16.00"),
        next_sale_sequence=1,
    )
    t2 = Tenant(
        name="Nairobi Tech Hub",
        phone="020-654321",
        email="contact@nairobitech.io",
        address="Westlands, Nairobi",
        currency="USD",
        vat_enabled=False,
        vat_rate=Decimal("0.00"),
        next_sale_sequence=1,
    )
    db.session.add_all([t1, t2])
    db.session.flush()

    # 2. Users
    u1_owner = User(tenant_id=t1.id, email="owner@kenyatta.com", full_name="John Owner", role="owner")
    u1_owner.set_password("password123")

    u1_mgr = User(tenant_id=t1.id, email="manager@kenyatta.com", full_name="Alice Manager", role="manager")
    u1_mgr.set_password("password123")

    u1_cashier = User(tenant_id=t1.id, email="cashier@kenyatta.com", full_name="Bob Cashier", role="cashier")
    u1_cashier.set_password("password123")

    u2_owner = User(tenant_id=t2.id, email="owner@nairobitech.io", full_name="Hub Admin", role="owner")
    u2_owner.set_password("password123")

    db.session.add_all([u1_owner, u1_mgr, u1_cashier, u2_owner])
    db.session.flush()

    # 3. Products for Tenant 1
    p1 = Product(
        tenant_id=t1.id,
        name="Blue Band Margarine 500g",
        sku="BB-MARG-500",
        barcode="6001234567890",
        category="Groceries",
        price=Decimal("150.00"),
        cost=Decimal("120.00"),
        stock_on_hand=50,
        reorder_level=10,
        active=True,
    )
    p2 = Product(
        tenant_id=t1.id,
        name="Jogoo Maize Meal 2kg",
        sku="JOG-2KG",
        barcode="6009876543210",
        category="Groceries",
        price=Decimal("230.00"),
        cost=Decimal("190.00"),
        stock_on_hand=8,  # Triggers low stock!
        reorder_level=15,
        active=True,
    )
    p3 = Product(
        tenant_id=t1.id,
        name="Broadways Bread 400g",
        sku="BWAY-BREAD-400",
        barcode="6005556667770",
        category="Groceries",
        price=Decimal("65.00"),
        cost=Decimal("50.00"),
        stock_on_hand=3,  # Triggers low stock!
        reorder_level=10,
        active=True,
    )
    p4 = Product(
        tenant_id=t1.id,
        name="Safari Tea 250g",
        sku="SAF-TEA-250",
        barcode="6003334442220",
        category="Beverages",
        price=Decimal("180.00"),
        cost=Decimal("140.00"),
        stock_on_hand=30,
        reorder_level=5,
        active=True,
    )
    p5 = Product(
        tenant_id=t1.id,
        name="Fanta Orange 500ml",
        sku="FANTA-500",
        barcode="6001112223330",
        category="Beverages",
        price=Decimal("70.00"),
        cost=Decimal("55.00"),
        stock_on_hand=40,
        reorder_level=12,
        active=True,
    )
    db.session.add_all([p1, p2, p3, p4, p5])
    db.session.flush()

    # Add initial stock movements
    for p in [p1, p2, p3, p4, p5]:
        db.session.add(
            StockMovement(
                tenant_id=t1.id,
                product_id=p.id,
                movement_type="purchase",
                quantity_delta=p.stock_on_hand,
                notes="Initial Stock Seed",
                created_by=u1_owner.id,
            )
        )

    # 4. Customers for Tenant 1
    c1 = Customer(
        tenant_id=t1.id,
        name="Mwangi Credit Customer",
        phone="0712345678",
        notes="Regular buyer, credit up to 5000 KES",
        balance=Decimal("0.00"),
    )
    c2 = Customer(
        tenant_id=t1.id,
        name="Njeri Walk-in",
        phone="0723456789",
        notes="Cash-only client",
        balance=Decimal("0.00"),
    )
    db.session.add_all([c1, c2])
    db.session.flush()

    # 5. Seed some past sales (for reports and velocity alerts)
    # Sale 1: 5 days ago
    s1 = Sale(
        tenant_id=t1.id,
        sale_number="INV-0001",
        sale_type="counter",
        customer_id=c1.id,
        subtotal=Decimal("650.00"),
        discount=Decimal("50.00"),
        total=Decimal("600.00"),
        payment_status="paid",
        cash_amount=Decimal("600.00"),
        created_by=u1_cashier.id,
        created_at=datetime.utcnow() - timedelta(days=5),
        status="active",
    )
    db.session.add(s1)
    db.session.flush()

    si1 = SaleItem(
        sale_id=s1.id,
        product_id=p1.id,
        name_snapshot=p1.name,
        sku_snapshot=p1.sku,
        unit_price=p1.price,
        quantity=2,
        line_total=Decimal("300.00"),
    )
    si2 = SaleItem(
        sale_id=s1.id,
        product_id=p4.id,
        name_snapshot=p4.name,
        sku_snapshot=p4.sku,
        unit_price=p4.price,
        quantity=2,
        line_total=Decimal("360.00"),
    )
    db.session.add_all([si1, si2])
    t1.next_sale_sequence += 1

    # Sale 2: Today (seeded sales to test report counts)
    s2 = Sale(
        tenant_id=t1.id,
        sale_number="INV-0002",
        sale_type="counter",
        customer_id=c2.id,
        subtotal=Decimal("230.00"),
        discount=Decimal("0.00"),
        total=Decimal("230.00"),
        payment_status="paid",
        mpesa_amount=Decimal("230.00"),
        created_by=u1_cashier.id,
        created_at=datetime.utcnow() - timedelta(hours=1),
        status="active",
    )
    db.session.add(s2)
    db.session.flush()

    si3 = SaleItem(
        sale_id=s2.id,
        product_id=p2.id,
        name_snapshot=p2.name,
        sku_snapshot=p2.sku,
        unit_price=p2.price,
        quantity=1,
        line_total=Decimal("230.00"),
    )
    db.session.add(si3)
    t1.next_sale_sequence += 1

    # Write Audit logs for seed
    db.session.add(
        AuditLog(
            tenant_id=t1.id,
            action="seed",
            entity_type="system",
            entity_id=None,
            detail="Database seeded with standard test data.",
            created_by=u1_owner.id,
        )
    )

    db.session.commit()
    flash("Database seeded successfully with premium test data!", "success")
    return redirect(url_for("auth.login"))

