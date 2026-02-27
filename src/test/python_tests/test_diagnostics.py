"""Unit tests for Litestar diagnostics (LITESTAR001–004)."""

import sys
from pathlib import Path

TOOL_DIR = Path(__file__).parent.parent.parent.parent / "bundled" / "tool"
sys.path.insert(0, str(TOOL_DIR))

from diagnostics import DiagnosticIssue, detect_issues  # noqa: E402
from route_parser import parse_file  # noqa: E402
from workspace_index import WorkspaceIndex  # noqa: E402


def _codes(issues: list[DiagnosticIssue]) -> list[str]:
    return [issue.code for issue in issues]


# ---- LITESTAR001: missing return type ----


def test_litestar001_fires_on_missing_return_type():
    source = """
from litestar import get

@get("/items")
async def list_items():
    ...
"""
    result = parse_file(source, "file:///test.py")
    issues = detect_issues(result)
    assert "LITESTAR001" in _codes(issues)


def test_litestar001_does_not_fire_with_return_type():
    source = """
from litestar import get

@get("/items")
async def list_items() -> list[dict]:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert "LITESTAR001" not in _codes(detect_issues(result))


def test_litestar001_fires_on_controller_handler():
    source = """
from litestar import Controller, get

class MyCtrl(Controller):
    path = "/x"

    @get()
    async def no_ret(self):
        ...
"""
    result = parse_file(source, "file:///test.py")
    assert "LITESTAR001" in _codes(detect_issues(result))


# ---- LITESTAR002: sync handler without sync_to_thread ----


def test_litestar002_fires_on_sync_handler():
    source = """
from litestar import post

@post("/items")
def create_item(data: dict) -> dict:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert "LITESTAR002" in _codes(detect_issues(result))


def test_litestar002_does_not_fire_on_async():
    source = """
from litestar import post

@post("/items")
async def create_item(data: dict) -> dict:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert "LITESTAR002" not in _codes(detect_issues(result))


def test_litestar002_does_not_fire_with_sync_to_thread():
    source = """
from litestar import post

@post("/items", sync_to_thread=True)
def create_item(data: dict) -> dict:
    ...
"""
    result = parse_file(source, "file:///test.py")
    assert "LITESTAR002" not in _codes(detect_issues(result))


# ---- LITESTAR003: shadowed dependency ----


def test_litestar003_fires_on_shadowed_dependency():
    """A dependency key defined at both app and router level should warn."""
    source = """
from litestar import get, Router, Litestar
from litestar.di import Provide

@get()
async def handler() -> dict:
    ...

router = Router(
    path="/api",
    route_handlers=[handler],
    dependencies={"db": Provide(get_db_override)},
)

app = Litestar(
    route_handlers=[router],
    dependencies={"db": Provide(get_db)},
)
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR003" in _codes(issues)


def test_litestar003_message_mentions_layers():
    source = """
from litestar import get, Router, Litestar
from litestar.di import Provide

@get()
async def handler() -> dict:
    ...

router = Router(
    path="/api",
    route_handlers=[handler],
    dependencies={"db": Provide(get_db_override)},
)

app = Litestar(
    route_handlers=[router],
    dependencies={"db": Provide(get_db)},
)
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    shadow_issues = [i for i in issues if i.code == "LITESTAR003"]
    assert len(shadow_issues) >= 1
    assert "db" in shadow_issues[0].message


def test_litestar003_does_not_fire_without_shadow():
    source = """
from litestar import get, Router, Litestar
from litestar.di import Provide

@get()
async def handler() -> dict:
    ...

router = Router(
    path="/api",
    route_handlers=[handler],
    dependencies={"cache": Provide(get_cache)},
)

app = Litestar(
    route_handlers=[router],
    dependencies={"db": Provide(get_db)},
)
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR003" not in _codes(issues)


# ---- LITESTAR004: guard with wrong signature ----


def test_litestar004_fires_on_guard_with_zero_params():
    source = """
from litestar import get, Litestar

def bad_guard():
    ...

@get("/items")
async def handler() -> dict:
    ...

app = Litestar(route_handlers=[handler], guards=[bad_guard])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR004" in _codes(issues)


def test_litestar004_fires_on_guard_with_one_param():
    source = """
from litestar import get, Litestar

def bad_guard(connection):
    ...

@get("/items")
async def handler() -> dict:
    ...

app = Litestar(route_handlers=[handler], guards=[bad_guard])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR004" in _codes(issues)


def test_litestar004_does_not_fire_on_valid_guard():
    source = """
from litestar import get, Litestar

def good_guard(connection, route_handler):
    ...

@get("/items")
async def handler() -> dict:
    ...

app = Litestar(route_handlers=[handler], guards=[good_guard])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR004" not in _codes(issues)


def test_litestar004_fires_on_controller_guard():
    source = """
from litestar import get, Controller, Litestar

def bad_guard():
    ...

class MyController(Controller):
    path = "/items"
    guards = [bad_guard]

    @get()
    async def handler(self) -> dict:
        ...

app = Litestar(route_handlers=[MyController])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR004" in _codes(issues)


def test_litestar004_guard_not_defined_in_file_is_skipped():
    """If a guard name can't be found as a function definition, don't crash."""
    source = """
from litestar import get, Litestar

@get("/items")
async def handler() -> dict:
    ...

app = Litestar(route_handlers=[handler], guards=[external_guard])
"""
    idx = WorkspaceIndex()
    idx.update_file("file:///app.py", source)
    issues = detect_issues(
        idx.get_file_result("file:///app.py"),
        workspace_index=idx,
    )
    assert "LITESTAR004" not in _codes(issues)
