#!/bin/bash
set -e

echo "========================================="
echo "Setting up cheqmate development environment..."
echo "========================================="

# Install uv
echo ""
echo "📦 Installing uv package manager..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Install Claude Code CLI
echo ""
echo "🤖 Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code

# Install Python dependencies
echo ""
echo "🐍 Installing Python dependencies with uv..."
uv sync

# Set up environment file
echo ""
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env file from .env.example"
    echo ""
    echo "⚠️  IMPORTANT: Please add your API keys to the .env file or Codespaces secrets:"
    echo "   - TELEGRAM_BOT_TOKEN (get from @BotFather on Telegram)"
    echo "   - ANTHROPIC_API_KEY (for Claude Vision OCR)"
    echo ""
    echo "   To add as Codespaces secrets:"
    echo "   1. Go to your GitHub settings > Codespaces > Secrets"
    echo "   2. Add the secrets there for automatic injection"
else
    echo "✅ .env file already exists"
fi

# Configure git remote
echo ""
echo "🔗 Configuring git remote..."
if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin https://github.com/xechehot/cheqmate.git
    echo "✅ Git remote 'origin' configured"
else
    echo "✅ Git remote 'origin' already exists"
fi

echo ""
echo "========================================="
echo "✨ Setup complete!"
echo "========================================="
echo ""
echo "Quick start commands:"
echo "  uv run python main.py          # Run the bot"
echo "  uv run pytest                  # Run tests"
echo "  uv run ruff check .            # Lint code"
echo "  uv run ruff format .           # Format code"
echo ""
