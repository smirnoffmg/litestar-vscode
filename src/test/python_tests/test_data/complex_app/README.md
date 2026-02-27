# Complex Litestar app (single file)

Use this file in the **Extension Development Host** to manually verify all extension features. Open `app.py` in a folder that has this file (or copy it into your workspace).

## What it exercises

| Feature | What to check |
|--------|----------------|
| **Route Explorer** | Star icon → Routes panel. Tree: `main_app` (routers, controllers, handlers) and `secondary_app` (ping). Nested: api/v1, api/v2, internal. |
| **Route Search** | `Cmd+Shift+P` → "Litestar: Search Routes". Filter by path/method, open handler on select. |
| **Diagnostics** | `missing_return_bad` → LITESTAR001 (missing return type). `sync_handler_no_thread` → LITESTAR002 (sync without sync_to_thread). App + `api_v1_router` both define `db` → LITESTAR003 (shadowed dependency). `bad_guard` → LITESTAR004 (guard wrong signature). |
| **Hover** | Hover handler names (e.g. `list_items`, `get_item`): method + path, controller/handler, return type, dependencies, guards, shadowed warning. |
| **CodeLens** | Above each `client.get(...)` / `client.post(...)` in the test functions at the bottom: "Go to handler: …". Click to jump to handler. |
| **Multiple apps** | Two roots in Route Explorer: `main_app` and `secondary_app`. |

## Quick test

1. Launch "Debug Extension and Python" (F5).
2. In the new window, File → Open Folder → select a folder containing this `app.py` (e.g. the `complex_app` folder or your project).
3. Open `app.py`.
4. Run through the checks in the table above and in [TESTING.md](../../../../../TESTING.md).
