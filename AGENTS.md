# Repository Guidelines

## Project Structure & Module Organization
- `custom_components/novelanladv9/`: Home Assistant integration source (domain: `novelanladv9`). Key modules: `__init__.py` (setup), `config_flow.py` (UI config), `sensor.py`, `select.py`, `reading_data.py`, `const.py`, `manifest.json`.
- `.github/workflows/validate.yaml`: CI running `hassfest` and HACS validation.
- `requirements.txt`: Python runtime deps for local development.
- `README.md`: User setup instructions. No `tests/` folder yet.

## Build, Test, and Development Commands
- Install deps (dev): `pip install -r requirements.txt`
- Quick syntax check: `python -m compileall custom_components`
- Local run (manual): copy `custom_components/novelanladv9` into your HA `config/custom_components/` and restart Home Assistant; add the integration via UI.
- CI validation: open a PR to trigger `hassfest` + HACS checks.

## Coding Style & Naming Conventions
- Python, 4-space indentation, PEP 8. Prefer type hints where clear.
- Filenames and module names: `snake_case`. Constants in `const.py` are `UPPER_SNAKE_CASE`.
- Domain and package name fixed to `novelanladv9`. New platforms follow HA patterns (e.g., `switch.py`, `binary_sensor.py`).
- Entity naming: human-readable `name` in HA; unique IDs follow `f"{DOMAIN}_{ip_id}_{name}"` (see `sensor.py`).

## Testing Guidelines
- Current repo has no automated tests. Favor adding `pytest`-based tests for:
  - `reading_data.determine_sensor_type` classification.
  - Value parsing in `sensor.NovelAnLADV9Sensor.native_value`.
- Convention: place tests under `tests/` mirroring module paths; name files `test_*.py`.
- Run (once added): `pytest -q` and ensure high coverage on parsing/conversion logic.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise title (<72 chars), include rationale in body if needed. Example: `Add select entities for heat pump controls`.
- PRs: include a clear description, steps to reproduce/verify in HA, screenshots of entities/UI where relevant, and link related issues.
- Keep changes scoped; update `manifest.json` and `requirements.txt` when dependencies change; note breaking changes in PR description.

## Security & Configuration Tips
- Never commit real IPs, PINs, or tokens. All credentials must flow through `config_flow.py`.
- Network access uses `websockets` on the device (port 8214); handle errors gracefully and avoid blocking operations.
