# Project Restructure Notes

This file documents the recent refactor that splits the codebase into layers: views, services, repositories, models, reports, and utils.

## Goals
- Separate UI-only code (views) from business logic (services) and data access (repositories).
- Maintain backward compatibility during incremental migration using shims (`app.py`, `db_service.py`, `report_service.py`).
- Preserve tests and add focused unit tests for repositories and services.

## Key File Mappings (old → new)
- `app.py` → now a thin shim that imports `MainWindow` from `views.main_view` and exposes `main()`
- `views/main_view.py` ← extracted `MainWindow` and UI-only logic
- `repositories/db_repository.py` ← migrated DB access methods (read/write) from the old DB service
- `services/reporting.py` ← moved report generation logic (Jinja2, renderers)
- `report_service.py` → compatibility shim re-exporting `services.reporting` public API
- `db_service.py` → compatibility shim exposing `DBService` (which is implemented in `repositories/db_repository.py`)

## Templates & Assets
- `templates/` and `assets/images/` remain in place; report renderer uses Path.as_uri() so relative images work from package root.

## Tests
- Unit tests use an in-memory SQLite DB and are located in `tests/`.
- Existing tests pass locally: `pytest` currently shows all tests passing.

## Next Steps
1. Add `main.py` entrypoint and update README with launch instructions (TODO: in progress).
2. Add GitHub Actions CI workflow to run `pytest` on push/PR (TODO).
3. Add documentation for contributing and the refactor rationale (TODO).
4. Add smoke tests for UI flows (manual steps and/or headless tests) (TODO).

## Notes
- During the incremental migration, shims were added/kept to avoid breaking imports used across the codebase.
- If you plan to further rename public APIs, update the shims and the tests together.
