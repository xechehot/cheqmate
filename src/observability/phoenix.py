"""Phoenix tracing instrumentation for CheqMate agent and LLM calls.

This module sets up Arize Phoenix for observability of:
- Anthropic API calls (agent orchestrator, OCR, bill splitting)
- Agent iterations and tool executions
- LLM prompts, responses, and token usage
- Timing and performance metrics

Configuration via .env:
- PHOENIX_ENABLED: Enable/disable tracing (default: True)
- PHOENIX_COLLECTOR_ENDPOINT: Phoenix OTLP endpoint (default: http://localhost:4317)
"""

import logging

logger = logging.getLogger(__name__)

# Module-level initialization using config settings
# This happens at import time, ensuring tracing is available immediately
try:
    from src.config import settings
    from phoenix.otel import register
    from openinference.instrumentation.anthropic import AnthropicInstrumentor

    # Only initialize if Phoenix is enabled in config
    if settings.phoenix_enabled:
        logger.info(
            f"Initializing Phoenix tracing with endpoint: {settings.phoenix_collector_endpoint}"
        )

        # Register Phoenix tracer provider at module import time
        # This creates an OpenInference-aware TracerProvider
        tracer_provider = register(
            endpoint=settings.phoenix_collector_endpoint,
            project_name="cheqmate-agent",
        )

        # Auto-instrument Anthropic SDK to capture all API calls
        AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)

        logger.info(
            "Phoenix tracing initialized successfully. View traces at http://localhost:6006"
        )
    else:
        logger.info("Phoenix tracing disabled by config (PHOENIX_ENABLED=False)")
        tracer_provider = None

except ImportError as e:
    logger.warning(
        f"Failed to import Phoenix dependencies: {e}. "
        "Install with: uv add arize-phoenix openinference-instrumentation-anthropic"
    )
    tracer_provider = None

except Exception as e:
    logger.error(f"Failed to initialize Phoenix tracing: {e}", exc_info=True)
    tracer_provider = None


def get_tracer(name: str = "cheqmate.agent"):
    """
    Get a tracer for creating custom spans.

    This is used throughout the application to create spans for:
    - Handler entry points (Telegram message handlers)
    - Workflow orchestration steps
    - LLM processing operations
    - Tool executions

    Args:
        name: Name of the tracer (default: "cheqmate.agent")

    Returns:
        OpenTelemetry Tracer instance

    Raises:
        RuntimeError: If Phoenix is not initialized (disabled or failed to initialize)

    Example:
        >>> from src.observability.phoenix import get_tracer
        >>> tracer = get_tracer("my.component")
        >>> with tracer.start_as_current_span("my_operation", openinference_span_kind="chain"):
        ...     # Your code here
        ...     pass
    """
    if tracer_provider is None:
        raise RuntimeError(
            "Phoenix tracer not initialized. "
            "Check PHOENIX_ENABLED and PHOENIX_COLLECTOR_ENDPOINT in your .env file. "
            "Ensure Phoenix is running: docker compose up -d phoenix"
        )

    return tracer_provider.get_tracer(name)


def shutdown_phoenix() -> None:
    """
    Shutdown Phoenix tracing and flush remaining spans.

    This should be called before application exit to ensure all traces are sent.
    It's registered as an atexit handler in main.py.
    """
    if tracer_provider is not None:
        try:
            logger.info("Shutting down Phoenix tracing and flushing spans...")
            tracer_provider.shutdown()
            logger.info("Phoenix tracing shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down Phoenix tracing: {e}", exc_info=True)
