"""AST-based parser for extracting Litestar routes, controllers, routers, and app instances."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

HANDLER_DECORATORS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "route"}
)

DECORATOR_TO_METHODS: dict[str, list[str]] = {
    "get": ["GET"],
    "post": ["POST"],
    "put": ["PUT"],
    "patch": ["PATCH"],
    "delete": ["DELETE"],
    "head": ["HEAD"],
}


@dataclass
class HandlerInfo:
    name: str
    http_methods: list[str]
    path: str
    line: int
    col: int
    end_line: int
    uri: str = ""
    return_type: str | None = None
    is_async: bool = False
    sync_to_thread: bool = False
    parameters: list[str] = field(default_factory=list)


@dataclass
class ControllerInfo:
    name: str
    path: str
    handlers: list[HandlerInfo] = field(default_factory=list)
    line: int = 0
    end_line: int = 0
    uri: str = ""
    guards: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)


@dataclass
class RouterInfo:
    variable_name: str
    path: str
    route_handler_names: list[str] = field(default_factory=list)
    line: int = 0
    end_line: int = 0
    uri: str = ""
    guards: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)


@dataclass
class AppInfo:
    variable_name: str
    route_handler_names: list[str] = field(default_factory=list)
    line: int = 0
    end_line: int = 0
    uri: str = ""
    guards: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)


@dataclass
class FileParseResult:
    uri: str
    handlers: list[HandlerInfo] = field(default_factory=list)
    controllers: list[ControllerInfo] = field(default_factory=list)
    routers: list[RouterInfo] = field(default_factory=list)
    apps: list[AppInfo] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)


def _get_string_value(node: ast.expr) -> str | None:
    """Extract a string constant from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_name(node: ast.expr) -> str | None:
    """Extract a name from a Name or Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _get_dotted_name(node: ast.expr) -> str | None:
    """Extract a dotted name like 'litestar.get' from an Attribute chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _get_dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def _extract_list_names(node: ast.expr) -> list[str]:
    """Extract names from a list literal, e.g. [ItemController, item_router]."""
    names: list[str] = []
    if isinstance(node, ast.List):
        for elt in node.elts:
            name = _get_name(elt)
            if name:
                names.append(name)
    return names


def _extract_dict_dependencies(node: ast.expr) -> dict[str, str]:
    """Extract dependencies from a dict literal like {"db": Provide(get_db)}."""
    deps: dict[str, str] = {}
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if key is None:
                continue
            key_str = _get_string_value(key)
            if key_str is None:
                continue
            if isinstance(value, ast.Call):
                func_name = _get_name(value.func)
                if func_name == "Provide" and value.args:
                    provider_name = _get_name(value.args[0])
                    if provider_name:
                        deps[key_str] = provider_name
                    else:
                        deps[key_str] = ast.dump(value.args[0])
                else:
                    deps[key_str] = _get_dotted_name(value.func) or "unknown"
            else:
                name = _get_name(value)
                if name:
                    deps[key_str] = name
    return deps


def _extract_guard_names(node: ast.expr) -> list[str]:
    """Extract guard names from a list literal."""
    guards: list[str] = []
    if isinstance(node, ast.List):
        for elt in node.elts:
            name = _get_name(elt)
            if name:
                guards.append(name)
    return guards


def _get_call_keyword(call: ast.Call, keyword: str) -> ast.expr | None:
    """Get the value of a keyword argument in a Call node."""
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _has_keyword_true(call: ast.Call, keyword: str) -> bool:
    """Check if a keyword argument is set to True."""
    val = _get_call_keyword(call, keyword)
    if val is None:
        return False
    if isinstance(val, ast.Constant) and val.value is True:
        return True
    return False


def _extract_decorator_info(
    decorator: ast.expr,
) -> tuple[list[str], str, bool] | None:
    """Extract (http_methods, path, sync_to_thread) from a handler decorator.

    Returns None if the decorator is not a recognized Litestar handler decorator.
    """
    if isinstance(decorator, ast.Call):
        func_name = _get_name(decorator.func)
        if func_name not in HANDLER_DECORATORS:
            return None

        path = ""
        if decorator.args:
            path = _get_string_value(decorator.args[0]) or ""
        path_kw = _get_call_keyword(decorator, "path")
        if path_kw is not None:
            path = _get_string_value(path_kw) or path

        sync_to_thread = _has_keyword_true(decorator, "sync_to_thread")

        if func_name == "route":
            methods_kw = _get_call_keyword(decorator, "http_method")
            methods: list[str] = []
            if methods_kw is not None:
                if isinstance(methods_kw, ast.List):
                    for elt in methods_kw.elts:
                        s = _get_string_value(elt)
                        if s:
                            methods.append(s.upper())
                elif isinstance(methods_kw, ast.Constant) and isinstance(
                    methods_kw.value, str
                ):
                    methods.append(methods_kw.value.upper())
            if not methods:
                methods = ["GET"]
            return methods, path, sync_to_thread

        return (
            DECORATOR_TO_METHODS.get(func_name, [func_name.upper()]),
            path,
            sync_to_thread,
        )

    if isinstance(decorator, ast.Name) and decorator.id in HANDLER_DECORATORS:
        methods = DECORATOR_TO_METHODS.get(decorator.id, [decorator.id.upper()])
        return methods, "", False

    return None


def _get_return_type_str(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Get the return type annotation as a string."""
    if node.returns is None:
        return None
    return ast.unparse(node.returns)


def _get_func_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Get parameter names excluding 'self'."""
    params = []
    for arg in node.args.args:
        if arg.arg != "self":
            params.append(arg.arg)
    return params


class _FileVisitor(ast.NodeVisitor):
    """Visit an AST to extract Litestar constructs."""

    def __init__(self, uri: str, resolved_imports: dict[str, str]) -> None:
        self.uri = uri
        self.result = FileParseResult(uri=uri)
        self.result.imports = resolved_imports
        self._current_class: ControllerInfo | None = None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name
            self.result.imports[local] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            self.result.imports[local] = (
                f"{module}.{alias.name}" if module else alias.name
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_controller = False
        for base in node.bases:
            base_name = _get_name(base)
            if base_name == "Controller":
                is_controller = True
                break
            resolved = self.result.imports.get(base_name or "")
            if resolved and resolved.endswith("Controller"):
                is_controller = True
                break

        if is_controller:
            controller = ControllerInfo(
                name=node.name,
                path="",
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                uri=self.uri,
            )
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "path":
                                controller.path = _get_string_value(stmt.value) or ""
                            elif target.id == "guards" and isinstance(
                                stmt.value, ast.List
                            ):
                                controller.guards = _extract_guard_names(stmt.value)
                            elif target.id == "dependencies" and isinstance(
                                stmt.value, ast.Dict
                            ):
                                controller.dependencies = _extract_dict_dependencies(
                                    stmt.value
                                )
                elif isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name
                ):
                    if stmt.target.id == "path" and stmt.value:
                        controller.path = _get_string_value(stmt.value) or ""

            prev = self._current_class
            self._current_class = controller
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._visit_function(stmt)
            self._current_class = prev
            self.result.controllers.append(controller)
        else:
            self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._current_class is None:
            self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._current_class is None:
            self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            info = _extract_decorator_info(decorator)
            if info is None:
                continue
            methods, path, sync_to_thread = info
            handler = HandlerInfo(
                name=node.name,
                http_methods=methods,
                path=path,
                line=node.lineno,
                col=node.col_offset,
                end_line=node.end_lineno or node.lineno,
                uri=self.uri,
                return_type=_get_return_type_str(node),
                is_async=isinstance(node, ast.AsyncFunctionDef),
                sync_to_thread=sync_to_thread,
                parameters=_get_func_params(node),
            )
            if self._current_class is not None:
                self._current_class.handlers.append(handler)
            else:
                self.result.handlers.append(handler)
            break

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            self._check_call_assignment(
                node.value, node.targets, node.lineno, node.end_lineno
            )
        self.generic_visit(node)

    def _check_call_assignment(
        self,
        call: ast.Call,
        targets: list[ast.expr],
        lineno: int,
        end_lineno: int | None,
    ) -> None:
        func_name = _get_name(call.func)
        if func_name is None:
            return

        var_name = ""
        if targets:
            first = targets[0]
            if isinstance(first, ast.Name):
                var_name = first.id

        resolved = self.result.imports.get(func_name, func_name)

        if func_name == "Litestar" or resolved.endswith("Litestar"):
            app = AppInfo(
                variable_name=var_name,
                line=lineno,
                end_line=end_lineno or lineno,
                uri=self.uri,
            )
            rh = _get_call_keyword(call, "route_handlers")
            if rh is not None:
                app.route_handler_names = _extract_list_names(rh)
            elif call.args:
                app.route_handler_names = _extract_list_names(call.args[0])
            guards_kw = _get_call_keyword(call, "guards")
            if guards_kw is not None:
                app.guards = _extract_guard_names(guards_kw)
            deps_kw = _get_call_keyword(call, "dependencies")
            if deps_kw is not None:
                app.dependencies = _extract_dict_dependencies(deps_kw)
            self.result.apps.append(app)

        elif func_name == "Router" or resolved.endswith("Router"):
            router = RouterInfo(
                variable_name=var_name,
                path="",
                line=lineno,
                end_line=end_lineno or lineno,
                uri=self.uri,
            )
            if call.args:
                router.path = _get_string_value(call.args[0]) or ""
            path_kw = _get_call_keyword(call, "path")
            if path_kw is not None:
                router.path = _get_string_value(path_kw) or router.path
            rh = _get_call_keyword(call, "route_handlers")
            if rh is not None:
                router.route_handler_names = _extract_list_names(rh)
            guards_kw = _get_call_keyword(call, "guards")
            if guards_kw is not None:
                router.guards = _extract_guard_names(guards_kw)
            deps_kw = _get_call_keyword(call, "dependencies")
            if deps_kw is not None:
                router.dependencies = _extract_dict_dependencies(deps_kw)
            self.result.routers.append(router)


def parse_file(source: str, uri: str) -> FileParseResult:
    """Parse a Python source file and extract Litestar constructs.

    Args:
        source: The Python source code.
        uri: The document URI for location tracking.

    Returns:
        A FileParseResult containing all discovered Litestar constructs.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return FileParseResult(uri=uri)

    visitor = _FileVisitor(uri, {})
    visitor.visit(tree)
    return visitor.result
