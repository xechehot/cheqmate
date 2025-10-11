# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**cheqmate** is a Telegram bot that splits restaurant bills using voice notes and receipt photos. It automatically assigns dishes to friends and exports splits to Splitwise/Tricount.

## Technology Stack

- **Python 3.13**: Required Python version
- **uv**: Package and dependency manager (replaces pip/poetry/pipenv)
- **Telegram Bot API**: For bot interaction
- **AI/ML Services**: Voice-to-text and OCR for receipt processing

## Development Setup

### Initial Project Setup

```bash
# Initialize uv project (if not already done)
uv init

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On macOS/Linux
# .venv\Scripts\activate   # On Windows

# Install dependencies
uv pip install -r requirements.txt  # or pyproject.toml
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
uv run python -m cheqmate  # or main entry point

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

- Store API keys and tokens in `.env` file (never commit this)
- Required environment variables:
  - `TELEGRAM_BOT_TOKEN`: Telegram bot API token
  - `SPLITWISE_API_KEY`: Splitwise API credentials
  - `TRICOUNT_API_KEY`: Tricount API credentials (if applicable)
  - AI service keys for voice/OCR processing

## Project Structure Conventions

- Use `src/` directory for main application code
- Use `tests/` directory for test files (mirror src/ structure)
- Configuration files at project root
- Keep sensitive data in `.env` (gitignored)
