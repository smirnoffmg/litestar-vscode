"""Unit tests for the workspace index."""

import sys
from pathlib import Path

TOOL_DIR = Path(__file__).parent.parent.parent.parent / "bundled" / "tool"
sys.path.insert(0, str(TOOL_DIR))

from workspace_index import WorkspaceIndex, route_tree_to_dict  # noqa: E402


def test_build_route_tree_single_file():
    source = """
from litestar import get, Controller, Router, Litestar

@get("/health")
async def health_check() -> dict:
    ...

class ItemController(Controller):
    path = "/items"

    @get()
    async def list_items(self) -> list[dict]:
        ...

router = Router(path="/api", route_handlers=[ItemController])

app = Litestar(route_handlers=[router, health_check])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    tree = idx.build_route_tree()

    assert len(tree) == 1
    app_node = tree[0]
    assert app_node.kind == "app"
    assert len(app_node.children) == 2

    router_node = app_node.children[0]
    assert router_node.kind == "router"
    assert router_node.full_path == "/api"

    ctrl_node = router_node.children[0]
    assert ctrl_node.kind == "controller"
    assert ctrl_node.full_path == "/api/items"

    handler_node = ctrl_node.children[0]
    assert handler_node.kind == "handler"
    assert handler_node.full_path == "/api/items"
    assert handler_node.http_methods == ["GET"]

    health_node = app_node.children[1]
    assert health_node.kind == "handler"
    assert health_node.full_path == "/health"


def test_build_route_tree_no_app():
    """When no Litestar app is found, show a flat listing."""
    source = """
from litestar import get

@get("/items")
async def list_items() -> list[dict]:
    ...
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///handlers.py", source)
    tree = idx.build_route_tree()

    assert len(tree) == 1
    assert tree[0].kind == "handler"
    assert tree[0].full_path == "/items"


def test_build_route_tree_cross_file():
    """Route handlers from different files are linked together."""
    controller_src = """
from litestar import Controller, get

class UserController(Controller):
    path = "/users"

    @get()
    async def list_users(self) -> list[dict]:
        ...
"""
    app_src = """
from litestar import Litestar, Router

router = Router(path="/api", route_handlers=[UserController])
app = Litestar(route_handlers=[router])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///controllers.py", controller_src)
    idx.update_file("file:///main.py", app_src)
    tree = idx.build_route_tree()

    assert len(tree) == 1
    app_node = tree[0]
    router_node = app_node.children[0]
    assert router_node.full_path == "/api"

    ctrl_node = router_node.children[0]
    assert ctrl_node.kind == "controller"
    assert ctrl_node.full_path == "/api/users"


def test_resolved_routes():
    source = """
from litestar import get, post, Controller, Litestar

class ItemController(Controller):
    path = "/items"

    @get()
    async def list_items(self) -> list[dict]:
        ...

    @post()
    async def create_item(self, data: dict) -> dict:
        ...

app = Litestar(route_handlers=[ItemController])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    routes = idx.build_resolved_routes()

    assert len(routes) == 2
    paths = {(r.http_methods[0], r.full_path) for r in routes}
    assert ("GET", "/items") in paths
    assert ("POST", "/items") in paths


def test_route_tree_to_dict_serialization():
    source = """
from litestar import get, Litestar

@get("/hello")
async def hello() -> str:
    ...

app = Litestar(route_handlers=[hello])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    tree = idx.build_route_tree()
    data = route_tree_to_dict(tree)

    assert isinstance(data, list)
    assert data[0]["kind"] == "app"
    assert data[0]["children"][0]["kind"] == "handler"
    assert data[0]["children"][0]["fullPath"] == "/hello"
    assert data[0]["children"][0]["httpMethods"] == ["GET"]


def test_remove_file():
    source = """
from litestar import get

@get("/items")
async def list_items() -> list[dict]:
    ...
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    assert len(idx.get_all_handlers()) == 1

    idx.remove_file("file:///app.py")
    assert len(idx.get_all_handlers()) == 0


def test_incremental_update():
    source_v1 = """
from litestar import get

@get("/items")
async def list_items() -> list[dict]:
    ...
"""
    source_v2 = """
from litestar import get, post

@get("/items")
async def list_items() -> list[dict]:
    ...

@post("/items")
async def create_item(data: dict) -> dict:
    ...
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source_v1)
    assert len(idx.get_all_handlers()) == 1

    idx.update_file("file:///app.py", source_v2)
    assert len(idx.get_all_handlers()) == 2
