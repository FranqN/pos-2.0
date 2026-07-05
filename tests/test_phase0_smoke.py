from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Tenant, User, Product, Customer


def create_tenant_and_admin():
    tenant = Tenant(name="Tenant A", email="t@example.com", phone="123", address="Nairobi")
    db.session.add(tenant)
    db.session.flush()

    admin = User(
        tenant_id=tenant.id,
        email="owner@example.com",
        full_name="Owner",
        role="owner",
    )
    admin.set_password("password123")
    db.session.add(admin)
    db.session.commit()
    return tenant, admin


def login_as(client, tenant_id: int, email: str, password: str):
    # Login route expects tenant_id in form.
    return client.post(
        "/login",
        data={"tenant_id": str(tenant_id), "email": email, "password": password},
        follow_redirects=False,
    )


@pytest.fixture()
def authed_client(client):
    tenant, admin = create_tenant_and_admin()
    # create minimal tenant users are created; login should succeed
    resp = login_as(client, tenant.id, admin.email, "password123")
    # login triggers redirect to /pos/checkout
    assert resp.status_code in (302, 303)
    return client, tenant


def test_checkout_and_daily_report_smoke(authed_client):
    client, tenant = authed_client

    # create data under tenant
    p = Product(
        tenant_id=tenant.id,
        name="Apple",
        sku="SKU-1",
        barcode=None,
        category="Fruits",
        price=Decimal("10.00"),
        cost=Decimal("5.00"),
        stock_on_hand=10,
        reorder_level=5,
        active=True,
    )
    c = Customer(tenant_id=tenant.id, name="John", phone=None, notes=None)
    db.session.add_all([p, c])
    db.session.commit()

    r1 = client.get("/pos/checkout")
    assert r1.status_code == 200
    assert b"checkout" in r1.data.lower() or b"pos" in r1.data.lower()

    r2 = client.get("/reports/daily")
    assert r2.status_code == 200


def test_sale_insufficient_stock_fails_safely(authed_client):
    client, tenant = authed_client

    p = Product(
        tenant_id=tenant.id,
        name="Orange",
        sku="SKU-2",
        barcode=None,
        category="Fruits",
        price=Decimal("10.00"),
        cost=Decimal("3.00"),
        stock_on_hand=1,
        reorder_level=1,
        active=True,
    )
    c = Customer(tenant_id=tenant.id, name="Jane", phone=None, notes=None)
    db.session.add_all([p, c])
    db.session.commit()

    # Build cart: qty > stock
    data = {
        "product_id_0": str(p.id),
        "qty_0": "5",
        "customer_id": str(c.id),
        "discount": "0",
        "cash_amount": "0",
        "mpesa_amount": "0",
        "card_amount": "0",
    }
    resp = client.post("/pos/sale", data=data, follow_redirects=False)
    # Should redirect back to checkout on error
    assert resp.status_code in (302, 303)

    # Ensure stock not decremented
    refreshed = Product.query.get(p.id)
    assert int(refreshed.stock_on_hand) == 1
