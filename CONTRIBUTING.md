# Contributing

Thanks for helping improve the MaxxAir Fan Pi Interface (original algorithm by Ryder Henry).

**Documentation:** [docs/README.md](docs/README.md) — setup, architecture, CLI, and development guides.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pre-commit install   # optional
```

## Local development

See [docs/development.md](docs/development.md) for simulator mode, fake Firebase, and replay fixtures.

```bash
./scripts/dev.sh
maxxair-fan run --simulator --once
maxxair-fan check
```

## Tests

```bash
pytest --cov=maxxair_fan --cov-report=term-missing
pytest -m "not integration"    # unit tests only
pytest -m integration          # integration tests only
```

## Lint

```bash
ruff check .
ruff format .
```

## Adding a replay fixture

1. Create `tests/fixtures/your_scenario.json` with `target`, `direction`, and `steps`
2. Run `maxxair-fan replay tests/fixtures/your_scenario.json`
3. Add the fixture to `tests/integration/test_replay_fixtures.py` parametrize list if needed

Details: [Development → Replay fixtures](docs/development.md#replay-fixtures).

## Pull requests

- Keep changes focused
- Ensure tests pass
- Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes
- Update relevant docs under `docs/` when behavior or configuration changes
