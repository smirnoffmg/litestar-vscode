"""Unit tests for dependency_resolver — shadow detection and guard chain resolution."""

import sys
from pathlib import Path

TOOL_DIR = Path(__file__).parent.parent.parent.parent / "bundled" / "tool"
sys.path.insert(0, str(TOOL_DIR))

from dependency_resolver import resolve_dependency_chain  # noqa: E402
from dependency_resolver import resolve_guard_chain, validate_guard_signature

# ---- Shadow detection ----


def test_resolve_chain_detects_shadow():
    layers = [
        {"layer": "app", "label": "app", "dependencies": {"db": "get_db"}},
        {
            "layer": "router",
            "label": "api_router",
            "dependencies": {"db": "get_db_override"},
        },
    ]
    chain = resolve_dependency_chain(layers)

    assert len(chain.shadowed) == 1
    key, original, shadower = chain.shadowed[0]
    assert key == "db"
    assert original.layer_name == "app"
    assert shadower.layer_name == "api_router"

    assert chain.effective["db"].layer_name == "api_router"


def test_resolve_chain_no_shadow():
    layers = [
        {"layer": "app", "label": "app", "dependencies": {"db": "get_db"}},
        {
            "layer": "router",
            "label": "api_router",
            "dependencies": {"cache": "get_cache"},
        },
    ]
    chain = resolve_dependency_chain(layers)
    assert len(chain.shadowed) == 0
    assert "db" in chain.effective
    assert "cache" in chain.effective


def test_resolve_chain_to_dict():
    layers = [
        {"layer": "app", "label": "app", "dependencies": {"db": "get_db"}},
        {"layer": "router", "label": "r", "dependencies": {"db": "get_db_v2"}},
    ]
    chain = resolve_dependency_chain(layers)
    data = chain.to_dict()

    assert len(data["layers"]) == 2
    assert len(data["shadowed"]) == 1
    assert data["shadowed"][0]["key"] == "db"
    assert data["effective"]["db"]["provider"] == "get_db_v2"


# ---- Guard chain ----


def test_resolve_guard_chain():
    layers = [
        {"layer": "app", "label": "app", "guards": ["auth_guard"]},
        {"layer": "router", "label": "r", "guards": ["rate_limit"]},
    ]
    chain = resolve_guard_chain(layers)
    assert chain.all_guards == ["auth_guard", "rate_limit"]
    assert len(chain.layers) == 2


def test_resolve_guard_chain_to_dict():
    layers = [
        {"layer": "app", "label": "app", "guards": ["auth_guard"]},
    ]
    data = resolve_guard_chain(layers).to_dict()
    assert data["allGuards"] == ["auth_guard"]
    assert data["layers"][0]["layerKind"] == "app"


# ---- Guard signature validation ----


def test_validate_guard_valid_signature():
    source = """
def my_guard(connection, route_handler):
    ...
"""
    assert validate_guard_signature(source, "my_guard") is None


def test_validate_guard_zero_params():
    source = """
def my_guard():
    ...
"""
    msg = validate_guard_signature(source, "my_guard")
    assert msg is not None
    assert "at least 2 parameters" in msg


def test_validate_guard_one_param():
    source = """
def my_guard(connection):
    ...
"""
    msg = validate_guard_signature(source, "my_guard")
    assert msg is not None
    assert "at least 2 parameters" in msg


def test_validate_guard_not_found():
    source = """
def other_func():
    ...
"""
    assert validate_guard_signature(source, "missing_guard") is None


def test_validate_guard_three_params_ok():
    source = """
def my_guard(connection, route_handler, extra):
    ...
"""
    assert validate_guard_signature(source, "my_guard") is None
