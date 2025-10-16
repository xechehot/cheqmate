"""Tool registry for Claude agent.

Defines tools in Anthropic format for the bill splitting agent.

IMPORTANT: Many tools were removed/automated by the workflow manager:
- /new_bill is handled deterministically (no tool needed)
- Photo OCR is automated when no OCR exists (no tool needed)
- State save/load operations are automated (no tools needed)

Reduced from 22 tools to 12 tools for efficiency.
"""

from typing import Any

# Tool definitions for Anthropic Claude function calling API
TOOLS: list[dict[str, Any]] = [
    # ===== USER INTERACTION TOOLS (6) =====
    {
        "name": "send_message",
        "description": "Send message to user (Markdown supported). Use for final summary or general communication.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Message text"}},
            "required": ["text"],
        },
    },
    {
        "name": "ask_clarification_question",
        "description": "Ask user a clarification question when input is ambiguous",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "Question"}},
            "required": ["question"],
        },
    },
    {
        "name": "send_processing_status",
        "description": "Send status update during long operations (e.g., 'Processing receipt...')",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Status message"}},
            "required": ["status"],
        },
    },
    {
        "name": "send_error_message",
        "description": "Send error message to user",
        "input_schema": {
            "type": "object",
            "properties": {"error": {"type": "string", "description": "Error text"}},
            "required": ["error"],
        },
    },
    {
        "name": "send_formatted_receipt",
        "description": "Send formatted receipt summary. Receipt data is automatically fetched from session (already extracted by workflow manager's OCR). NOTE: Workflow manager already sends this after OCR for standard flow. Use only if re-showing is needed.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "send_formatted_split",
        "description": "Send formatted split summary. Use after create_initial_bill_split and refine_split_with_llm. Receipt data is automatically fetched from session for currency/total display.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "BillSplit JSON"},
                "title": {"type": "string", "description": "Title (default: 'Bill Split - Draft')"},
            },
            "required": ["bill_split_json"],
        },
    },
    # ===== LLM PROCESSING TOOLS (3) =====
    # NOTE: extract_receipt_ocr removed - now automated by workflow manager
    {
        "name": "create_initial_bill_split",
        "description": "Create bill split from participant description. Receipt data is automatically fetched from session (already extracted by workflow manager's OCR).",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Who ate what (from user text)"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "refine_split_with_llm",
        "description": "Refine bill split when quality issues are detected. Use after evaluate_split_quality shows problems. Receipt data is automatically fetched from session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "Current BillSplit JSON"},
                "issue_explanation": {"type": "string", "description": "Detailed explanation of issues found"},
            },
            "required": ["bill_split_json", "issue_explanation"],
        },
    },
    {
        "name": "evaluate_bill_quality_with_llm",
        "description": "Use LLM to evaluate split quality qualitatively. Provides overall assessment, confidence, issues, and recommendations. Use after evaluate_split_quality. Receipt data is automatically fetched from session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "BillSplit JSON to evaluate"},
            },
            "required": ["bill_split_json"],
        },
    },
    # ===== QUALITY EVALUATION (1 CONSOLIDATED TOOL - replaces 4 calculation tools) =====
    {
        "name": "evaluate_split_quality",
        "description": "Comprehensive quality check (replaces 4 tools). Returns: participant_totals, participants_sum, receipt_total, total_discrepancy, unassigned_items, passes_accuracy_threshold, is_complete. ALWAYS use this before completing split. Receipt data is automatically fetched from session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "BillSplit JSON"},
                "tolerance": {"type": "number", "description": "Max acceptable discrepancy (default: 0.02)"},
            },
            "required": ["bill_split_json"],
        },
    },
]
