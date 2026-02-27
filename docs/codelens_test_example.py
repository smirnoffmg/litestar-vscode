"""
Minimal example to test CodeLens for Test Client.

1. Put this file in a Litestar project (or ensure litestar is installed).
2. Open it in VS Code with the Litestar extension enabled.
3. Ensure the Litestar language server is running (Python interpreter selected).
4. You should see "Go to handler: ..." links above each client.get/post/... line.
   Click a link to jump to the route handler.

Run tests: pytest docs/codelens_test_example.py -v
"""

from litestar import get, post, Litestar
from litestar.testing import create_test_client


# --- App and routes (CodeLens will jump to these handlers) ---


@get("/health")
async def health() -> dict:
    """Health check."""
    return {"status": "ok"}


@get("/items")
async def list_items() -> list[dict]:
    """List items."""
    return []


@post("/items")
async def create_item(data: dict) -> dict:
    """Create item."""
    return data


app = Litestar(route_handlers=[health, list_items, create_item])


# --- Tests: CodeLens appears above each client.get/post line ---


def test_health() -> None:
    with create_test_client(app) as client:
        # CodeLens: "Go to handler: health"
        response = client.get("/health")
        assert response.status_code == 200


def test_list_items() -> None:
    with create_test_client(app) as client:
        # CodeLens: "Go to handler: list_items"
        response = client.get("/items")
        assert response.status_code == 200


def test_create_item() -> None:
    with create_test_client(app) as client:
        # CodeLens: "Go to handler: create_item"
        response = client.post("/items", json={"name": "test"})
        assert response.status_code in (200, 201)
