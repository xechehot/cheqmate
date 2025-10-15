"""CheqMate - Telegram bot for smart restaurant bill splitting."""

import atexit
import logging
import sys

from src.bot import run_bot
from src.config import settings
from src.observability import shutdown_phoenix


def setup_logging() -> None:
    """Configure logging for the application."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce verbosity of some loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def main() -> None:
    """Main entry point for the application."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Phoenix tracing initializes automatically on import (see src/observability/phoenix.py)
    # Register shutdown handler to flush traces on exit
    atexit.register(shutdown_phoenix)

    try:
        logger.info("Starting CheqMate bot application")
        run_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        shutdown_phoenix()  # Flush traces on graceful shutdown
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        shutdown_phoenix()  # Flush traces on error
        sys.exit(1)


if __name__ == "__main__":
    main()
