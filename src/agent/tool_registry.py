"""Tool registry for Claude agent - defines all 22 tools in Anthropic format."""

from typing import Any

# Tool definitions for Anthropic Claude function calling API
TOOLS: list[dict[str, Any]] = [
    # ===== USER INTERACTION TOOLS (8) =====
    {
        "name": "send_message",
        "description": "Send message to user (Markdown supported)",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Message text"}},
            "required": ["text"],
        },
    },
    {
        "name": "request_participant_description",
        "description": "Ask user to describe who ate what",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "request_receipt_photo",
        "description": "Ask user to send receipt photo",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ask_clarification_question",
        "description": "Ask clarification question",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "Question"}},
            "required": ["question"],
        },
    },
    {
        "name": "send_processing_status",
        "description": "Send status update",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Status message"}},
            "required": ["status"],
        },
    },
    {
        "name": "send_error_message",
        "description": "Send error message",
        "input_schema": {
            "type": "object",
            "properties": {"error": {"type": "string", "description": "Error text"}},
            "required": ["error"],
        },
    },
    {
        "name": "send_formatted_receipt",
        "description": "Send formatted receipt summary. Use IMMEDIATELY after extract_receipt_ocr",
        "input_schema": {
            "type": "object",
            "properties": {
                "receipt_data_json": {"type": "string", "description": "ReceiptData JSON"}
            },
            "required": ["receipt_data_json"],
        },
    },
    {
        "name": "send_formatted_split",
        "description": "Send formatted split summary. Use after create_initial_bill_split and refine_split_with_llm",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "BillSplit JSON"},
                "title": {"type": "string", "description": "Title (default: 'Bill Split - Draft')"},
            },
            "required": ["bill_split_json"],
        },
    },
    # ===== STATE MANAGEMENT TOOLS (4) =====
    {
        "name": "get_participant_description",
        "description": "Get stored participant description",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_receipt_file_id",
        "description": "Get stored receipt file ID",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_participant_description",
        "description": "Save participant description",
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string", "description": "Who ate what"}},
            "required": ["description"],
        },
    },
    {
        "name": "save_receipt_file_id",
        "description": "Save receipt file ID",
        "input_schema": {
            "type": "object",
            "properties": {"file_id": {"type": "string", "description": "File ID"}},
            "required": ["file_id"],
        },
    },
    # ===== TELEGRAM UTILITY TOOLS (3) =====
    {
        "name": "download_telegram_photo",
        "description": "Download photo by file ID (auto-cached for OCR)",
        "input_schema": {
            "type": "object",
            "properties": {"file_id": {"type": "string", "description": "Photo file ID"}},
            "required": ["file_id"],
        },
    },
    {
        "name": "get_latest_text_message",
        "description": "Extract text from current update",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "extract_file_id_from_message",
        "description": "Extract photo file ID from current update",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ===== LLM PROCESSING TOOLS (3) =====
    {
        "name": "extract_receipt_ocr",
        "description": "OCR receipt image (uses cached image). No parameters needed",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_initial_bill_split",
        "description": "Create bill split from description and receipt data",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Who ate what"},
                "receipt_data_json": {"type": "string", "description": "ReceiptData JSON from OCR"},
            },
            "required": ["description", "receipt_data_json"],
        },
    },
    {
        "name": "refine_split_with_llm",
        "description": "Refine bill split when issues detected",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "Current BillSplit JSON"},
                "receipt_data_json": {"type": "string", "description": "ReceiptData JSON"},
                "issue_explanation": {"type": "string", "description": "Issue details"},
            },
            "required": ["bill_split_json", "receipt_data_json", "issue_explanation"],
        },
    },
    # ===== CALCULATION TOOLS (4) =====
    {
        "name": "calculate_all_participant_totals",
        "description": "Calculate total owed by each participant",
        "input_schema": {
            "type": "object",
            "properties": {"bill_split_json": {"type": "string", "description": "BillSplit JSON"}},
            "required": ["bill_split_json"],
        },
    },
    {
        "name": "calculate_total_discrepancy",
        "description": "Calculate difference between participant sum and receipt total",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "BillSplit JSON"},
                "receipt_total": {"type": "number", "description": "Receipt total"},
            },
            "required": ["bill_split_json", "receipt_total"],
        },
    },
    {
        "name": "check_accuracy_threshold",
        "description": "Check if split is accurate within tolerance (default 0.02)",
        "input_schema": {
            "type": "object",
            "properties": {
                "discrepancy": {"type": "number", "description": "Discrepancy value"},
                "tolerance": {"type": "number", "description": "Max difference (default 0.02)"},
            },
            "required": ["discrepancy"],
        },
    },
    {
        "name": "find_unassigned_items",
        "description": "Find items not assigned to any participant. Requires bill_split_json and receipt_data_json from current session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {"type": "string", "description": "BillSplit JSON"},
                "receipt_data_json": {"type": "string", "description": "ReceiptData JSON"},
            },
            "required": ["bill_split_json", "receipt_data_json"],
        },
    },
]
