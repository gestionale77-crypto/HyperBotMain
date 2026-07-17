# Hyperbot architecture

## 1. Goals

Build a professional, modular, async trading bot for Hyperliquid with enterprise-grade infrastructure for future extensions such as adaptive grids, risk engine, recovery, dashboard, and multi-account support.

## 2. System modules

- core: runtime context, settings, logging, retries
- exchange: REST/WebSocket abstraction and Hyperliquid client
- strategy: strategy interface and future implementations
- risk: kill switch, drawdown, exposure, liquidation checks
- execution: order manager, retries, partial fills, recovery hooks
- models: domain objects such as account snapshots
- storage: SQLite-backed persistence for events and state
- dashboard: FastAPI backend for live metrics and health checks
- utils: shared helpers

## 3. Data flow

1. Configuration is loaded from environment variables and .env.
2. Runtime starts the exchange client and logger.
3. Market data arrives through WebSocket and falls back to REST.
4. Strategy layer consumes market data and emits signals.
5. Risk engine validates the signal and blocks unsafe actions.
6. Execution layer submits orders and tracks state.
7. Storage persists events and snapshots.
8. Dashboard exposes health and metrics.

## 4. Dependency directions

- core -> no dependency on strategy
- exchange -> core
- strategy -> exchange, risk, execution
- risk -> core, models
- execution -> core, exchange, risk
- storage -> core
- dashboard -> core, storage

## 5. Suggested implementation order

1. Infrastructure: config, logging, runtime, retries
2. Exchange abstraction and Hyperliquid client
3. Risk engine and kill switch
4. Execution manager and order lifecycle
5. Storage and persistence
6. Dashboard API and metrics endpoint
7. Strategy implementations and backtesting
8. Recovery, resume, and multi-account support

## 6. Operational notes

- Use asyncio for all long-running services.
- Prefer typed interfaces and pydantic settings.
- Keep order state recovery and persistence first-class features.
- Start with SQLite, then evolve to Postgres when scale requires it.
