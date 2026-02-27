"""Litestar language server — route discovery, diagnostics, CodeLens, and more."""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any, Optional


# **********************************************************
# Update sys.path before importing any bundled libraries.
# **********************************************************
def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        elif strategy == "fromEnvironment":
            sys.path.append(path_to_add)


# Ensure that we can import LSP libraries, and other bundled libraries.
update_sys_path(
    os.fspath(pathlib.Path(__file__).parent.parent / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)

import dependency_resolver as dep_resolver
import diagnostics as litestar_diagnostics

# **********************************************************
# Imports needed for the language server.
# **********************************************************
# pylint: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils
import lsprotocol.types as lsp
import route_parser
import workspace_index as ws_index
from pygls import uris, workspace
from pygls.lsp.server import LanguageServer

WORKSPACE_SETTINGS = {}
GLOBAL_SETTINGS = {}
RUNNER = pathlib.Path(__file__).parent / "lsp_runner.py"

MAX_WORKERS = 5
LSP_SERVER = LanguageServer(name="Litestar", version="0.1.0", max_workers=MAX_WORKERS)

TOOL_MODULE = "litestar"
TOOL_DISPLAY = "Litestar"

INDEX = ws_index.WorkspaceIndex()


# **********************************************************
# LSP event handlers.
# **********************************************************


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    """LSP handler for textDocument/didOpen request."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    _reparse_and_diagnose(document)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    """LSP handler for textDocument/didSave request."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    _reparse_and_diagnose(document)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    """LSP handler for textDocument/didClose request."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    LSP_SERVER.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(uri=document.uri, diagnostics=[])
    )


def _reparse_and_diagnose(document: workspace.TextDocument) -> None:
    """Re-parse a document, update the workspace index, and publish diagnostics."""
    if str(document.uri).startswith("vscode-notebook-cell"):
        return
    if utils.is_stdlib_file(document.path):
        return

    settings = _get_settings_by_document(document)
    diag_enabled = settings.get("diagnosticsEnabled", True)

    result = INDEX.update_file(document.uri, document.source)

    diags: list[lsp.Diagnostic] = []
    if diag_enabled:
        diags = litestar_diagnostics.compute_diagnostics(result, workspace_index=INDEX)

    LSP_SERVER.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(uri=document.uri, diagnostics=diags)
    )


# **********************************************************
# CodeLens
# **********************************************************


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_CODE_LENS)
def code_lens(params: lsp.CodeLensParams) -> list[lsp.CodeLens] | None:
    """LSP handler for textDocument/codeLens request."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    settings = _get_settings_by_document(document)
    if not settings.get("codeLensEnabled", True):
        return None

    return _build_code_lens(document)


def _build_code_lens(document: workspace.TextDocument) -> list[lsp.CodeLens]:
    """Build CodeLens items for test client calls in the document."""
    import ast

    lenses: list[lsp.CodeLens] = []
    try:
        tree = ast.parse(document.source)
    except SyntaxError:
        return lenses

    test_client_vars: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                func_name = route_parser._get_name(node.value.func)
                dotted = route_parser._get_dotted_name(node.value.func)
                if func_name in ("TestClient", "create_test_client") or (
                    dotted
                    and ("TestClient" in dotted or "create_test_client" in dotted)
                ):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            test_client_vars.add(target.id)

        if isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call):
                    func_name = route_parser._get_name(item.context_expr.func)
                    if func_name in ("TestClient", "create_test_client"):
                        if item.optional_vars and isinstance(
                            item.optional_vars, ast.Name
                        ):
                            test_client_vars.add(item.optional_vars.id)

    if not test_client_vars:
        return lenses

    http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    resolved_routes = INDEX.build_resolved_routes()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in http_methods:
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id not in test_client_vars:
            continue

        method = node.func.attr.upper()
        path = ""
        if node.args:
            path = route_parser._get_string_value(node.args[0]) or ""

        target = _find_matching_route(resolved_routes, method, path)
        if target:
            lens_range = lsp.Range(
                start=lsp.Position(line=node.lineno - 1, character=node.col_offset),
                end=lsp.Position(line=node.lineno - 1, character=node.col_offset + 1),
            )
            lenses.append(
                lsp.CodeLens(
                    range=lens_range,
                    command=lsp.Command(
                        title=f"Go to handler: {target.handler_name}",
                        command="litestar.goToHandler",
                        arguments=[target.uri, target.line],
                    ),
                )
            )

    return lenses


def _find_matching_route(
    routes: list[ws_index.ResolvedRoute], method: str, path: str
) -> ws_index.ResolvedRoute | None:
    """Find a resolved route matching the given HTTP method and path."""
    for route in routes:
        if method in route.http_methods and route.full_path == path:
            return route
    return None


# **********************************************************
# Hover
# **********************************************************


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(params: lsp.HoverParams) -> lsp.Hover | None:
    """LSP handler for textDocument/hover — show resolved route info."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    position = params.position

    file_result = INDEX.get_file_result(document.uri)
    if not file_result:
        return None

    for handler in file_result.handlers:
        if handler.line - 1 <= position.line <= (handler.end_line - 1):
            return _hover_for_handler(handler, document.uri)

    for ctrl in file_result.controllers:
        if ctrl.line - 1 <= position.line <= (ctrl.end_line - 1):
            for handler in ctrl.handlers:
                if handler.line - 1 <= position.line <= (handler.end_line - 1):
                    return _hover_for_controller_handler(handler, ctrl, document.uri)

    return None


def _hover_for_handler(handler: route_parser.HandlerInfo, uri: str) -> lsp.Hover:
    """Build hover content for a standalone handler."""
    routes = INDEX.build_resolved_routes()
    full_path = handler.path or "/"
    for r in routes:
        if r.handler_name == handler.name and r.uri == uri and r.line == handler.line:
            full_path = r.full_path
            break

    methods_str = ", ".join(handler.http_methods)
    lines = [
        f"**{methods_str}** `{full_path}`",
        "",
        f"Handler: `{handler.name}`",
    ]
    if handler.return_type:
        lines.append(f"Return type: `{handler.return_type}`")

    _append_deps_and_guards(lines, uri, handler.line)

    return lsp.Hover(
        contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value="\n".join(lines),
        )
    )


def _hover_for_controller_handler(
    handler: route_parser.HandlerInfo,
    ctrl: route_parser.ControllerInfo,
    uri: str,
) -> lsp.Hover:
    """Build hover content for a handler inside a controller."""
    routes = INDEX.build_resolved_routes()
    full_path = handler.path or "/"
    for r in routes:
        if r.handler_name == handler.name and r.uri == uri and r.line == handler.line:
            full_path = r.full_path
            break

    methods_str = ", ".join(handler.http_methods)
    lines = [
        f"**{methods_str}** `{full_path}`",
        "",
        f"Controller: `{ctrl.name}` | Handler: `{handler.name}`",
    ]
    if handler.return_type:
        lines.append(f"Return type: `{handler.return_type}`")

    _append_deps_and_guards(lines, uri, handler.line)

    return lsp.Hover(
        contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value="\n".join(lines),
        )
    )


def _append_deps_and_guards(lines: list[str], uri: str, handler_line: int) -> None:
    """Append dependency and guard info (with shadow warnings) to hover lines."""
    dep_layers = INDEX.get_dependencies_for_handler(uri, handler_line)
    if dep_layers:
        chain = dep_resolver.resolve_dependency_chain(dep_layers)
        lines.append("")
        lines.append("**Dependencies:**")
        for layer in chain.layers:
            for key, val in layer.dependencies.items():
                lines.append(
                    f"- `{key}` = `{val}` (from {layer.layer_kind} `{layer.layer_name}`)"
                )
        if chain.shadowed:
            lines.append("")
            lines.append("**Shadowed dependencies:**")
            for key, original, shadower in chain.shadowed:
                lines.append(
                    f"- `{key}`: {shadower.layer_kind} `{shadower.layer_name}` "
                    f"overrides {original.layer_kind} `{original.layer_name}`"
                )

    guard_layers = INDEX.get_guards_for_handler(uri, handler_line)
    if guard_layers:
        chain = dep_resolver.resolve_guard_chain(guard_layers)
        lines.append("")
        lines.append("**Guards:**")
        for layer in chain.layers:
            for g in layer.guards:
                lines.append(f"- `{g}` (from {layer.layer_kind} `{layer.layer_name}`)")


# **********************************************************
# Custom LSP methods.
# **********************************************************


@LSP_SERVER.feature("litestar/routes")
def get_routes(params: Any = None) -> list[dict]:
    """Custom LSP method: return the full route tree."""
    tree = INDEX.build_route_tree()
    return ws_index.route_tree_to_dict(tree)


@LSP_SERVER.feature("litestar/removeFile")
def remove_file(params: dict) -> None:
    """Custom LSP method: remove a file from the workspace index (e.g. after delete/rename)."""
    uri = params.get("uri")
    if isinstance(uri, str):
        INDEX.remove_file(uri)


@LSP_SERVER.feature("litestar/dependencies")
def get_dependencies(params: dict) -> list[dict]:
    """Custom LSP method: return the dependency chain for a handler."""
    uri = params.get("uri", "")
    line = params.get("line", 0)
    return INDEX.get_dependencies_for_handler(uri, line)


@LSP_SERVER.feature("litestar/guards")
def get_guards(params: dict) -> list[dict]:
    """Custom LSP method: return the guard chain for a handler."""
    uri = params.get("uri", "")
    line = params.get("line", 0)
    return INDEX.get_guards_for_handler(uri, line)


# **********************************************************
# Required Language Server Initialization and Exit handlers.
# **********************************************************


@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """LSP handler for initialize request."""
    log_to_output(f"CWD Server: {os.getcwd()}")

    paths = "\r\n   ".join(sys.path)
    log_to_output(f"sys.path used to run Server:\r\n   {paths}")

    GLOBAL_SETTINGS.update(**params.initialization_options.get("globalSettings", {}))

    settings = params.initialization_options["settings"]
    _update_workspace_settings(settings)
    log_to_output(
        f"Settings used to run Server:\r\n{json.dumps(settings, indent=4, ensure_ascii=False)}\r\n"
    )
    log_to_output(
        f"Global settings:\r\n{json.dumps(GLOBAL_SETTINGS, indent=4, ensure_ascii=False)}\r\n"
    )

    workspace_folders = params.workspace_folders
    if workspace_folders:
        for folder in workspace_folders:
            folder_path = uris.to_fs_path(folder.uri)
            log_to_output(f"Scanning workspace: {folder_path}")
            INDEX.scan_workspace(folder_path)
        INDEX.set_workspace_roots([uris.to_fs_path(f.uri) for f in workspace_folders])
    else:
        cwd = os.getcwd()
        log_to_output(f"Scanning workspace (cwd): {cwd}")
        INDEX.scan_workspace(cwd)
        INDEX.set_workspace_roots([cwd])

    tree = INDEX.build_route_tree()
    log_to_output(f"Found {_count_handlers(tree)} route handlers in workspace")


def _count_handlers(nodes: list[ws_index.RouteTreeNode]) -> int:
    count = 0
    for node in nodes:
        if node.kind == "handler":
            count += 1
        count += _count_handlers(node.children)
    return count


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Optional[Any] = None) -> None:
    """Handle clean up on exit."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Optional[Any] = None) -> None:
    """Handle clean up on shutdown."""
    jsonrpc.shutdown_json_rpc()


def get_cwd(settings: dict, document: Optional[workspace.TextDocument]) -> str:
    """Returns the working directory for running the tool.

    Resolves VS Code file-related variable substitutions when a document
    is available. See https://code.visualstudio.com/docs/reference/variables-reference
    """
    cwd = settings.get("cwd", settings["workspaceFS"])

    workspace_fs = settings["workspaceFS"]

    if document and document.path:
        file_path = document.path
        file_dir = os.path.dirname(file_path)
        file_basename = os.path.basename(file_path)
        file_stem, file_ext = os.path.splitext(file_basename)

        substitutions = {
            "${file}": file_path,
            "${fileBasename}": file_basename,
            "${fileBasenameNoExtension}": file_stem,
            "${fileExtname}": file_ext,
            "${fileDirname}": file_dir,
            "${fileDirnameBasename}": os.path.basename(file_dir),
            "${relativeFile}": os.path.relpath(file_path, workspace_fs),
            "${relativeFileDirname}": os.path.relpath(file_dir, workspace_fs),
            "${fileWorkspaceFolder}": workspace_fs,
        }

        for token, value in substitutions.items():
            cwd = cwd.replace(token, value)
    else:
        if "${file" in cwd or "${relativeFile" in cwd:
            cwd = workspace_fs

    return cwd


def _get_global_defaults():
    return {
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
    }


def _update_workspace_settings(settings):
    if not settings:
        key = os.getcwd()
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }
        return

    for setting in settings:
        key = uris.to_fs_path(setting["workspace"])
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            **setting,
            "workspaceFS": key,
        }


def _get_settings_by_path(file_path: pathlib.Path):
    workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

    while file_path != file_path.parent:
        str_file_path = str(file_path)
        if str_file_path in workspaces:
            return WORKSPACE_SETTINGS[str_file_path]
        file_path = file_path.parent

    setting_values = list(WORKSPACE_SETTINGS.values())
    return setting_values[0]


def _get_document_key(document: workspace.TextDocument):
    if WORKSPACE_SETTINGS:
        document_workspace = pathlib.Path(document.path)
        workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

        while document_workspace != document_workspace.parent:
            if str(document_workspace) in workspaces:
                return str(document_workspace)
            document_workspace = document_workspace.parent

    return None


def _get_settings_by_document(document: workspace.TextDocument | None):
    if document is None or document.path is None:
        return list(WORKSPACE_SETTINGS.values())[0]

    key = _get_document_key(document)
    if key is None:
        key = os.fspath(pathlib.Path(document.path).parent)
        return {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }

    return WORKSPACE_SETTINGS[str(key)]


# *****************************************************
# Logging and notification.
# *****************************************************
def log_to_output(
    message: str, msg_type: lsp.MessageType = lsp.MessageType.Log
) -> None:
    LSP_SERVER.window_log_message(lsp.LogMessageParams(type=msg_type, message=message))


def log_error(message: str) -> None:
    LSP_SERVER.window_log_message(
        lsp.LogMessageParams(type=lsp.MessageType.Error, message=message)
    )
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onError", "onWarning", "always"]:
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Error, message=message)
        )


def log_warning(message: str) -> None:
    LSP_SERVER.window_log_message(
        lsp.LogMessageParams(type=lsp.MessageType.Warning, message=message)
    )
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onWarning", "always"]:
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Warning, message=message)
        )


def log_always(message: str) -> None:
    LSP_SERVER.window_log_message(
        lsp.LogMessageParams(type=lsp.MessageType.Info, message=message)
    )
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["always"]:
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Info, message=message)
        )


# *****************************************************
# Start the server.
# *****************************************************
if __name__ == "__main__":
    LSP_SERVER.start_io()
