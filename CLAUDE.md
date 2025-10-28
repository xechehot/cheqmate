# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**cheqmate** is a Telegram bot that splits restaurant bills using voice notes and receipt photos. It automatically assigns dishes to friends.

## Technology Stack

- **Python 3.13**: Required Python version
- **uv**: Package and dependency manager
- **python-telegram-bot**: Telegram bot framework with async support
- **OpenAI API**: Whisper for voice transcription, GPT-4 Vision for receipt OCR
- **Anthropic Claude**: Alternative vision API for receipt processing
- **thefuzz + python-Levenshtein**: Fuzzy string matching for dish assignment
- **Splitwise SDK**: Export functionality for Splitwise
- **httpx**: Async HTTP client for Tricount API
- **SQLAlchemy**: Database ORM for storing conversation state
- **Pydantic**: Data validation and settings management

## Development Setup

### GitHub Codespaces (Recommended for Quick Start)

The project is configured for GitHub Codespaces with a pre-built development environment:

**Quick Start:**
1. Click "Open in GitHub Codespaces" badge in README or visit: https://codespaces.new/xechehot/cheqmate
2. Environment automatically includes: Python 3.13, uv, npm, Claude Code CLI, and all dependencies
3. Add API keys as Codespaces secrets or edit `.env` file
4. Start coding immediately!

**Features:**
- Pre-configured VS Code with Python, Pylance, and Ruff extensions
- Automatic dependency installation via `uv sync`
- Fast startup (~10 seconds with prebuilds)
- Switch between branches/tags freely using Git commands

**Configuration Files:**
- `.devcontainer/devcontainer.json` - Container configuration
- `.devcontainer/post-create.sh` - Setup script (installs uv, Claude Code, dependencies)
- `.github/workflows/codespaces-prebuild.yml` - Prebuild workflow for fast startup

**Rebuilding Container:**
If you update devcontainer configuration, rebuild using:
- Command Palette (Cmd/Ctrl+Shift+P) → "Codespaces: Rebuild Container"

### Local Development Setup

```bash
# Project already initialized with uv
# Virtual environment created at .venv/

# Install all dependencies (production + dev)
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your actual API keys
```

### Common Commands

```bash
# Add a new dependency
uv add <package-name>

# Add a development dependency
uv add --dev <package-name>

# Update dependencies
uv lock
uv sync

# Run the bot
uv run python main.py

# Run tests
uv run pytest

# Run tests for a specific file
uv run pytest tests/test_<module>.py

# Run a specific test
uv run pytest tests/test_<module>.py::test_function_name

# Type checking
uv run mypy .

# Linting
uv run ruff check .

# Format code
uv run ruff format .
```

## Architecture Overview

The application follows a modular architecture with these key components:

### Core Modules

1. **Bot Handler** - Telegram bot interface that receives voice notes and photos
2. **Voice Processor** - Transcribes voice notes to extract order details and participant names
3. **Receipt Scanner** - OCR engine to extract items, prices, and totals from receipt photos
4. **Bill Splitter** - Logic to match dishes to people and calculate individual shares (including tax/tip)
5. **Export Service** - API integrations for Splitwise and Tricount

### Data Flow

```
User Input (Voice + Photo)
    ↓
Voice Transcription → Extract participants & verbal order
    ↓
Receipt OCR → Extract line items & prices
    ↓
Matching Engine → Auto-assign dishes to people
    ↓
Split Calculator → Calculate individual amounts
    ↓
Export Service → Push to Splitwise/Tricount
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

- `TELEGRAM_BOT_TOKEN`: Get from [@BotFather](https://t.me/botfather) on Telegram
- `ANTHROPIC_API_KEY`: OCR and bill split processing

## Project Structure Conventions

- Use `src/` directory for main application code
- Use `tests/` directory for test files (mirror src/ structure)
- Configuration files at project root
- Keep sensitive data in `.env` (gitignored)
