# Trading System

Algorithmic trading system for the Argentine market (CEDEARs). Combines data ingestion, technical analysis, strategy backtesting, signal generation, and portfolio management.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+
- Poetry

### 1. Clone and setup environment

```bash
git clone https://github.com/MauroPerna/ar-trading-bot
cd ar-trading-bot

# Copy environment file
cp .env.example .env
```

The default `.env` values work out of the box with docker-compose.

### 2. Start the database

```bash
docker-compose up -d
```

This starts:
- PostgreSQL 16 on port 5432
- Redis 7 on port 6379

### 3. Install dependencies

```bash
poetry install
```

### 4. Active the virtual environment

```bash
# if the plugin is not yet installed
poetry self add poetry-plugin-shell
```

```bash
poetry shell
```

### 5. Run database migrations (Optional)

```bash
poetry run alembic upgrade head
```

### 6. Start the application

```bash
poetry run python main.py
```

The API will be available at http://localhost:8000

### 6. Verify it's working

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

## Project Structure

```
src/
  application/          # FastAPI app, DI container, lifecycle
  domain/
    etl/                # Data extraction, transformation, enrichment
    signals/            # Signal generation and aggregation
    strategies/         # Backtesting engine and strategy selection
    portfolio/          # Portfolio optimization (Markowitz, HRP)
    trading/            # Trade execution (FakeBroker for dev)
  infrastructure/
    broker/             # Broker clients (IOL, FakeBroker)
    data/               # Data providers (yfinance)
    database/           # SQLAlchemy models and repositories
    scheduler/          # APScheduler jobs
    config/             # Settings and configuration
```

## Architecture

### Signals Engine
Transforms OHLCV data into actionable signals:
- Technical indicators (pandas-ta): RSI, MACD, Bollinger Bands, etc.
- Custom analyzers: Breakout, Fair Value Gap, Trend
- Interpreters: Momentum, Structure, Volume, Volatility, Risk

### Strategy Selection
Backtesting engine powered by `backtesting.py`:
1. Fetches historical data from yfinance
2. Runs signal engine
3. Evaluates multiple strategies
4. Ranks by Sharpe ratio, drawdown, win rate
5. Persists best strategy per symbol

### Portfolio Optimization
Two optimizers available:
- **Markowitz**: Mean-variance optimization (max Sharpe)
- **HRP**: Hierarchical Risk Parity

### Scheduled Jobs
- `StrategyPerTickerJob`: Monthly strategy re-evaluation
- `GenerateSignalsJob`: Hourly signal generation
- `PortfolioWeightsJob`: Monthly portfolio rebalancing

## Development

### Run tests

```bash
poetry run pytest
```

### Manual backtest

```bash
# Via API
curl http://localhost:8000/api/v1/research/run?symbol=AAPL.BA
```

### Environment modes

- `development`: Auto-creates default portfolio, enables hot reload
- `production`: Requires manual setup, no auto-seeding

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_URL` | PostgreSQL connection string | - |
| `ENVIRONMENT` | development/production | development |
| `LOG_LEVEL` | DEBUG/INFO/WARNING/ERROR | INFO |
| `SCHEDULER_TIMEZONE` | Timezone for jobs | America/Argentina/Buenos_Aires |
| `IOL_USERNAME` | IOL broker username | - |
| `IOL_PASSWORD` | IOL broker password | - |

## Stopping the application

```bash
# Stop the API (Ctrl+C in the terminal)

# Stop Docker services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

## License

MIT
