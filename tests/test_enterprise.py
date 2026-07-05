from decimal import Decimal
import pytest
from app.extensions import db
from app.models import Tenant, User, Product, Customer, Sale, SaleItem


def create_tenant_and_users():
    tenant = Tenant(name="Tenant X", email="x@example.com", phone="123", address="Nairobi", next_sale_sequence=1)
    db.session.add(tenant)
    db.session.flush()

    owner = User(tenant_id=tenant.id, email="owner@x.com", full_name="Owner X", role="owner")
    owner.set_password("pass123")

    cashier = User(tenant_id=tenant.id, email="cashier@x.com", full_name="Cashier X", role="cashier")
    cashier.set_password("pass123")

    db.session.add_all([owner, cashier])
    db.session.commit()
    return tenant, owner, cashier


def login_as(client, tenant_id: int, email: str, password: str):
    return client.post(
        "/login",
        data={"tenant_id": str(tenant_id), "email": email, "password": password},
        follow_redirects=False,
    )


def test_role_restrictions(client, app_ctx):
    tenant, owner, cashier = create_tenant_and_users()

    # 1. Login as Cashier
    resp = login_as(client, tenant.id, cashier.email, "pass123")
    assert resp.status_code in (302, 303)

    # Cashier should NOT be able to view daily reports (403 forbidden)
    r_rep = client.get("/reports/daily")
    assert r_rep.status_code == 403

    # Cashier should NOT be able to create products (403 forbidden)
    r_prod = client.post("/products/new", data={"name": "New Prod", "price": "100"})
    assert r_prod.status_code == 403

    # Logout
    client.get("/logout")

    # 2. Login as Owner
    resp = login_as(client, tenant.id, owner.email, "pass123")
    assert resp.status_code in (302, 303)

    # Owner should be allowed to view reports
    r_rep = client.get("/reports/daily")
    assert r_rep.status_code == 200


def test_sequential_invoice_number(client, app_ctx):
    tenant, owner, cashier = create_tenant_and_users()

    p = Product(
        tenant_id=tenant.id,
        name="Soda",
        sku="SODA-1",
        price=Decimal("50.00"),
        cost=Decimal("35.00"),
        stock_on_hand=100,
        reorder_level=5,
        active=True,
    )
    db.session.add(p)
    db.session.commit()

    # Login as owner
    login_as(client, tenant.id, owner.email, "pass123")

    # Perform sale 1
    data1 = {
        "product_id_0": str(p.id),
        "qty_0": "2",
        "discount": "0",
        "cash_amount": "100.00",
        "mpesa_amount": "0",
        "card_amount": "0",
    }
    client.post("/pos/sale", data=data1)

    # Perform sale 2
    data2 = {
        "product_id_0": str(p.id),
        "qty_0": "1",
        "discount": "0",
        "cash_amount": "50.00",
        "mpesa_amount": "0",
        "card_amount": "0",
    }
    client.post("/pos/sale", data=data2)

    # Query sales in database
    sales = Sale.query.filter_by(tenant_id=tenant.id).order_by(Sale.created_at.asc()).all()
    assert len(sales) == 2
    assert sales[0].sale_number == "INV-000001"
    assert sales[1].sale_number == "INV-000002"
    assert sales[0].status == "active"


def test_void_and_refund_flows(client, app_ctx):
    tenant, owner, cashier = create_tenant_and_users()

    p = Product(
        tenant_id=tenant.id,
        name="Bread",
        sku="BREAD-1",
        price=Decimal("65.00"),
        cost=Decimal("50.00"),
        stock_on_hand=10,
        reorder_level=2,
        active=True,
    )
    c = Customer(tenant_id=tenant.id, name="Mwangi Credit", phone="07123", balance=Decimal("0.00"))
    db.session.add_all([p, c])
    db.session.commit()

    login_as(client, tenant.id, owner.email, "pass123")

    # Checkout sale on credit
    data = {
        "product_id_0": str(p.id),
        "qty_0": "4",
        "customer_id": str(c.id),
        "discount": "10.00", # Total = 4 * 65 - 10 = 250
        "cash_amount": "50.00", # Credit portion = 200
        "mpesa_amount": "0",
        "card_amount": "0",
    }
    client.post("/pos/sale", data=data)

    # Confirm stock was decremented and customer balance increased
    db.session.expire_all()
    p_ref = Product.query.get(p.id)
    c_ref = Customer.query.get(c.id)
    s_ref = Sale.query.filter_by(tenant_id=tenant.id).first()

    assert int(p_ref.stock_on_hand) == 6
    assert c_ref.balance == Decimal("200.00")
    assert s_ref.status == "active"

    # Void the sale
    resp_void = client.post(f"/pos/void/{s_ref.id}")
    assert resp_void.status_code in (302, 303)

    # Verify stock restored and credit reverted
    db.session.expire_all()
    p_voided = Product.query.get(p.id)
    c_voided = Customer.query.get(c.id)
    s_voided = Sale.query.get(s_ref.id)

    assert int(p_voided.stock_on_hand) == 10
    assert c_voided.balance == Decimal("0.00")
    assert s_voided.status == "voided"


def test_tenant_registration_and_login(client, app_ctx):
    # Register tenant via POST to /tenant/create
    reg_data = {
        "name": "New Business Store",
        "phone": "987654",
        "email": "newbusiness@example.com",
        "address": "Mombasa Road",
        "admin_email": "admin@newbusiness.com",
        "admin_password": "securepassword",
    }
    resp = client.post("/tenant/create", data=reg_data, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Tenant created" in resp.data or b"Please login" in resp.data

    # Query the newly created Tenant
    t = Tenant.query.filter_by(name="New Business Store").first()
    assert t is not None
    assert t.next_sale_sequence == 1

    # Query the user
    user = User.query.filter_by(tenant_id=t.id, email="admin@newbusiness.com").first()
    assert user is not None
    assert user.role == "owner"
    assert user.check_password("securepassword") is True

    # Try login as admin@newbusiness.com
    login_resp = client.post(
        "/login",
        data={
            "tenant_id": str(t.id),
            "email": "admin@newbusiness.com",
            "password": "securepassword"
        },
        follow_redirects=False
    )
    # Successful login redirects to POS checkout (302/303)
    assert login_resp.status_code in (302, 303)


def test_tenant_settings_and_staff_management(client, app_ctx):
    tenant, owner, cashier = create_tenant_and_users()

    # 1. Cashier should be blocked from dashboard (403)
    login_as(client, tenant.id, cashier.email, "pass123")
    r = client.get("/tenant/dashboard")
    assert r.status_code == 403
    client.get("/logout")

    # 2. Owner should be allowed (200)
    login_as(client, tenant.id, owner.email, "pass123")
    r2 = client.get("/tenant/dashboard")
    assert r2.status_code == 200

    # 3. Owner updates settings
    update_data = {
        "name": "Kenyatta Supermarket",
        "phone": "0700111222",
        "email": "super@kenyatta.com",
        "address": "Nairobi CBD",
        "currency": "KES",
        "vat_enabled": "y",
        "vat_rate": "16.00"
    }
    r3 = client.post("/tenant/dashboard", data=update_data, follow_redirects=True)
    assert r3.status_code == 200

    db.session.expire_all()
    t_updated = Tenant.query.get(tenant.id)
    assert t_updated.name == "Kenyatta Supermarket"
    assert t_updated.vat_enabled is True
    assert t_updated.vat_rate == Decimal("16.00")

    # 4. Owner creates new cashier
    new_staff_data = {
        "full_name": "Kelvin Staff",
        "email": "kelvin@x.com",
        "password": "kelvinpassword",
        "role": "cashier"
    }
    r4 = client.post("/tenant/users/new", data=new_staff_data, follow_redirects=True)
    assert r4.status_code == 200

    db.session.expire_all()
    k_staff = User.query.filter_by(tenant_id=tenant.id, email="kelvin@x.com").first()
    assert k_staff is not None
    assert k_staff.role == "cashier"

    # Logout owner
    client.get("/logout")

    # Check new cashier can login
    login_resp = login_as(client, tenant.id, "kelvin@x.com", "kelvinpassword")
    assert login_resp.status_code in (302, 303)
    client.get("/logout")

    # Log back in as owner to delete
    login_as(client, tenant.id, owner.email, "pass123")

    # 5. Delete staff member
    r5 = client.post(f"/tenant/users/delete/{k_staff.id}", follow_redirects=True)
    assert r5.status_code == 200

    db.session.expire_all()
    deleted_staff = User.query.filter_by(tenant_id=tenant.id, email="kelvin@x.com").first()
    assert deleted_staff is None


