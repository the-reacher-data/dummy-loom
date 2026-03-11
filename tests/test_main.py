"""Integration scenarios for the dummy store API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import create_app


def _build_client(tmp_path: Path, monkeypatch: MonkeyPatch) -> TestClient:
    db_file = tmp_path / "store.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    # Run Celery tasks in-process with no external broker required
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")
    app = create_app()
    return TestClient(app)


def test_store_flow_user_address_product_order_order_item(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Should support the full store flow across main resources."""
    with _build_client(tmp_path, monkeypatch) as client:
        user_resp = client.post("/users/", json={"full_name": "Ana Demo", "email": "ana@example.com"})
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        address_resp = client.post(
            f"/users/{user_id}/addresses/",
            json={
                "label": "home",
                "street": "Main 1",
                "city": "Madrid",
                "country": "ES",
                "zip_code": "28001",
            },
        )
        assert address_resp.status_code == 201
        address_id = address_resp.json()["id"]

        product_resp = client.post(
            "/products/",
            json={
                "sku": "SKU-001",
                "name": "Keyboard",
                "category": "peripherals",
                "price_cents": 9900,
                "stock": 10,
            },
        )
        assert product_resp.status_code == 201
        product_id = product_resp.json()["id"]

        order_resp = client.post(
            "/orders/",
            json={"user_id": user_id, "address_id": address_id, "status": "created", "payment_method": "card"},
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["id"]

        item_resp = client.post(
            "/order-items/",
            json={"order_id": order_id, "product_id": product_id, "quantity": 2, "unit_price_cents": 9900},
        )
        assert item_resp.status_code == 201
        order_item_id = item_resp.json()["id"]

        get_order = client.get(f"/orders/{order_id}")
        assert get_order.status_code == 200
        assert get_order.json() is not None

        patch_user = client.patch(f"/users/{user_id}", json={"full_name": "Ana Updated"})
        assert patch_user.status_code == 200
        get_user = client.get(f"/users/{user_id}")
        assert get_user.status_code == 200
        assert get_user.json()["fullName"] == "Ana Updated"

        patch_address = client.patch(f"/users/{user_id}/addresses/{address_id}", json={"city": "Barcelona"})
        assert patch_address.status_code == 200
        get_address = client.get(f"/users/{user_id}/addresses/{address_id}")
        assert get_address.status_code == 200
        assert get_address.json()["city"] == "Barcelona"

        patch_order_item = client.patch(f"/order-items/{order_item_id}", json={"quantity": 3})
        assert patch_order_item.status_code == 200
        get_order_item = client.get(f"/order-items/{order_item_id}")
        assert get_order_item.status_code == 200
        assert get_order_item.json()["quantity"] == 3

        patch_order = client.patch(f"/orders/{order_id}", json={"status": "paid"})
        assert patch_order.status_code == 200
        get_order_updated = client.get(f"/orders/{order_id}")
        assert get_order_updated.status_code == 200
        assert get_order_updated.json()["status"] == "paid"

        delete_order_item = client.delete(f"/order-items/{order_item_id}")
        assert delete_order_item.status_code == 200
        assert delete_order_item.json() is True

        delete_order = client.delete(f"/orders/{order_id}")
        assert delete_order.status_code == 200
        assert delete_order.json() is True

        delete_address = client.delete(f"/users/{user_id}/addresses/{address_id}")
        assert delete_address.status_code == 200
        assert delete_address.json() is True

        delete_product = client.delete(f"/products/{product_id}")
        assert delete_product.status_code == 200
        assert delete_product.json() is True

        delete_user = client.delete(f"/users/{user_id}")
        assert delete_user.status_code == 200
        assert delete_user.json() is True


def test_products_list_cursor_pagination(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Products list should support cursor pagination."""
    with _build_client(tmp_path, monkeypatch) as client:
        for idx in range(3):
            response = client.post(
                "/products/",
                json={
                    "sku": f"SKU-{idx}",
                    "name": f"Product-{idx}",
                    "category": "cat",
                    "price_cents": 1000 + idx,
                    "stock": 5,
                },
            )
            assert response.status_code == 201

        first = client.get("/products/?pagination=cursor&limit=1&sort=id&direction=ASC")
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["has_next"] is True
        assert first_payload["next_cursor"] is not None

        cursor = first_payload["next_cursor"]
        second = client.get(f"/products/?pagination=cursor&after={cursor}&limit=1&sort=id&direction=ASC")
        assert second.status_code == 200
        second_payload = second.json()
        assert len(second_payload["items"]) == 1


def test_orders_list_offset_pagination_and_product_update(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Orders should support offset pagination and products should support update."""
    with _build_client(tmp_path, monkeypatch) as client:
        user_resp = client.post("/users/", json={"full_name": "Bob", "email": "bob@example.com"})
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        address_resp = client.post(
            f"/users/{user_id}/addresses/",
            json={
                "label": "work",
                "street": "Street 9",
                "city": "Lisbon",
                "country": "PT",
                "zip_code": "1000-001",
            },
        )
        assert address_resp.status_code == 201
        address_id = address_resp.json()["id"]

        product_resp = client.post(
            "/products/",
            json={
                "sku": "SKU-U1",
                "name": "Mouse",
                "category": "peripherals",
                "price_cents": 3000,
                "stock": 100,
            },
        )
        assert product_resp.status_code == 201
        product_id = product_resp.json()["id"]

        for _ in range(2):
            response = client.post(
                "/orders/",
                json={"user_id": user_id, "address_id": address_id, "status": "created", "payment_method": "card"},
            )
            assert response.status_code == 201

        paged = client.get("/orders/?limit=1&page=1&sort=id&direction=ASC")
        assert paged.status_code == 200
        payload = paged.json()
        assert payload["total_count"] == 2
        assert len(payload["items"]) == 1

        patch_resp = client.patch(f"/products/{product_id}", json={"stock": 80})
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched is not None
        assert patched["stock"] == 80


def test_user_validation_rules_for_email_and_name(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """User create/update should enforce name and email business rules."""
    with _build_client(tmp_path, monkeypatch) as client:
        invalid_email = client.post("/users/", json={"full_name": "Ana", "email": "invalid"})
        assert invalid_email.status_code == 422

        created = client.post("/users/", json={"full_name": "Ana", "email": "ana@demo.com"})
        assert created.status_code == 201
        user_id = created.json()["id"]

        duplicate = client.post("/users/", json={"full_name": "Ana 2", "email": "ana@demo.com"})
        assert duplicate.status_code == 422

        blank_name = client.patch(f"/users/{user_id}", json={"full_name": "   "})
        assert blank_name.status_code == 422


def test_restock_workflow_chains_use_cases_and_success_callback(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Workflow endpoint should run use-case chaining and success callback tagging."""
    with _build_client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/products/",
            json={
                "sku": "SKU-CB-OK",
                "name": "Cable",
                "category": "accessories",
                "price_cents": 1299,
                "stock": 0,
            },
        )
        assert created.status_code == 201
        product_id = created.json()["id"]

        workflow = client.post(
            f"/products/{product_id}/workflows/restock",
            json={
                "recipientEmail": "buyer@example.com",
                "forceFail": False,
            },
        )
        assert workflow.status_code == 202
        payload = workflow.json()
        assert payload["restockJobId"]
        assert payload["summary"]

        loaded = client.get(f"/products/{product_id}")
        assert loaded.status_code == 200
        assert loaded.json()["category"].startswith("accessories")


def test_restock_dispatch_failure_triggers_failure_callback_tag(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Dispatch with forced failure should mark product via failure callback."""
    with _build_client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/products/",
            json={
                "sku": "SKU-CB-FAIL",
                "name": "Adapter",
                "category": "gadgets",
                "price_cents": 2999,
                "stock": 0,
            },
        )
        assert created.status_code == 201
        product_id = created.json()["id"]

        dispatched = client.post(
            f"/products/{product_id}/jobs/restock-email",
            json={
                "recipientEmail": "ops@example.com",
                "forceFail": True,
            },
        )
        assert dispatched.status_code == 202

        loaded = client.get(f"/products/{product_id}")
        assert loaded.status_code == 200
        assert loaded.json()["category"].startswith("gadgets")


def test_user_update_email_uniqueness_and_delete_not_found(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """User update should enforce email uniqueness and return 404 after delete."""
    with _build_client(tmp_path, monkeypatch) as client:
        first = client.post("/users/", json={"full_name": "Ana", "email": "ana@demo.com"})
        assert first.status_code == 201
        user_id = first.json()["id"]

        second = client.post("/users/", json={"full_name": "Pepe", "email": "pepe@demo.com"})
        assert second.status_code == 201

        update_duplicate = client.patch(f"/users/{user_id}", json={"email": "pepe@demo.com"})
        assert update_duplicate.status_code == 422

        update_same_email = client.patch(f"/users/{user_id}", json={"email": "ana@demo.com"})
        assert update_same_email.status_code == 200
        assert update_same_email.json()["email"] == "ana@demo.com"

        update_new_email = client.patch(f"/users/{user_id}", json={"email": "ana.new@demo.com"})
        assert update_new_email.status_code == 200
        assert update_new_email.json()["email"] == "ana.new@demo.com"

        deleted = client.delete(f"/users/{user_id}")
        assert deleted.status_code == 200
        assert deleted.json() is True

        missing_after_delete = client.get(f"/users/{user_id}")
        assert missing_after_delete.status_code == 404


def test_products_low_stock_endpoint_with_cache_enabled(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Low stock endpoint should work while product repository cache is enabled."""
    monkeypatch.setenv("CACHE_ENABLED", "true")
    monkeypatch.setenv("CACHE_BACKEND", "memory")

    with _build_client(tmp_path, monkeypatch) as client:
        payloads = [
            {"sku": "L-1", "name": "A", "category": "x", "price_cents": 100, "stock": 2},
            {"sku": "L-2", "name": "B", "category": "x", "price_cents": 100, "stock": 9},
            {"sku": "L-3", "name": "C", "category": "x", "price_cents": 100, "stock": 5},
        ]
        for payload in payloads:
            created = client.post("/products/", json=payload)
            assert created.status_code == 201

        response = client.get("/products/low-stock?max_stock=5&limit=10")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 2
        assert [item["stock"] for item in items] == [2, 5]


def test_order_create_returns_404_when_user_or_address_missing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Order create should fail with 404 if foreign references do not exist."""
    with _build_client(tmp_path, monkeypatch) as client:
        missing_user = client.post(
            "/orders/",
            json={"user_id": 999, "address_id": 1, "status": "created", "payment_method": "card"},
        )
        assert missing_user.status_code == 404

        user_resp = client.post("/users/", json={"full_name": "Order User", "email": "order.user@example.com"})
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        missing_address = client.post(
            "/orders/",
            json={"user_id": user_id, "address_id": 999, "status": "created", "payment_method": "card"},
        )
        assert missing_address.status_code == 404


def test_order_item_create_returns_404_when_order_or_product_missing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Order item create should fail with 404 if order or product does not exist."""
    with _build_client(tmp_path, monkeypatch) as client:
        missing_order = client.post(
            "/order-items/",
            json={"order_id": 999, "product_id": 1, "quantity": 1, "unit_price_cents": 1000},
        )
        assert missing_order.status_code == 404

        user_resp = client.post("/users/", json={"full_name": "Item User", "email": "item.user@example.com"})
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        address_resp = client.post(
            f"/users/{user_id}/addresses/",
            json={
                "label": "home",
                "street": "Street 1",
                "city": "Madrid",
                "country": "ES",
                "zip_code": "28001",
            },
        )
        assert address_resp.status_code == 201
        address_id = address_resp.json()["id"]

        order_resp = client.post(
            "/orders/",
            json={"user_id": user_id, "address_id": address_id, "status": "created", "payment_method": "card"},
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["id"]

        missing_product = client.post(
            "/order-items/",
            json={"order_id": order_id, "product_id": 999, "quantity": 1, "unit_price_cents": 1000},
        )
        assert missing_product.status_code == 404
