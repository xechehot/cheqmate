"""Phoenix tracing instrumentation for CheqMate agent and LLM calls.

This module sets up Arize Phoenix for observability of:
- Anthropic API calls (agent orchestrator, OCR, bill splitting)
- Agent iterations and tool executions
- LLM prompts, responses, and token usage
- Timing and performance metrics
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Global reference to tracer provider for cleanup
_tracer_provider: Any = None


def initialize_phoenix(
    endpoint: str = "http://localhost:4317",
    enabled: bool = True,
    auto_instrument: bool = True,
) -> None:
    """
    Initialize Phoenix tracing using phoenix.otel.register.

    This sets up:
    1. OpenInference TracerProvider with OTLP exporter to Phoenix
    2. Auto-instrumentation for Anthropic SDK (captures all API calls)
    3. Decorator support for @tracer.agent, @tracer.chain, @tracer.tool

    Args:
        endpoint: Phoenix OTLP gRPC endpoint (default: http://localhost:4317)
        enabled: Enable or disable tracing (useful for testing)
        auto_instrument: Auto-instrument Anthropic SDK (default: True)

    Example:
        >>> from src.observability import initialize_phoenix
        >>> initialize_phoenix(endpoint="http://localhost:4317")
    """
    if not enabled:
        logger.info("Phoenix tracing is disabled")
        return

    try:
        from phoenix.otel import register

        logger.info(f"Initializing Phoenix tracing with endpoint: {endpoint}")

        # Register Phoenix with OpenInference TracerProvider
        # This provides decorator support and helper methods
        global _tracer_provider
        _tracer_provider = register(
            endpoint=endpoint,
            project_name="cheqmate-agent",
            batch=True,  # Use BatchSpanProcessor for better performance
            set_global_tracer_provider=True,
            verbose=False,  # Reduce console output
        )

        logger.info("Phoenix tracer provider configured successfully")

        # Auto-instrument Anthropic SDK
        if auto_instrument:
            try:
                from openinference.instrumentation.anthropic import (
                    AnthropicInstrumentor,
                )

                AnthropicInstrumentor().instrument(tracer_provider=_tracer_provider)
                logger.info("Anthropic SDK auto-instrumentation enabled")
            except ImportError as e:
                logger.warning(
                    f"Failed to import Anthropic instrumentor: {e}. "
                    "Install with: uv add openinference-instrumentation-anthropic"
                )

        logger.info(
            "Phoenix tracing initialized successfully. "
            "View traces at http://localhost:6006"
        )

    except ImportError as e:
        logger.warning(
            f"Failed to initialize Phoenix tracing: {e}. "
            "Install dependencies with: uv sync"
        )
    except Exception as e:
        logger.error(f"Error initializing Phoenix tracing: {e}", exc_info=True)


def shutdown_phoenix() -> None:
    """
    Shutdown Phoenix tracing and flush remaining spans.

    Call this before application exit to ensure all traces are sent.
    """
    global _tracer_provider
    if _tracer_provider is not None:
        try:
            logger.info("Shutting down Phoenix tracing and flushing spans...")
            _tracer_provider.shutdown()
            logger.info("Phoenix tracing shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down Phoenix tracing: {e}", exc_info=True)


def get_tracer(name: str = "cheqmate.agent"):
    """
    Get a tracer for creating custom spans.

    This is useful for tracing custom operations like:
    - Agent iterations
    - Tool executions
    - Business logic steps

    Args:
        name: Name of the tracer (default: "cheqmate.agent")

    Returns:
        OpenTelemetry Tracer instance or NoOpTracer if Phoenix not initialized

    Example:
        >>> from src.observability.phoenix import get_tracer
        >>> tracer = get_tracer()
        >>> with tracer.start_as_current_span("agent_iteration"):
        ...     # Your code here
        ...     pass
    """
    # Check if Phoenix was initialized
    if _tracer_provider is None:
        logger.debug("Phoenix not initialized. Returning no-op tracer.")
        return _NoOpTracer()

    try:
        # Get tracer directly from OpenInference TracerProvider
        # This ensures we get an OpenInference-aware tracer with support for:
        # - openinference_span_kind parameter
        # - Decorator methods (@tracer.agent, @tracer.chain, @tracer.tool)
        # - Span helper methods (span.set_input(), span.set_output())
        return _tracer_provider.get_tracer(name)
    except Exception as e:
        logger.warning(f"Failed to get OpenInference tracer: {e}. Returning no-op tracer.")
        return _NoOpTracer()


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""

    def start_as_current_span(
        self, name: str, *, openinference_span_kind=None, **kwargs
    ):
        """No-op context manager that returns a no-op span."""
        from contextlib import nullcontext

        # Return a nullcontext with a no-op span object
        return nullcontext(enter_result=_NoOpSpan())

    # Decorator methods
    def agent(self, func):
        """No-op agent decorator."""
        return func

    def chain(self, func):
        """No-op chain decorator."""
        return func

    def tool(self, func):
        """No-op tool decorator."""
        return func


class _NoOpSpan:
    """No-op span for when OpenTelemetry is not available."""

    def set_attribute(self, key: str, value: any) -> None:
        """No-op attribute setter."""
        pass

    def set_input(self, value: any) -> None:
        """No-op input setter."""
        pass

    def set_output(self, value: any) -> None:
        """No-op output setter."""
        pass

    def set_status(self, status: any) -> None:
        """No-op status setter."""
        pass
