"""Dependency injection and guard chain resolution for Litestar's layered architecture."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DependencyLayer:
    """Dependencies defined at a single layer in the hierarchy."""

    layer_kind: str  # "app", "router", "controller", "handler"
    layer_name: str
    dependencies: dict[str, str] = field(default_factory=dict)


@dataclass
class ResolvedDependencyChain:
    """Full resolved dependency chain from app -> router -> controller -> handler."""

    layers: list[DependencyLayer] = field(default_factory=list)
    effective: dict[str, DependencyLayer] = field(default_factory=dict)
    shadowed: list[tuple[str, DependencyLayer, DependencyLayer]] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "layers": [],
            "effective": {},
            "shadowed": [],
        }
        for layer in self.layers:
            result["layers"].append(
                {
                    "layerKind": layer.layer_kind,
                    "layerName": layer.layer_name,
                    "dependencies": layer.dependencies,
                }
            )
        for key, layer in self.effective.items():
            result["effective"][key] = {
                "provider": layer.dependencies.get(key, "unknown"),
                "layerKind": layer.layer_kind,
                "layerName": layer.layer_name,
            }
        for key, outer, inner in self.shadowed:
            result["shadowed"].append(
                {
                    "key": key,
                    "shadowedBy": {
                        "layerKind": inner.layer_kind,
                        "layerName": inner.layer_name,
                    },
                    "originalFrom": {
                        "layerKind": outer.layer_kind,
                        "layerName": outer.layer_name,
                    },
                }
            )
        return result


def resolve_dependency_chain(layers: list[dict[str, Any]]) -> ResolvedDependencyChain:
    """Resolve a dependency chain, detecting shadowing.

    Args:
        layers: List of dicts with keys "layer", "label", "dependencies"
                as returned by WorkspaceIndex.get_dependencies_for_handler.
    """
    chain = ResolvedDependencyChain()

    for raw in layers:
        dl = DependencyLayer(
            layer_kind=raw["layer"],
            layer_name=raw["label"],
            dependencies=raw.get("dependencies", {}),
        )
        chain.layers.append(dl)

    for layer in chain.layers:
        for key in layer.dependencies:
            if key in chain.effective:
                prev = chain.effective[key]
                chain.shadowed.append((key, prev, layer))
            chain.effective[key] = layer

    return chain


@dataclass
class GuardLayer:
    """Guards defined at a single layer in the hierarchy."""

    layer_kind: str
    layer_name: str
    guards: list[str] = field(default_factory=list)


@dataclass
class ResolvedGuardChain:
    """Full cumulative guard chain."""

    layers: list[GuardLayer] = field(default_factory=list)
    all_guards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layers": [
                {
                    "layerKind": gl.layer_kind,
                    "layerName": gl.layer_name,
                    "guards": gl.guards,
                }
                for gl in self.layers
            ],
            "allGuards": self.all_guards,
        }


def resolve_guard_chain(layers: list[dict[str, Any]]) -> ResolvedGuardChain:
    """Resolve a guard chain from layered data.

    Args:
        layers: List of dicts with keys "layer", "label", "guards"
                as returned by WorkspaceIndex.get_guards_for_handler.
    """
    chain = ResolvedGuardChain()

    for raw in layers:
        gl = GuardLayer(
            layer_kind=raw["layer"],
            layer_name=raw["label"],
            guards=raw.get("guards", []),
        )
        chain.layers.append(gl)
        chain.all_guards.extend(gl.guards)

    return chain


def validate_guard_signature(source: str, guard_name: str) -> str | None:
    """Validate that a guard function has the correct signature.

    Guards must accept (connection, route_handler) as parameters.
    Returns an error message if invalid, None if valid.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == guard_name:
                params = [arg.arg for arg in node.args.args if arg.arg != "self"]
                if len(params) < 2:
                    return (
                        f"Guard '{guard_name}' must accept at least 2 parameters "
                        f"(connection, route_handler), but has {len(params)}."
                    )
                return None

    return None
