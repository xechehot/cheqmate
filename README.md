# cheqmate 🧾

**AI-powered receipt recognition for Telegram.**

A Telegram bot that extracts items, prices, and totals from receipt photos using Claude Vision API. Perfect for digitizing receipts and understanding what you paid for.

## What is this?

cheqmate makes receipt scanning simple:

1. **Use `/new_bill` to start** - Begin a new receipt recognition session
2. **Snap a photo of the receipt** - AI reads it using Claude Vision (works with any language!)
3. **Get the items** - Automatically extracts all items with prices and quantities

Perfect for tracking expenses, understanding receipts, or building expense management workflows.

## Prerequisites

- **Python 3.13+**
- **uv** - Fast Python package manager ([install here](https://docs.astral.sh/uv/))
- **API Keys:**
  - [Telegram Bot Token](https://t.me/botfather) (free)
  - [Anthropic API Key](https://console.anthropic.com/) (for Claude Vision)

## Get Started

```bash
# Clone the repo
git clone https://github.com/xechehot/cheqmate.git
cd cheqmate

# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys
```

## How to Run

### Run the bot

```bash
uv run python main.py
```

### Run tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_splitter.py

# With coverage
uv run pytest --cov
```

### Development tools

```bash
# Type checking
uv run mypy .

# Linting
uv run ruff check .

# Auto-format code
uv run ruff format .
```

## Architecture

```
User sends /new_bill
         ↓
User sends receipt photo
         ↓
Claude Vision API → Extract receipt items & prices
         ↓
Display formatted results
```

## Tech Stack

- **Python 3.13** + **uv**
- **python-telegram-bot** - Bot framework
- **Anthropic Claude** - Claude Vision API for receipt OCR
- **Pydantic** - Data validation and settings
- **httpx** - Async HTTP client

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines and architecture details.

## License

MIT License - see [LICENSE](LICENSE) for details.
