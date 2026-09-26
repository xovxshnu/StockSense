import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import Contact, ContactType

FORBIDDEN_FIELDS = {
    "warehouse_id", "location_id", "product_id", "quantity", "stock",
    "reserved_quantity", "email", "phone",
}


@pytest.fixture
def api(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    client.headers.update(auth_headers)
    return client


def create(api: TestClient, **overrides):
    return api.post("/api/contacts", json={"name": "Acme", "type": "supplier"} | overrides)


def test_create_supplier(api: TestClient) -> None:
    response = create(api, address="1 Main St")
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Acme", "type": "supplier", "address": "1 Main St"}


def test_create_customer(api: TestClient) -> None:
    body = create(api, name="Globex", type="customer").json()
    assert body["type"] == "customer" and body["address"] is None


def test_list_contacts(api: TestClient) -> None:
    create(api, name="Zeta")
    create(api, name="Alpha", type="customer")
    response = api.get("/api/contacts")
    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Alpha", "Zeta"]


def test_get_contact(api: TestClient) -> None:
    contact_id = create(api).json()["id"]
    response = api.get(f"/api/contacts/{contact_id}")
    assert response.status_code == 200 and response.json()["name"] == "Acme"


def test_update_contact_is_partial(api: TestClient) -> None:
    contact_id = create(api, address="Old").json()["id"]
    response = api.put(f"/api/contacts/{contact_id}", json={"name": "Acme Ltd", "type": "customer"})
    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Acme Ltd" and body["type"] == "customer" and body["address"] == "Old"
    assert api.put(f"/api/contacts/{contact_id}", json={"address": None}).json()["address"] is None


@pytest.mark.parametrize("name", ["", "   ", None])
def test_blank_name_rejected(api: TestClient, name) -> None:
    assert create(api, name=name).status_code == 422
    contact_id = create(api).json()["id"]
    assert api.put(f"/api/contacts/{contact_id}", json={"name": name}).status_code == 422


@pytest.mark.parametrize("contact_type", ["vendor", "", "SUPPLIER", None])
def test_invalid_type_rejected(api: TestClient, contact_type) -> None:
    assert create(api, type=contact_type).status_code == 422
    contact_id = create(api).json()["id"]
    assert api.put(f"/api/contacts/{contact_id}", json={"type": contact_type}).status_code == 422


def test_missing_type_rejected(api: TestClient) -> None:
    assert api.post("/api/contacts", json={"name": "Acme"}).status_code == 422


def test_name_is_normalized(api: TestClient) -> None:
    assert create(api, name="  Acme Corp  ").json()["name"] == "Acme Corp"
    contact_id = create(api, name="X").json()["id"]
    assert api.put(f"/api/contacts/{contact_id}", json={"name": " Y "}).json()["name"] == "Y"


def test_address_is_normalized_and_blank_becomes_null(api: TestClient) -> None:
    assert create(api, address="  5 High St ").json()["address"] == "5 High St"
    for blank in ("", "   "):
        assert create(api, address=blank).json()["address"] is None
    contact_id = create(api, address="Old").json()["id"]
    assert api.put(f"/api/contacts/{contact_id}", json={"address": "  "}).json()["address"] is None


def test_filter_by_type(api: TestClient) -> None:
    create(api, name="S1")
    create(api, name="S2")
    create(api, name="C1", type="customer")
    suppliers = api.get("/api/contacts", params={"type": "supplier"}).json()
    customers = api.get("/api/contacts", params={"type": "customer"}).json()
    assert [c["name"] for c in suppliers] == ["S1", "S2"]
    assert [c["name"] for c in customers] == ["C1"]
    assert len(api.get("/api/contacts").json()) == 3


def test_filter_by_invalid_type_rejected(api: TestClient) -> None:
    assert api.get("/api/contacts", params={"type": "vendor"}).status_code == 422


def test_missing_contact_returns_404(api: TestClient) -> None:
    assert api.get("/api/contacts/999").status_code == 404
    assert api.put("/api/contacts/999", json={"name": "X"}).status_code == 404


def test_auth_required(client: TestClient) -> None:
    assert client.get("/api/contacts").status_code == 401
    assert client.post("/api/contacts", json={}).status_code == 401
    assert client.get("/api/contacts/1").status_code == 401
    assert client.put("/api/contacts/1", json={}).status_code == 401


def test_duplicate_names_allowed(api: TestClient) -> None:
    assert create(api).status_code == 201
    assert create(api).status_code == 201


def test_supplier_and_customer_can_share_a_name(api: TestClient) -> None:
    assert create(api, type="supplier").status_code == 201
    assert create(api, type="customer").status_code == 201


def test_db_rejects_invalid_type(db: Session) -> None:
    with pytest.raises(DBAPIError):
        db.execute(text("INSERT INTO contacts (name, type) VALUES ('Bad', 'vendor')"))
    db.rollback()


def test_db_rejects_null_and_blank_values(db: Session) -> None:
    for sql in (
        "INSERT INTO contacts (name, type) VALUES (NULL, 'supplier')",
        "INSERT INTO contacts (name, type) VALUES ('Ok', NULL)",
        "INSERT INTO contacts (name, type) VALUES ('   ', 'supplier')",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()


def test_orm_round_trip_uses_enum(db: Session) -> None:
    db.add(Contact(name="Acme", type=ContactType.CUSTOMER))
    db.commit()
    assert db.query(Contact).one().type is ContactType.CUSTOMER


def test_contact_has_exactly_the_master_data_fields(api: TestClient) -> None:
    columns = {c.key for c in inspect(Contact).columns}
    assert columns == {"id", "name", "type", "address"}
    assert FORBIDDEN_FIELDS.isdisjoint(columns)
    assert set(create(api).json()) == columns


def test_extra_fields_rejected(api: TestClient) -> None:
    assert create(api, phone="123").status_code == 422
    assert create(api, warehouse_id=1).status_code == 422
