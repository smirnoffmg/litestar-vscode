# Change Log

All notable changes to the Litestar VS Code extension will be documented in this file.

## [0.2.0] - 2025-03-01

### Added

- GitHub Actions CI and aligned tool versions (#17)

### Changed

- Bump fs-extra from 11.2.0 to 11.3.3 (#1)
- Bump GitHub Actions: checkout 4→6, setup-node 4→6, setup-python 5→6, upload-artifact 4→7, download-artifact 4→8 (#11, #12, #13, #14, #15)
- Update README (#18)

## [0.1.0] - 2025-02-27

### Added

- Route Explorer: hierarchical tree view of routers, controllers, and handlers
- Route Search: quick search by path, HTTP method, handler name, or controller
- CodeLens for TestClient: jump from test client calls to route handler definitions
- Diagnostics: static analysis for common Litestar issues (missing return types, duplicate routes, etc.)
- Dependency injection visualization on hover
- Guard chain visualization
- Litestar snippets for handlers, controllers, routers, and tests
