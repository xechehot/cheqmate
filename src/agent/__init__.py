"""Agent package for agentic bill splitting orchestration.

This package implements a ReAct-based agent that uses 20 atomic tools
to flexibly orchestrate the bill splitting workflow.
"""

from src.agent.handlers import (
    handle_new_bill,
    handle_photo_message,
    handle_text_message,
)
from src.agent.orchestrator import orchestrator

__all__ = [
    "orchestrator",
    "handle_new_bill",
    "handle_text_message",
    "handle_photo_message",
]
