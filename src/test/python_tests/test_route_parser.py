"""Unit tests for the AST-based route parser."""

import sys
from pathlib import Path

# Add bundled/tool to the path so we can import the parser directly.
TOOL_DIR = Path(__file__).parent.parent.parent.parent / "bundled" / "tool"
sys.path.insert(0, str(TOOL_DIR))

from route_parser import parse_file  # noqa: E402


def test_parse_standalone_handlers():
    source = """
from litestar import get, post

@get("/items")
async def list_items() -> list[dict]:
    ...

@post("/items")
async def create_item(data: dict) -> dict:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.handlers) == 2

    h1 = result.handlers[0]
    assert h1.name == "list_items"
    assert h1.http_methods == ["GET"]
    assert h1.path == "/items"
    assert h1.is_async is True
    assert h1.return_type == "list[dict]"

    h2 = result.handlers[1]
    assert h2.name == "create_item"
    assert h2.http_methods == ["POST"]
    assert h2.path == "/items"
    assert h2.return_type == "dict"


def test_parse_controller():
    source = """
from litestar import Controller, get, post

class ItemController(Controller):
    path = "/items"

    @get()
    async def list_items(self) -> list[dict]:
        ...

    @post()
    async def create_item(self, data: dict) -> dict:
        ...
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.controllers) == 1
    assert len(result.handlers) == 0

    ctrl = result.controllers[0]
    assert ctrl.name == "ItemController"
    assert ctrl.path == "/items"
    assert len(ctrl.handlers) == 2
    assert ctrl.handlers[0].name == "list_items"
    assert ctrl.handlers[1].name == "create_item"


def test_parse_router():
    source = """
from litestar import Router
from litestar.di import Provide

router = Router(
    path="/api",
    route_handlers=[ItemController],
    guards=[auth_guard],
    dependencies={"db": Provide(get_db)},
)
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.routers) == 1

    r = result.routers[0]
    assert r.variable_name == "router"
    assert r.path == "/api"
    assert r.route_handler_names == ["ItemController"]
    assert r.guards == ["auth_guard"]
    assert r.dependencies == {"db": "get_db"}


def test_parse_app():
    source = """
from litestar import Litestar
from litestar.di import Provide

app = Litestar(
    route_handlers=[item_router, health_check],
    dependencies={"settings": Provide(get_settings)},
    guards=[auth_guard],
)
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.apps) == 1

    app = result.apps[0]
    assert app.variable_name == "app"
    assert app.route_handler_names == ["item_router", "health_check"]
    assert app.dependencies == {"settings": "get_settings"}
    assert app.guards == ["auth_guard"]


def test_parse_missing_return_type():
    source = """
from litestar import get

@get("/items")
async def list_items():
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.handlers) == 1
    assert result.handlers[0].return_type is None


def test_parse_sync_handler():
    source = """
from litestar import get

@get("/items")
def list_items() -> list[dict]:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.handlers) == 1
    assert result.handlers[0].is_async is False
    assert result.handlers[0].sync_to_thread is False


def test_parse_sync_handler_with_sync_to_thread():
    source = """
from litestar import get

@get("/items", sync_to_thread=True)
def list_items() -> list[dict]:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.handlers) == 1
    assert result.handlers[0].sync_to_thread is True


def test_parse_route_decorator():
    source = """
from litestar import route

@route("/items", http_method=["GET", "POST"])
async def handle_items() -> dict:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert len(result.handlers) == 1
    h = result.handlers[0]
    assert h.http_methods == ["GET", "POST"]


def test_parse_syntax_error_returns_empty():
    source = "def broken(:\n    pass"
    result = parse_file(source, "file:///bad.py")
    assert len(result.handlers) == 0
    assert len(result.controllers) == 0
    assert len(result.routers) == 0
    assert len(result.apps) == 0


def test_parse_handler_with_path_kwarg():
    source = """
from litestar import get

@get(path="/items/{item_id:int}")
async def get_item(item_id: int) -> dict:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert result.handlers[0].path == "/items/{item_id:int}"
