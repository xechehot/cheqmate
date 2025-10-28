# cheqmate 🧾

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/xechehot/cheqmate)

**Split restaurant bills effortlessly with AI.**

A Telegram bot that takes your voice note + receipt photo and automatically splits the bill among friends. Just say who ordered what, snap a photo of the receipt, and let AI handle the rest.

## What is this?

cheqmate eliminates the tedious part of splitting restaurant bills:

1. **Record a voice note** - "Петя взял борщ и пиво, я взял салат..."
2. **Snap a photo of the receipt** - AI reads it (even in foreign languages!)
3. **Get the split** - Automatically matches dishes to people and calculates shares
4. **Export** - Send to Splitwise/Tricount with one tap

Perfect for group dinners where apps like Splitwise help track IOUs but don't simplify data entry.

## Prerequisites

- **Python 3.13+**
- **uv** - Fast Python package manager ([install here](https://docs.astral.sh/uv/))
- **API Keys:**
  - [Telegram Bot Token](https://t.me/botfather) (free)
  - Anthropic API Key - to OCR bill and then split it using LLM

## Quick Start with GitHub Codespaces

The fastest way to get started is using GitHub Codespaces - a fully configured development environment in your browser:

1. **Click the badge above** or [open in Codespaces](https://codespaces.new/xechehot/cheqmate)
2. **Wait ~10 seconds** for the environment to load (prebuilt!)
3. **Add your API keys** as Codespaces secrets:
   - Go to [GitHub Settings → Codespaces → Secrets](https://github.com/settings/codespaces)
   - Add `TELEGRAM_BOT_TOKEN`,
   - ADD `ANTHROPIC_API_KEY`,
   - Or manually edit the `.env` file in the codespace
4. **Run the bot**: `uv run python main.py`

### Working with branches and tags

You can easily switch between different versions:

```bash
# Switch to a specific branch
git checkout stage/split_bill_v0

# Switch to a specific tag
git checkout empty_bot

# Create a new branch
git checkout -b my-feature
```

No need to rebuild the container - just switch and code!

## Get Started (Local Development)

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
Voice Note → Whisper API → Extract participants & orders
Photo → GPT-4 Vision → Extract receipt items & prices
         ↓
   Fuzzy Matching → Assign dishes to people
         ↓
   Calculate Split → Including tax/tip
         ↓
   Export → Splitwise/Tricount
```

## Tech Stack

- **Python 3.13** + **uv**
- **python-telegram-bot** - Bot framework
- **thefuzz** - Fuzzy string matching
- **SQLAlchemy** - Conversation state

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines and architecture details.

## License

MIT License - see [LICENSE](LICENSE) for details.
