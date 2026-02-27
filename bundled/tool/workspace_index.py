"""Workspace-level index that aggregates per-file parse results into a full route tree."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

from route_parser import (
    AppInfo,
    ControllerInfo,
    FileParseResult,
    HandlerInfo,
    RouterInfo,
    parse_file,
)


@dataclass
class ResolvedRoute:
    """A fully resolved route with its absolute path and location info."""

    http_methods: list[str]
    full_path: str
    handler_name: str
    line: int
    col: int
    end_line: int
    uri: str
    return_type: str | None = None
    is_async: bool = False
    sync_to_thread: bool = False
    parameters: list[str] = field(default_factory=list)


@dataclass
class RouteTreeNode:
    """A node in the hierarchical route tree sent to the client."""

    kind: str  # "app", "router", "controller", "handler"
    label: str
    path: str
    full_path: str = ""
    http_methods: list[str] = field(default_factory=list)
    line: int = 0
    end_line: int = 0
    uri: str = ""
    children: list[RouteTreeNode] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)


def _normalize_path(path: str) -> str:
    """Normalize a route path segment."""
    path = path.strip("/")
    return f"/{path}" if path else ""


def _join_paths(*parts: str) -> str:
    """Join route path segments, avoiding double slashes."""
    combined = ""
    for part in parts:
        normalized = _normalize_path(part)
        combined = combined.rstrip("/") + normalized
    return combined or "/"


class WorkspaceIndex:
    """Maintains an index of all Litestar constructs across the workspace."""

    def __init__(self) -> None:
        self._file_results: dict[str, FileParseResult] = {}
        self._file_sources: dict[str, str] = {}
        self._workspace_roots: list[str] = []

    def set_workspace_roots(self, roots: list[str]) -> None:
        self._workspace_roots = roots

    def update_file(self, uri: str, source: str) -> FileParseResult:
        """Parse or re-parse a file and update the index."""
        result = parse_file(source, uri)
        self._file_results[uri] = result
        self._file_sources[uri] = source
        return result

    def remove_file(self, uri: str) -> None:
        """Remove a file from the index."""
        self._file_results.pop(uri, None)
        self._file_sources.pop(uri, None)

    def get_file_result(self, uri: str) -> FileParseResult | None:
        return self._file_results.get(uri)

    def scan_workspace(self, root_path: str) -> None:
        """Scan all Python files in a workspace root directory."""
        root = pathlib.Path(root_path)
        if not root.is_dir():
            return
        for py_file in root.rglob("*.py"):
            if _should_skip(py_file, root):
                continue
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            uri = py_file.as_uri()
            self.update_file(uri, source)

    def get_all_handlers(self) -> list[HandlerInfo]:
        """Return all standalone handlers across all files."""
        handlers = []
        for result in self._file_results.values():
            handlers.extend(result.handlers)
        return handlers

    def get_all_controllers(self) -> list[ControllerInfo]:
        controllers = []
        for result in self._file_results.values():
            controllers.extend(result.controllers)
        return controllers

    def get_all_routers(self) -> list[RouterInfo]:
        routers = []
        for result in self._file_results.values():
            routers.extend(result.routers)
        return routers

    def get_all_apps(self) -> list[AppInfo]:
        apps = []
        for result in self._file_results.values():
            apps.extend(result.apps)
        return apps

    def build_route_tree(self) -> list[RouteTreeNode]:
        """Build the full hierarchical route tree.

        Walks: App -> route_handlers (routers, controllers, standalone handlers)
        and resolves full paths by concatenating parent paths.
        """
        name_to_controller: dict[str, ControllerInfo] = {}
        name_to_router: dict[str, RouterInfo] = {}
        name_to_handler: dict[str, HandlerInfo] = {}

        for result in self._file_results.values():
            for ctrl in result.controllers:
                name_to_controller[ctrl.name] = ctrl
            for router in result.routers:
                name_to_router[router.variable_name] = router
            for handler in result.handlers:
                name_to_handler[handler.name] = handler

        apps = self.get_all_apps()
        if not apps:
            return self._build_flat_tree(
                name_to_handler, name_to_controller, name_to_router
            )

        tree: list[RouteTreeNode] = []
        for app in apps:
            app_node = RouteTreeNode(
                kind="app",
                label=app.variable_name or "app",
                path="/",
                full_path="/",
                line=app.line,
                end_line=app.end_line,
                uri=app.uri,
                guards=app.guards,
                dependencies=app.dependencies,
            )
            for name in app.route_handler_names:
                child = self._resolve_route_handler(
                    name, "/", name_to_controller, name_to_router, name_to_handler
                )
                if child:
                    app_node.children.append(child)
            tree.append(app_node)
        return tree

    def _resolve_route_handler(
        self,
        name: str,
        parent_path: str,
        controllers: dict[str, ControllerInfo],
        routers: dict[str, RouterInfo],
        handlers: dict[str, HandlerInfo],
    ) -> RouteTreeNode | None:
        if name in routers:
            return self._build_router_node(
                routers[name], parent_path, controllers, routers, handlers
            )
        if name in controllers:
            return self._build_controller_node(controllers[name], parent_path)
        if name in handlers:
            return self._build_handler_node(handlers[name], parent_path)
        return None

    def _build_router_node(
        self,
        router: RouterInfo,
        parent_path: str,
        controllers: dict[str, ControllerInfo],
        routers: dict[str, RouterInfo],
        handlers: dict[str, HandlerInfo],
    ) -> RouteTreeNode:
        full_path = _join_paths(parent_path, router.path)
        node = RouteTreeNode(
            kind="router",
            label=router.variable_name or "router",
            path=router.path,
            full_path=full_path,
            line=router.line,
            end_line=router.end_line,
            uri=router.uri,
            guards=router.guards,
            dependencies=router.dependencies,
        )
        for name in router.route_handler_names:
            child = self._resolve_route_handler(
                name, full_path, controllers, routers, handlers
            )
            if child:
                node.children.append(child)
        return node

    def _build_controller_node(
        self,
        controller: ControllerInfo,
        parent_path: str,
    ) -> RouteTreeNode:
        full_path = _join_paths(parent_path, controller.path)
        node = RouteTreeNode(
            kind="controller",
            label=controller.name,
            path=controller.path,
            full_path=full_path,
            line=controller.line,
            end_line=controller.end_line,
            uri=controller.uri,
            guards=controller.guards,
            dependencies=controller.dependencies,
        )
        for handler in controller.handlers:
            node.children.append(self._build_handler_node(handler, full_path))
        return node

    def _build_handler_node(
        self,
        handler: HandlerInfo,
        parent_path: str,
    ) -> RouteTreeNode:
        full_path = _join_paths(parent_path, handler.path)
        return RouteTreeNode(
            kind="handler",
            label=handler.name,
            path=handler.path,
            full_path=full_path,
            http_methods=handler.http_methods,
            line=handler.line,
            end_line=handler.end_line,
            uri=handler.uri,
        )

    def _build_flat_tree(
        self,
        handlers: dict[str, HandlerInfo],
        controllers: dict[str, ControllerInfo],
        routers: dict[str, RouterInfo],
    ) -> list[RouteTreeNode]:
        """Fallback: when no App is found, show a flat list."""
        nodes: list[RouteTreeNode] = []
        for router in routers.values():
            nodes.append(
                self._build_router_node(router, "/", controllers, routers, handlers)
            )
        for ctrl in controllers.values():
            nodes.append(self._build_controller_node(ctrl, "/"))
        for handler in handlers.values():
            nodes.append(self._build_handler_node(handler, "/"))
        return nodes

    def build_resolved_routes(self) -> list[ResolvedRoute]:
        """Build a flat list of all resolved routes for searching."""
        routes: list[ResolvedRoute] = []
        tree = self.build_route_tree()
        self._collect_routes(tree, routes)
        return routes

    def _collect_routes(
        self, nodes: list[RouteTreeNode], out: list[ResolvedRoute]
    ) -> None:
        for node in nodes:
            if node.kind == "handler":
                out.append(
                    ResolvedRoute(
                        http_methods=node.http_methods,
                        full_path=node.full_path,
                        handler_name=node.label,
                        line=node.line,
                        col=0,
                        end_line=node.end_line,
                        uri=node.uri,
                    )
                )
            self._collect_routes(node.children, out)

    def get_dependencies_for_handler(self, uri: str, line: int) -> list[dict[str, Any]]:
        """Resolve the full dependency chain for a handler at the given position.

        Walks the layered hierarchy collecting dependencies at each level.
        """
        chain: list[dict[str, Any]] = []
        tree = self.build_route_tree()
        self._find_handler_deps(tree, uri, line, chain)
        return chain

    def _find_handler_deps(
        self,
        nodes: list[RouteTreeNode],
        uri: str,
        line: int,
        chain: list[dict[str, Any]],
    ) -> bool:
        for node in nodes:
            if node.kind == "handler" and node.uri == uri and node.line == line:
                return True
            if node.children:
                if self._find_handler_deps(node.children, uri, line, chain):
                    if node.dependencies:
                        chain.insert(
                            0,
                            {
                                "layer": node.kind,
                                "label": node.label,
                                "dependencies": node.dependencies,
                            },
                        )
                    return True
        return False

    def get_guards_for_handler(self, uri: str, line: int) -> list[dict[str, Any]]:
        """Resolve the full guard chain for a handler at the given position."""
        chain: list[dict[str, Any]] = []
        tree = self.build_route_tree()
        self._find_handler_guards(tree, uri, line, chain)
        return chain

    def _find_handler_guards(
        self,
        nodes: list[RouteTreeNode],
        uri: str,
        line: int,
        chain: list[dict[str, Any]],
    ) -> bool:
        for node in nodes:
            if node.kind == "handler" and node.uri == uri and node.line == line:
                return True
            if node.children:
                if self._find_handler_guards(node.children, uri, line, chain):
                    if node.guards:
                        chain.insert(
                            0,
                            {
                                "layer": node.kind,
                                "label": node.label,
                                "guards": node.guards,
                            },
                        )
                    return True
        return False


def route_tree_to_dict(nodes: list[RouteTreeNode]) -> list[dict[str, Any]]:
    """Serialize route tree nodes to dicts for JSON transport over LSP."""
    result = []
    for node in nodes:
        d: dict[str, Any] = {
            "kind": node.kind,
            "label": node.label,
            "path": node.path,
            "fullPath": node.full_path,
            "httpMethods": node.http_methods,
            "line": node.line,
            "endLine": node.end_line,
            "uri": node.uri,
            "guards": node.guards,
            "dependencies": node.dependencies,
        }
        if node.children:
            d["children"] = route_tree_to_dict(node.children)
        else:
            d["children"] = []
        result.append(d)
    return result


def _should_skip(path: pathlib.Path, root: pathlib.Path) -> bool:
    """Decide if a Python file should be skipped during workspace scanning."""
    parts = path.relative_to(root).parts
    skip_dirs = {
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
    }
    for part in parts:
        if part in skip_dirs or part.endswith(".egg-info"):
            return True
    return False
