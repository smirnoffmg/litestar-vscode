# Litestar extension for VS Code

VS Code extension that understands your [Litestar](https://litestar.dev/) app structure.

[![VS Marketplace](https://img.shields.io/visual-studio-marketplace/v/smirnoffmg.litestar?label=marketplace)](https://marketplace.visualstudio.com/items?itemName=smirnoffmg.litestar)
[![MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## What it does

**Route Explorer** - see every route in your app as a tree: `app` -> `routers` -> `controllers` -> `handlers`. Click to jump to code.

![Route Explorer](docs/route-explorer.png)

**Route Search** - fuzzy-search routes by path, method, or handler name.

![Route Search](docs/route-search.png)

**CodeLens** - links above `client.get("/items")` calls in tests that take you to the matching handler.

![CodeLens](docs/codelens.png)

**Diagnostics** - warns about missing return types, sync handlers without `sync_to_thread`, duplicate routes, bad guard signatures.

**DI & guard visualization** - hover a handler to see which dependencies are injected and which guards apply across all layers.

**Snippets** - `ls-get`, `ls-post`, `ls-controller`, `ls-router`, `ls-guard`, `ls-middleware`, `ls-test` and more.

## Install

Search "Litestar" in the VS Code extensions panel, or:

```bash
ext install smirnoffmg.litestar
```

Requires Python 3.9+ and the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python).

## Configuration

The extension auto-detects your app by finding `Litestar(...)` in the codebase. If that doesn't work, set the entry point manually:

```json
{
  "litestar.entryPoint": "my_app.main:app"
}
```

Other settings: `litestar.codeLens.enabled`, `litestar.diagnostics.enabled`, `litestar.showNotification`, `litestar.interpreter`. See full list in the extension settings panel.

## How it works

TypeScript side talks to VS Code. Python side (built on [pygls](https://github.com/openlawlibrary/pygls)) parses your code with `ast`, discovers routes, resolves the dependency/guard hierarchy, and reports diagnostics. They communicate over LSP.

## Development

```bash
git clone https://github.com/smirnoffmg/litestar-vscode.git
cd litestar-vscode
python -m venv .venv && source .venv/bin/activate
pip install nox && nox --session setup
npm install
```

Press `F5` in VS Code to launch the extension in debug mode.

```bash
nox --session tests    # run tests
nox --session lint     # lint everything
nox --session build_package  # build .vsix
```

## Contributing

PRs and issues welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)

## Credits

Built on the [VS Code Python Tools Extension Template](https://github.com/microsoft/vscode-python-tools-extension-template). Powered by [pygls](https://github.com/openlawlibrary/pygls) and [Litestar](https://litestar.dev/).
