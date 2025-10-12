"""Tool registry for Claude agent - defines all 20 available tools in Anthropic format."""

from typing import Any

# Tool definitions for Anthropic Claude function calling API
TOOLS: list[dict[str, Any]] = [
    # ===== USER INTERACTION TOOLS (6) =====
    {
        "name": "send_message",
        "description": "Send a generic message to the user in Telegram. Use this to communicate results, status updates, or information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Message text to send (supports Markdown formatting)",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "request_participant_description",
        "description": "Ask the user to describe what each participant ate. Use this when you need the participant information and it's not yet provided.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "request_receipt_photo",
        "description": "Ask the user to send a photo of the receipt. Use this after you have the participant description but before you can process the bill.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ask_clarification_question",
        "description": "Ask the user a specific clarification question when information is ambiguous, unclear, or missing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The clarification question to ask the user",
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "send_processing_status",
        "description": "Send a status update to show processing progress (e.g., 'Processing receipt...', 'Analyzing items...', 'Verifying totals...').",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Status message to display to the user",
                }
            },
            "required": ["status"],
        },
    },
    {
        "name": "send_error_message",
        "description": "Send an error message to the user when something goes wrong that prevents completing the task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "error": {
                    "type": "string",
                    "description": "Error description to show to the user",
                }
            },
            "required": ["error"],
        },
    },
    # ===== STATE MANAGEMENT TOOLS (4) =====
    {
        "name": "get_participant_description",
        "description": "Retrieve the stored participant description from session state. Returns the description text if set, or None if not yet provided.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_receipt_file_id",
        "description": "Retrieve the stored receipt file ID from session state. Returns the Telegram file_id if a receipt photo was uploaded, or None if not yet provided.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_participant_description",
        "description": "Store the participant description in session state for later use.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "User's description of who ate what",
                }
            },
            "required": ["description"],
        },
    },
    {
        "name": "save_receipt_file_id",
        "description": "Store the receipt file ID in session state for later use.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "Telegram file ID of the receipt photo",
                }
            },
            "required": ["file_id"],
        },
    },
    # ===== TELEGRAM UTILITY TOOLS (3) =====
    {
        "name": "download_telegram_photo",
        "description": "Download a photo from Telegram by file ID and return the raw image bytes encoded as base64.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "Telegram file ID of the photo to download",
                }
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "get_latest_text_message",
        "description": "Extract text message content from the current Telegram update. Returns the text if available, or None if the user didn't send text.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "extract_file_id_from_message",
        "description": "Extract photo file ID from the current Telegram update. Returns the file_id if user sent a photo, or None otherwise.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # ===== LLM PROCESSING TOOLS (3) =====
    {
        "name": "extract_receipt_ocr",
        "description": "Extract items, prices, currency, and totals from a receipt image using Claude Vision OCR. Requires the raw image bytes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_bytes_base64": {
                    "type": "string",
                    "description": "Base64-encoded image bytes of the receipt (get from download_telegram_photo)",
                }
            },
            "required": ["image_bytes_base64"],
        },
    },
    {
        "name": "create_initial_bill_split",
        "description": "Create initial bill split by assigning receipt items to participants based on the description. This uses LLM to match participants to items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "User's description of who ate what",
                },
                "receipt_data_json": {
                    "type": "string",
                    "description": "JSON string of ReceiptData object (from extract_receipt_ocr)",
                },
                "image_bytes_base64": {
                    "type": "string",
                    "description": "Base64-encoded image bytes of the receipt",
                },
            },
            "required": ["description", "receipt_data_json", "image_bytes_base64"],
        },
    },
    {
        "name": "refine_split_with_llm",
        "description": "Use LLM to refine bill split when issues are detected (e.g., discrepancies, missing items). Provides corrected assignments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {
                    "type": "string",
                    "description": "JSON string of current BillSplit object",
                },
                "receipt_data_json": {
                    "type": "string",
                    "description": "JSON string of ReceiptData object",
                },
                "issue_explanation": {
                    "type": "string",
                    "description": "Clear description of the issue to fix (e.g., 'Discrepancy of 5.00 detected', 'Missing items: Pizza, Salad')",
                },
            },
            "required": ["bill_split_json", "receipt_data_json", "issue_explanation"],
        },
    },
    # ===== CALCULATION TOOLS (4) =====
    {
        "name": "calculate_all_participant_totals",
        "description": "Calculate the total amount each participant owes based on their assigned items and fractional ownership. Returns a dictionary of {name: total}.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {
                    "type": "string",
                    "description": "JSON string of BillSplit object",
                }
            },
            "required": ["bill_split_json"],
        },
    },
    {
        "name": "calculate_total_discrepancy",
        "description": "Calculate the absolute difference between sum of participant totals and the receipt total. Used to verify accuracy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {
                    "type": "string",
                    "description": "JSON string of BillSplit object",
                },
                "receipt_total": {
                    "type": "number",
                    "description": "Target total from receipt",
                },
            },
            "required": ["bill_split_json", "receipt_total"],
        },
    },
    {
        "name": "check_accuracy_threshold",
        "description": "Check if the split is mathematically accurate within an acceptable tolerance (default 0.02). Returns true if accurate, false otherwise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "discrepancy": {
                    "type": "number",
                    "description": "Absolute difference between calculated sum and target",
                },
                "tolerance": {
                    "type": "number",
                    "description": "Maximum acceptable difference (default 0.02)",
                },
            },
            "required": ["discrepancy"],
        },
    },
    {
        "name": "find_unassigned_items",
        "description": "Find receipt items that are not assigned to any participant. Returns a list of unassigned item names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bill_split_json": {
                    "type": "string",
                    "description": "JSON string of BillSplit object",
                },
                "receipt_data_json": {
                    "type": "string",
                    "description": "JSON string of ReceiptData object",
                },
            },
            "required": ["bill_split_json", "receipt_data_json"],
        },
    },
]
