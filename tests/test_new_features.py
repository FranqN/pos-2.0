from decimal import Decimal
import io
import pytest
from app.extensions import db
from app.models import Tenant, User, Product, Customer, Supplier, Purchase, Sale, SaleItem

def create_tenant_and_users():
    tenant = Tenant(name="Tenant Y", email="y@example.com", phone="123", address="Mombasa", next_sale_sequence=1)
    db.session.add(tenant)
    db.session.flush()

    owner = User(tenant_id=tenant.id, email="owner@y.com", full_name="Owner Y", role="owner")
    owner.set_password("pass123")

    manager = User(tenant_id=tenant.id, email="manager@y.com", full_name="Manager Y", role="manager")
    manager.set_password("pass123")

    db.session.add_all([owner, manager])
    db.session.commit()
    return tenant, owner, manager

def login_as(client, tenant_id: int, email: str, password: str):
    return client.post(
        "/login",
        data={"tenant_id": str(tenant_id), "email": email, "password": password},
        follow_redirects=False,
    )

def test_stock_adjustments_and_suppliers(client, app_ctx):
    tenant, owner, manager = create_tenant_and_users()

    # Login as owner
    login_as(client, tenant.id, owner.email, "pass123")

    # 1. Create a Product
    p = Product(
        tenant_id=tenant.id,
        name="Milk",
        sku="MILK-1",
        price=Decimal("80.00"),
        cost=Decimal("60.00"),
        stock_on_hand=10,
        reorder_level=2,
        active=True,
    )
    db.session.add(p)
    db.session.commit()

    # 2. Adjust stock
    resp = client.post(
        "/stock/adjustments/apply",
        data={"product_id": str(p.id), "quantity_delta": "5", "notes": "Received extra"},
        follow_redirects=True
    )
    assert resp.status_code == 200
    db.session.expire_all()
    p_ref = Product.query.get(p.id)
    assert p_ref.stock_on_hand == 15

    # 3. Create a Supplier
    resp_supplier = client.post(
        "/stock/suppliers/new",
        data={"name": "KCC Dairy", "phone": "0722000000", "email": "info@kcc.co.ke", "contact_person": "Jane Doe"},
        follow_redirects=True
    )
    assert resp_supplier.status_code == 200
    db.session.expire_all()
    supplier = Supplier.query.filter_by(tenant_id=tenant.id, name="KCC Dairy").first()
    assert supplier is not None
    assert supplier.contact_person == "Jane Doe"

    # 4. Create a Purchase Order (record purchase/stock in)
    purchase_data = {
        "supplier_id": str(supplier.id),
        "ref_number": "PO-1002",
        "product_id_0": str(p.id),
        "qty_0": "20",
        "unit_cost_0": "55.00"
    }
    resp_purchase = client.post("/stock/purchases/new", data=purchase_data, follow_redirects=True)
    assert resp_purchase.status_code == 200

    db.session.expire_all()
    p_after_purchase = Product.query.get(p.id)
    assert p_after_purchase.stock_on_hand == 35  # 15 + 20

    purchase = Purchase.query.filter_by(tenant_id=tenant.id, purchase_number="PO-1002").first()
    assert purchase is not None
    assert purchase.total == Decimal("1100.00")  # 20 * 55.00

def test_receipt_views(client, app_ctx):
    tenant, owner, manager = create_tenant_and_users()
    login_as(client, tenant.id, owner.email, "pass123")

    p = Product(
        tenant_id=tenant.id,
        name="Water",
        sku="WATER-1",
        price=Decimal("40.00"),
        cost=Decimal("25.00"),
        stock_on_hand=50,
        reorder_level=5,
        active=True,
    )
    db.session.add(p)
    db.session.commit()

    # Perform a checkout
    sale_data = {
        "product_id_0": str(p.id),
        "qty_0": "3",
        "discount": "10",  # Total = 3 * 40 - 10 = 110
        "cash_amount": "200.00",
        "mpesa_amount": "0",
        "card_amount": "0",
    }
    client.post("/pos/sale", data=sale_data)

    db.session.expire_all()
    sale = Sale.query.filter_by(tenant_id=tenant.id).first()
    assert sale is not None

    # Test html receipt view
    resp_html = client.get(f"/receipt/{sale.id}")
    assert resp_html.status_code == 200
    assert b"Invoice" in resp_html.data
    assert b"Water" in resp_html.data

    # Test PDF generation
    resp_pdf = client.get(f"/receipt/{sale.id}/pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["Content-Type"] == "application/pdf"

def test_analytics_and_customer_history(client, app_ctx):
    tenant, owner, manager = create_tenant_and_users()
    login_as(client, tenant.id, owner.email, "pass123")

    # 1. Customer history and settle balance
    c = Customer(tenant_id=tenant.id, name="David Mwangi", phone="0711111111", balance=Decimal("500.00"))
    db.session.add(c)
    db.session.commit()

    # View customer history
    resp_hist = client.get(f"/customers/{c.id}/history")
    assert resp_hist.status_code == 200
    assert b"David Mwangi" in resp_hist.data

    # Settle balance
    resp_settle = client.post(f"/customers/{c.id}/settle", data={"amount": "200.00"}, follow_redirects=True)
    assert resp_settle.status_code == 200
    db.session.expire_all()
    c_ref = Customer.query.get(c.id)
    assert c_ref.balance == Decimal("300.00")

    # 2. Test analytics endpoints
    resp_trend = client.get("/analytics/revenue-trend")
    assert resp_trend.status_code == 200
    assert "labels" in resp_trend.json

    resp_top = client.get("/analytics/top-products")
    assert resp_top.status_code == 200
    assert "labels" in resp_top.json

    resp_split = client.get("/analytics/payment-split")
    assert resp_split.status_code == 200
    assert "labels" in resp_split.json

def test_csv_import_and_product_toggles(client, app_ctx):
    tenant, owner, manager = create_tenant_and_users()
    login_as(client, tenant.id, owner.email, "pass123")

    # 1. Get CSV Template
    resp_tpl = client.get("/products/csv-template")
    assert resp_tpl.status_code == 200
    assert resp_tpl.headers["Content-Type"] == "text/csv; charset=utf-8"

    # 2. Import CSV data
    csv_data = "name,sku,barcode,category,price,cost,stock_on_hand,reorder_level\n" \
               "Apple Juice,JUICE-1,111222,Drinks,120.00,75.00,100,15\n" \
               "Orange Juice,JUICE-2,111223,Drinks,130.00,80.00,80,10\n"
    
    resp_import = client.post(
        "/products/import-csv",
        data={"csv_file": (io.BytesIO(csv_data.encode("utf-8")), "products.csv")},
        follow_redirects=True
    )
    assert resp_import.status_code == 200

    db.session.expire_all()
    p1 = Product.query.filter_by(tenant_id=tenant.id, sku="JUICE-1").first()
    p2 = Product.query.filter_by(tenant_id=tenant.id, sku="JUICE-2").first()
    assert p1 is not None
    assert p1.price == Decimal("120.00")
    assert p1.stock_on_hand == 100
    assert p2 is not None
    assert p2.stock_on_hand == 80

    # 3. Toggle product active status
    resp_toggle = client.post(f"/products/{p1.id}/toggle", follow_redirects=True)
    assert resp_toggle.status_code == 200
    db.session.expire_all()
    p1_toggled = Product.query.get(p1.id)
    assert p1_toggled.active is False
