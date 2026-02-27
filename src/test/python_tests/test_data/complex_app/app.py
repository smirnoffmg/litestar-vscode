"""Complex single-file Litestar app for testing all extension features.

Covers: Route Explorer, Route Search, Diagnostics (LITESTAR001–004),
Hover (deps, guards, paths), CodeLens (test client), multiple Litestar instances.
"""

from __future__ import annotations

from typing import Any

from litestar import (
    Controller,
    Litestar,
    Router,
    delete,
    get,
    patch,
    post,
    put,
)
from litestar.di import Provide
from litestar.testing import create_test_client

# -----------------------------------------------------------------------------
# Dependencies (for Route Explorer + Hover dependency chain)
# -----------------------------------------------------------------------------


def get_db() -> Any:
    """App-level DB dependency (shadowed by router for LITESTAR003)."""
    ...


def get_user() -> Any:
    """User service dependency."""
    ...


def get_request_id() -> str:
    """Request-scoped ID."""
    ...


# -----------------------------------------------------------------------------
# Guards (correct + wrong signature for LITESTAR004)
# -----------------------------------------------------------------------------


def app_guard(connection: Any, route_handler: Any) -> None:
    """Valid guard: (connection, route_handler)."""
    ...


def bad_guard() -> None:
    """Invalid guard: no params → LITESTAR004 diagnostic."""
    ...


def router_guard(connection: Any, route_handler: Any) -> None:
    """Guard applied at router level."""
    ...


# -----------------------------------------------------------------------------
# Standalone handlers
# -----------------------------------------------------------------------------


@get("/health")
async def health_check() -> dict[str, str]:
    """Health check — Route Explorer, Hover, CodeLens target."""
    return {"status": "ok"}


@get("/version")
async def version() -> dict[str, str]:
    """Version endpoint."""
    return {"version": "1.0.0"}


@get("/no-return")
async def missing_return() -> None:
    """LITESTAR001: missing return type (fix: add -> dict or -> None explicitly).
    We use -> None here so there is no diagnostic; use a handler without
    return type in another file to test LITESTAR001, or change this to no annotation.
    """
    ...


@get("/no-return-bad")
async def missing_return_bad():
    """LITESTAR001: Handler missing return type annotation."""
    return {"ok": True}


@post("/sync-endpoint")
def sync_handler_no_thread(data: dict[str, Any]) -> dict[str, Any]:
    """LITESTAR002: Sync handler without sync_to_thread."""
    return {"received": data}


@post("/sync-ok", sync_to_thread=True)
def sync_handler_ok(data: dict[str, Any]) -> dict[str, Any]:
    """Sync handler with sync_to_thread=True — no diagnostic."""
    return {"received": data}


# -----------------------------------------------------------------------------
# Controllers
# -----------------------------------------------------------------------------


class ItemController(Controller):
    """Items CRUD — multiple methods for Route Explorer + Search."""

    path = "/items"
    dependencies = {"request_id": Provide(get_request_id)}

    @get()
    async def list_items(self, db: Any = None) -> list[dict[str, Any]]:
        """List all items."""
        ...

    @post()
    async def create_item(self, data: dict[str, Any], db: Any = None) -> dict[str, Any]:
        """Create item."""
        ...

    @get("/{item_id:int}")
    async def get_item(self, item_id: int, db: Any = None) -> dict[str, Any] | None:
        """Get item by ID."""
        ...

    @put("/{item_id:int}")
    async def update_item(
        self, item_id: int, data: dict[str, Any], db: Any = None
    ) -> dict[str, Any]:
        """Update item."""
        ...

    @patch("/{item_id:int}")
    async def partial_update_item(
        self, item_id: int, data: dict[str, Any], db: Any = None
    ) -> dict[str, Any]:
        """Partial update."""
        ...

    @delete("/{item_id:int}")
    async def delete_item(self, item_id: int, db: Any = None) -> None:
        """Delete item."""
        ...


class UserController(Controller):
    """Users — for second router and guard chain in Hover."""

    path = "/users"
    dependencies = {"user_svc": Provide(get_user)}

    @get()
    async def list_users(self) -> list[dict[str, Any]]:
        """List users."""
        ...

    @get("/{user_id:int}")
    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Get user by ID."""
        ...


class AdminController(Controller):
    """Admin routes — nested under a router with guards."""

    path = "/admin"

    @get("/stats")
    async def stats(self) -> dict[str, Any]:
        """Admin stats."""
        ...

    @get("/config")
    async def config(self) -> dict[str, Any]:
        """Admin config."""
        ...


# -----------------------------------------------------------------------------
# Routers (with dependencies + guards; shadowed dep for LITESTAR003)
# -----------------------------------------------------------------------------

api_v1_router = Router(
    path="/api/v1",
    route_handlers=[ItemController],
    dependencies={"db": Provide(get_db)},  # shadowed by app-level "db" → LITESTAR003
    guards=[router_guard],
)

api_v2_router = Router(
    path="/api/v2",
    route_handlers=[UserController],
    dependencies={"request_id": Provide(get_request_id)},
    guards=[router_guard],
)

admin_router = Router(
    path="/internal",
    route_handlers=[AdminController],
    guards=[router_guard],
)

# -----------------------------------------------------------------------------
# Main app (two Litestar instances for Test 10: multiple apps in tree)
# -----------------------------------------------------------------------------

main_app = Litestar(
    route_handlers=[
        api_v1_router,
        api_v2_router,
        admin_router,
        health_check,
        version,
        missing_return_bad,
        sync_handler_no_thread,
        sync_handler_ok,
    ],
    dependencies={"db": Provide(get_db)},  # shadows router "db" → LITESTAR003
    guards=[app_guard, bad_guard],  # bad_guard → LITESTAR004
)


@get("/ping", sync_to_thread=True)
def ping() -> dict[str, bool]:
    """Ping for secondary app."""
    return {"pong": True}


# Second app: appears as separate root in Route Explorer (Test 10)
secondary_app = Litestar(route_handlers=[ping])


# -----------------------------------------------------------------------------
# Tests (CodeLens: "Go to handler: ..." above client.get/post)
# -----------------------------------------------------------------------------


def test_health() -> None:
    with create_test_client(main_app) as client:
        response = client.get("/health")
        assert response.status_code == 200


def test_version() -> None:
    with create_test_client(main_app) as client:
        response = client.get("/version")
        assert response.status_code == 200


def test_list_items() -> None:
    with create_test_client(main_app) as client:
        response = client.get("/api/v1/items")
        assert response.status_code in (200, 500)


def test_get_item() -> None:
    with create_test_client(main_app) as client:
        response = client.get("/api/v1/items/1")
        assert response.status_code in (200, 404, 500)


def test_create_item() -> None:
    with create_test_client(main_app) as client:
        response = client.post("/api/v1/items", json={"name": "x"})
        assert response.status_code in (200, 201, 500)


def test_list_users() -> None:
    with create_test_client(main_app) as client:
        response = client.get("/api/v2/users")
        assert response.status_code in (200, 500)


def test_admin_stats() -> None:
    with create_test_client(main_app) as client:
        response = client.get("/internal/admin/stats")
        assert response.status_code in (200, 500)


def test_ping_secondary() -> None:
    with create_test_client(secondary_app) as client:
        response = client.get("/ping")
        assert response.status_code == 200
