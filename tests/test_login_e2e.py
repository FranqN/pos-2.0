import io
import pytest

from app import create_app
from app.extensions import db
from app.models import Tenant, User


@pytest.mark.usefixtures("client")
def test_create_tenant_then_login_owner(client):
    # Create tenant with owner credentials via POST /tenant/create
    data = {
        "name": "Test Store",
        "phone": "020-000000",
        "email": "store@example.com",
        "address": "Nairobi CBD",
        "admin_email": "owner@example.com",
        "admin_password": "StrongPassword123",
        # logo is optional
    }

    resp = client.post("/tenant/create", data=data, follow_redirects=True)
    assert resp.status_code in (200, 302)

    with create_app().app_context():
        tenant = Tenant.query.filter_by(email="store@example.com").first()
        assert tenant is not None

        user = User.query.filter_by(tenant_id=tenant.id, email="owner@example.com").first()
        assert user is not None
        assert user.check_password("StrongPassword123")

    # Login as owner
    login_resp = client.post(
        "/login",
        data={
            "tenant_id": str(tenant.id),
            "email": "owner@example.com",
            "password": "StrongPassword123",
        },
        follow_redirects=True,
    )

    assert login_resp.status_code == 200
    # Protected page should render
    assert b"Checkout" in login_resp.data or b"checkout" in login_resp.data

