"""Diagnostic rules for Litestar handler analysis.

Detection logic is in pure Python (no LSP dependency) so it can be unit-tested
without bundled libs. The ``compute_diagnostics`` function converts detected
issues into ``lsp.Diagnostic`` objects for the server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from route_parser import FileParseResult, HandlerInfo

if TYPE_CHECKING:
    from workspace_index import WorkspaceIndex


DIAGNOSTIC_SOURCE = "litestar"


@dataclass
class DiagnosticIssue:
    """A detected issue — pure data, no LSP dependency."""

    code: str
    message: str
    severity: str  # "warning", "error", "info", "hint"
    line: int
    col: int
    end_line: int
    end_col: int


# ------------------------------------------------------------------
# Detection (pure Python — no lsprotocol import)
# ------------------------------------------------------------------


def detect_issues(
    result: FileParseResult,
    *,
    workspace_index: WorkspaceIndex | None = None,
) -> list[DiagnosticIssue]:
    """Detect all issues for a parsed file.

    Pass *workspace_index* to enable cross-layer checks like shadowed
    dependencies (LITESTAR003) and guard signature validation (LITESTAR004).
    """
    issues: list[DiagnosticIssue] = []

    for handler in result.handlers:
        issues.extend(_check_handler(handler))

    for controller in result.controllers:
        for handler in controller.handlers:
            issues.extend(_check_handler(handler))

    if workspace_index is not None:
        issues.extend(_check_shadowed_dependencies(result, workspace_index))
        issues.extend(_check_guard_signatures(result, workspace_index))

    return issues


def _check_handler(handler: HandlerInfo) -> list[DiagnosticIssue]:
    issues: list[DiagnosticIssue] = []

    issue = _check_missing_return_type(handler)
    if issue:
        issues.append(issue)

    issue = _check_sync_without_sync_to_thread(handler)
    if issue:
        issues.append(issue)

    return issues


def _check_missing_return_type(handler: HandlerInfo) -> DiagnosticIssue | None:
    """LITESTAR001: Handler missing return type annotation."""
    if handler.return_type is not None:
        return None
    return DiagnosticIssue(
        code="LITESTAR001",
        message=f"Handler '{handler.name}' is missing a return type annotation.",
        severity="warning",
        line=handler.line,
        col=handler.col,
        end_line=handler.line,
        end_col=handler.col + len(handler.name) + 4,
    )


def _check_sync_without_sync_to_thread(handler: HandlerInfo) -> DiagnosticIssue | None:
    """LITESTAR002: Sync handler without sync_to_thread parameter."""
    if handler.is_async or handler.sync_to_thread:
        return None
    return DiagnosticIssue(
        code="LITESTAR002",
        message=(
            f"Sync handler '{handler.name}' does not set sync_to_thread=True. "
            f"Litestar will block the event loop unless sync_to_thread is enabled."
        ),
        severity="warning",
        line=handler.line,
        col=handler.col,
        end_line=handler.line,
        end_col=handler.col + len(handler.name) + 4,
    )


def _check_shadowed_dependencies(
    result: FileParseResult,
    index: WorkspaceIndex,
) -> list[DiagnosticIssue]:
    """LITESTAR003: Dependency key defined at multiple layers (shadowed)."""
    from dependency_resolver import resolve_dependency_chain

    issues: list[DiagnosticIssue] = []

    all_handlers: list[tuple[HandlerInfo, str]] = []
    for h in result.handlers:
        all_handlers.append((h, result.uri))
    for ctrl in result.controllers:
        for h in ctrl.handlers:
            all_handlers.append((h, result.uri))

    seen_shadow_keys: set[str] = set()

    for handler, uri in all_handlers:
        dep_layers = index.get_dependencies_for_handler(uri, handler.line)
        if not dep_layers:
            continue

        chain = resolve_dependency_chain(dep_layers)
        for key, original, shadower in chain.shadowed:
            dedup = f"{key}:{original.layer_name}:{shadower.layer_name}"
            if dedup in seen_shadow_keys:
                continue
            seen_shadow_keys.add(dedup)

            issues.append(
                DiagnosticIssue(
                    code="LITESTAR003",
                    message=(
                        f"Dependency '{key}' in {shadower.layer_kind} "
                        f"'{shadower.layer_name}' shadows the same key from "
                        f"{original.layer_kind} '{original.layer_name}'."
                    ),
                    severity="warning",
                    line=handler.line,
                    col=handler.col,
                    end_line=handler.line,
                    end_col=handler.col + len(handler.name) + 4,
                )
            )

    return issues


def _check_guard_signatures(
    result: FileParseResult,
    index: WorkspaceIndex,
) -> list[DiagnosticIssue]:
    """LITESTAR004: Guard function with incorrect signature."""
    from dependency_resolver import validate_guard_signature

    issues: list[DiagnosticIssue] = []
    checked: set[str] = set()

    guard_names: list[tuple[list[str], int, int]] = []

    for app in result.apps:
        if app.guards:
            guard_names.append((app.guards, app.line, 0))
    for router in result.routers:
        if router.guards:
            guard_names.append((router.guards, router.line, 0))
    for ctrl in result.controllers:
        if ctrl.guards:
            guard_names.append((ctrl.guards, ctrl.line, 0))

    source = _get_source_for_uri(result.uri, index)
    if source is None:
        return issues

    for guards, line, col in guard_names:
        for guard_name in guards:
            if guard_name in checked:
                continue
            checked.add(guard_name)

            error_msg = validate_guard_signature(source, guard_name)
            if error_msg is not None:
                issues.append(
                    DiagnosticIssue(
                        code="LITESTAR004",
                        message=error_msg,
                        severity="warning",
                        line=line,
                        col=col,
                        end_line=line,
                        end_col=col + len(guard_name) + 4,
                    )
                )

    return issues


def _get_source_for_uri(uri: str, index: WorkspaceIndex) -> str | None:
    """Retrieve the original source text for a URI from the index."""
    fr = index.get_file_result(uri)
    if fr is None:
        return None
    # We need the raw source, not the parse result.  The workspace index
    # stores FileParseResult but not the source.  We'll need to add that.
    return getattr(index, "_file_sources", {}).get(uri)


# ------------------------------------------------------------------
# LSP conversion (requires lsprotocol — only imported at server runtime)
# ------------------------------------------------------------------


def compute_diagnostics(
    result: FileParseResult,
    *,
    workspace_index: Any = None,
) -> list:
    """Convert detected issues into ``lsp.Diagnostic`` objects.

    Only call this from the LSP server where lsprotocol is available.
    """
    import lsprotocol.types as lsp

    severity_map = {
        "error": lsp.DiagnosticSeverity.Error,
        "warning": lsp.DiagnosticSeverity.Warning,
        "info": lsp.DiagnosticSeverity.Information,
        "hint": lsp.DiagnosticSeverity.Hint,
    }

    issues = detect_issues(result, workspace_index=workspace_index)
    diags: list[lsp.Diagnostic] = []

    for issue in issues:
        diags.append(
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=issue.line - 1, character=issue.col),
                    end=lsp.Position(line=issue.end_line - 1, character=issue.end_col),
                ),
                message=issue.message,
                severity=severity_map.get(
                    issue.severity, lsp.DiagnosticSeverity.Warning
                ),
                code=issue.code,
                source=DIAGNOSTIC_SOURCE,
            )
        )

    return diags
