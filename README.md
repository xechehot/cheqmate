# cheqmate 🧾

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
  - [OpenAI API Key](https://platform.openai.com/api-keys) (for Whisper + GPT-4 Vision)
  - [Splitwise API](https://secure.splitwise.com/apps) (optional, for export)

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
- **OpenAI** - Whisper (voice) + GPT-4 Vision (OCR)
- **thefuzz** - Fuzzy string matching
- **SQLAlchemy** - Conversation state
- **Splitwise SDK** - Export integration

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines and architecture details.

## License

MIT License - see [LICENSE](LICENSE) for details.
