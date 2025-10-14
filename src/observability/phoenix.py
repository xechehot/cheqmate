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
    Initialize Phoenix tracing with OpenTelemetry instrumentation.

    This sets up:
    1. OpenTelemetry tracer provider with OTLP exporter to Phoenix
    2. Auto-instrumentation for Anthropic SDK (captures all API calls)
    3. Optional: Custom spans for agent iterations and tool execution

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
        # Import Phoenix OTEL with lazy loading to avoid import errors if not installed
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        logger.info(f"Initializing Phoenix tracing with endpoint: {endpoint}")

        # Create resource with service name
        resource = Resource.create(
            {
                "service.name": "cheqmate-agent",
                "service.version": "0.1.0",
            }
        )

        # Create tracer provider
        global _tracer_provider
        _tracer_provider = TracerProvider(resource=resource)

        # Create OTLP exporter to Phoenix
        otlp_exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=True,  # Use insecure connection for local dev
        )

        # Add batch span processor for better performance
        span_processor = BatchSpanProcessor(otlp_exporter)
        _tracer_provider.add_span_processor(span_processor)

        # Set as global tracer provider
        from opentelemetry import trace

        trace.set_tracer_provider(_tracer_provider)

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
        OpenTelemetry Tracer instance

    Example:
        >>> from src.observability.phoenix import get_tracer
        >>> tracer = get_tracer()
        >>> with tracer.start_as_current_span("agent_iteration"):
        ...     # Your code here
        ...     pass
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        logger.warning("OpenTelemetry not available. Returning no-op tracer.")
        # Return a no-op tracer that does nothing
        return _NoOpTracer()


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""

    def start_as_current_span(self, name: str, *args, **kwargs):
        """No-op context manager."""
        from contextlib import nullcontext

        return nullcontext()
