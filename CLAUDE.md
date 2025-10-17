# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**cheqmate** is a Telegram bot that recognizes and extracts items from receipt photos using AI-powered OCR with Claude Vision.

## Technology Stack

- **Python 3.13**: Required Python version
- **uv**: Package and dependency manager
- **python-telegram-bot**: Telegram bot framework with async support
- **Anthropic Claude**: Claude Vision API for receipt OCR
- **httpx**: Async HTTP client
- **Pydantic**: Data validation and settings management

## Development Setup

### Initial Project Setup

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

1. **Bot Handler** - Telegram bot interface that receives receipt photos
2. **Receipt Scanner** - OCR engine using Claude Vision to extract items, prices, and totals from receipt photos
3. **Conversation Manager** - In-memory session state management per chat

### Data Flow

```
User sends /new_bill
    ↓
User sends receipt photo
    ↓
Receipt OCR (Claude Vision) → Extract line items & prices
    ↓
Display extracted items to user
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

- `TELEGRAM_BOT_TOKEN`: Get from [@BotFather](https://t.me/botfather) on Telegram
- `ANTHROPIC_API_KEY`: For Claude Vision receipt OCR
- `DEBUG`: Debug mode (default: `True`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

## Project Structure Conventions

- Use `src/` directory for main application code
- Use `tests/` directory for test files (mirror src/ structure)
- Configuration files at project root
- Keep sensitive data in `.env` (gitignored)
