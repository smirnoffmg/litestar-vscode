# Manual Test Plan

## How to install the dev package

From the repo root, in a terminal:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install nox
nox --session setup
npm install
```

This creates a venv, installs nox, runs the project’s dev setup (Python deps, tooling), and installs Node dependencies. On Windows use `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

## Launch

1. Open the **Run and Debug** view (sidebar icon or `Ctrl+Shift+D` / `Cmd+Shift+D`).
2. In the dropdown at the top of that panel, select **"Debug Extension and Python"**.
3. Press **F5** (or click the green play button).

This opens a new Extension Development Host window. If you don’t see "Debug Extension and Python" in the dropdown, ensure `.vscode/launch.json` is present and that the Python extension is installed.

---

## Test 1: Route Explorer Tree View

### Setup

Create a file `app.py` in the Extension Development Host with:

```python
from litestar import get, post, Controller, Router, Litestar
from litestar.di import Provide


def get_db():
    ...


@get("/health")
async def health_check() -> dict:
    return {"ok": True}


class ItemController(Controller):
    path = "/items"

    @get()
    async def list_items(self) -> list[dict]:
        ...

    @post()
    async def create_item(self, data: dict) -> dict:
        ...


item_router = Router(
    path="/api/v1",
    route_handlers=[ItemController],
    dependencies={"db": Provide(get_db)},
)

app = Litestar(route_handlers=[item_router, health_check])
```

### Expected

- A star icon appears in the activity bar (left sidebar).
- Clicking it shows a "Routes" panel.
- The tree shows:
  - `app`
    - `item_router [/api/v1]`
      - `ItemController [/items]`
        - `GET /api/v1/items`
        - `POST /api/v1/items`
    - `GET /health`
- Clicking any handler opens the file and jumps to that line.

### Refresh

- Edit the file (e.g., add a new `@delete` handler), save.
- The tree should update within ~1 second.
- Alternatively, click the refresh icon in the panel title bar.

---

## Test 2: Diagnostics

### LITESTAR001 — Missing return type

Add this handler to `app.py`:

```python
@get("/no-return")
async def missing_return():
    ...
```

**Expected**: Yellow squiggly underline on `missing_return` with message:
`Handler 'missing_return' is missing a return type annotation.`

Adding a return type (`-> dict`) should clear it on save.

### LITESTAR002 — Sync handler without sync_to_thread

Add this handler:

```python
@post("/sync-endpoint")
def sync_handler(data: dict) -> dict:
    ...
```

**Expected**: Warning on `sync_handler` with message mentioning `sync_to_thread`.

Change to `@post("/sync-endpoint", sync_to_thread=True)` — warning clears on save.
Change to `async def` — warning also clears.

### LITESTAR003 — Shadowed dependency

Modify the app to shadow a dependency:

```python
app = Litestar(
    route_handlers=[item_router, health_check],
    dependencies={"db": Provide(get_db)},
)
```

Now both `app` and `item_router` define `db`.

**Expected**: Warning mentioning `'db'` in router shadows the same key from app.

Remove `dependencies` from either the app or the router — warning clears.

### LITESTAR004 — Guard with wrong signature

Add a guard with the wrong number of parameters:

```python
def bad_guard():
    ...

app = Litestar(
    route_handlers=[item_router, health_check],
    guards=[bad_guard],
)
```

**Expected**: Warning: `Guard 'bad_guard' must accept at least 2 parameters (connection, route_handler), but has 0.`

Fix by changing to `def bad_guard(connection, route_handler): ...` — warning clears.

---

## Test 3: Hover

Hover over any handler function name (e.g., `list_items` inside the controller).

**Expected**: A hover popup showing:
- HTTP method and full resolved path: `GET /api/v1/items`
- Controller and handler name
- Return type
- Dependencies (from which layer)
- Guards (from which layer), if any
- Shadowed dependency warnings, if any

---

## Test 4: Route Search

Open Command Palette (`Cmd+Shift+P`) and run:
**Litestar: Search Routes**

**Expected**:
- A QuickPick dropdown appears listing all routes.
- Each item shows `[METHOD] /path` with handler name and file location.
- Typing filters the list.
- Selecting an item opens the file at the handler definition.

---

## Test 5: CodeLens (Test Client)

Create a test file `test_app.py`:

```python
from litestar.testing import create_test_client
from app import app

def test_health():
    with create_test_client(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

def test_items():
    with create_test_client(app) as client:
        response = client.get("/api/v1/items")
```

**Expected**:
- Above each `client.get(...)` / `client.post(...)` call, a CodeLens link appears: `Go to handler: health_check` / `Go to handler: list_items`.
- Clicking it navigates to the handler definition in `app.py`.

---

## Test 6: Snippets

Open a new `.py` file and type each prefix, then press Tab:

| Type this       | Expected scaffold                                             |
| --------------- | ------------------------------------------------------------- |
| `ls-get`        | `@get("/path")` handler with async def and return type        |
| `ls-post`       | `@post("/path")` handler                                      |
| `ls-put`        | `@put("/path/{item_id:int}")` handler                         |
| `ls-patch`      | `@patch(...)` handler                                         |
| `ls-delete`     | `@delete(...)` handler                                        |
| `ls-controller` | `Controller` class with path, get, post methods               |
| `ls-router`     | `Router(...)` with path, route_handlers, dependencies, guards |
| `ls-guard`      | Guard function with `(connection, route_handler)` signature   |
| `ls-middleware` | Middleware class with `__call__`                              |
| `ls-test`       | Test using `create_test_client`                               |

Tab stops should cycle through placeholder values.

---

## Test 7: Commands

Open Command Palette (`Cmd+Shift+P`) and verify these commands exist:

| Command                    | Behavior                                          |
| -------------------------- | ------------------------------------------------- |
| `Litestar: Restart Server` | Restarts the language server (check Output panel) |
| `Litestar: Show Routes`    | Focuses the Litestar sidebar                      |
| `Litestar: Search Routes`  | Opens route search QuickPick                      |
| `Litestar: Refresh Routes` | Refreshes the route tree                          |

---

## Test 8: Settings

Open VS Code Settings (`Cmd+,`) and search for `litestar`.

**Expected settings visible**:
- `litestar.diagnostics.enabled` (boolean, default true)
- `litestar.codeLens.enabled` (boolean, default true)
- `litestar.entryPoint` (string, default empty)
- `litestar.interpreter`, `litestar.importStrategy`, `litestar.showNotifications`, etc.

### Disable diagnostics

Set `litestar.diagnostics.enabled` to `false`, save. Reopen `app.py`.

**Expected**: No Litestar diagnostics appear (no LITESTAR001–004 warnings).

Re-enable, warnings reappear on save.

---

## Test 9: Cross-File Resolution

Split the app across files:

`controllers.py`:
```python
from litestar import Controller, get

class UserController(Controller):
    path = "/users"

    @get()
    async def list_users(self) -> list[dict]:
        ...
```

`main.py`:
```python
from litestar import Litestar, Router
from controllers import UserController

router = Router(path="/api", route_handlers=[UserController])
app = Litestar(route_handlers=[router])
```

**Expected**:
- Route Explorer shows `app > router [/api] > UserController [/users] > GET /api/users`
- Route Search finds `GET /api/users`
- Clicking the tree item opens `controllers.py` at the `list_users` line

---

## Test 10: Edge Cases

1. **Empty file** — open a blank `.py` file. No errors, no crashes.
2. **Syntax error** — add `def broken(:` to a file. No crashes, diagnostics clear gracefully.
3. **No Litestar imports** — open a regular Python file. No diagnostics, no tree entries.
4. **Multiple apps** — define two `Litestar(...)` instances. Both appear as separate roots in the tree.
5. **Large workspace** — open a project with many `.py` files. Check the Output panel ("Litestar") for `Found N route handlers in workspace` on startup.

---

## Test 11: Server Logs

Open the Output panel (`Cmd+Shift+U`) and select "Litestar" from the dropdown.

**Expected on startup**:
- `CWD Server: ...`
- `Scanning workspace: ...`
- `Found N route handlers in workspace`
- Settings dump

**Expected on file open/save**:
- No errors or tracebacks
