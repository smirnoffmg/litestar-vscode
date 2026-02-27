# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Debugging support for LSP."""

import os
import pathlib
import runpy
import sys


def update_sys_path(path_to_add: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        sys.path.append(path_to_add)


# Ensure debugger is loaded before we load anything else, to debug initialization.
debugger_path = os.getenv("DEBUGPY_PATH", None)
if debugger_path:
    if debugger_path.endswith("debugpy"):
        debugger_path = os.fspath(pathlib.Path(debugger_path).parent)

    update_sys_path(debugger_path)

    # pylint: disable=wrong-import-position,import-error
    import debugpy  # pyright: ignore[reportMissingImports]

    try:
        # 5678 is the default port. If you need to change it update it here
        # and in launch.json. Start "Attach to Server" in VS Code before
        # launching the extension when you want to debug the server.
        debugpy.connect(5678)
        # Pause as soon as the debugger connects. Comment out to run without stopping.
        debugpy.breakpoint()
    except (ConnectionRefusedError, OSError) as e:
        # No debugger listening on 5678 (e.g. extension started without Attach).
        # Run the server normally so the extension still works.
        sys.stderr.write(f"[Litestar LSP] Debug connect skipped: {e}\n")
        sys.stderr.flush()

SERVER_PATH = os.fspath(pathlib.Path(__file__).parent / "lsp_server.py")
# NOTE: Set breakpoint in `lsp_server.py` before continuing.
runpy.run_path(SERVER_PATH, run_name="__main__")
