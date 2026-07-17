# Hyperbot

Production-grade Python infrastructure for a Hyperliquid futures grid trading bot.

## Architecture goals

- Fully modular and extensible
- Asyncio-first runtime
- Typed with mypy
- Pydantic-based configuration
- Structured logging and retries
- Exchange abstraction with REST fallback
- SQLite-backed storage
- FastAPI dashboard scaffold
- Unit tests and CI ready

## Project structure

- core: runtime, config, logging, retry
- exchange: exchange client abstractions and Hyperliquid integration
- strategy: strategy interfaces and future strategy implementations
- risk: risk engine and guardrails
- execution: order management and execution lifecycle
- models: domain models
- storage: persistence layer
- dashboard: FastAPI backend
- utils: helpers

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r <(python -m pip install --dry-run -e . 2>/dev/null)
```git

## Testing

```bash
pytest -q
```
