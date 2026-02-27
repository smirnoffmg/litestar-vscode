# Contributing

Thanks for your interest in contributing to the Litestar VS Code extension.

## Development setup

- **Python / Node**: See [TESTING.md](TESTING.md) for venv setup, nox, and how to run the extension in development.
- **Linting / formatting**: The project uses ESLint, Prettier, and pre-commit. Run `pre-commit run --all-files` before submitting.

## Building the VSIX

The extension’s language server depends on Python packages (`lsprotocol`, `pygls`, etc.) that must be installed into `bundled/libs` before packaging. That folder is gitignored and is not included in the repo.

To build a VSIX locally, either:

- **Recommended**: Use nox so the bundle and VSIX are built together:
  ```bash
  nox -s build_package
  ```

- **Manual**: Install the Python bundle, then package:
  ```bash
  pip install -t ./bundled/libs --no-cache-dir --implementation py --no-deps --upgrade -r ./requirements.txt
  npm run vsce-package
  ```

Without the bundle step, installing the VSIX will fail with `ModuleNotFoundError` for `lsprotocol` (or similar) when the language server starts.

## Submitting changes

1. Open an issue or comment on an existing one to discuss the change.
2. Fork the repo, create a branch, and make your changes.
3. Ensure tests and lint pass (`npm run pretest`, pre-commit).
4. Open a pull request with a clear description and reference any related issues.

## Code of conduct

Be respectful and constructive. We follow the [Litestar community guidelines](https://litestar.dev/community/guidelines.html) where applicable.
