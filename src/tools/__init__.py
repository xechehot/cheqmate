"""Tools for agentic bill splitting workflow.

This package provides atomic, composable tools that an agent can use to orchestrate
the bill splitting process. Tools are organized into categories:

- user_interaction: Telegram I/O (sending/receiving messages)
- state_management: Session state access
- llm_processing: AI-powered operations (OCR, splitting, refinement)
- calculations: Pure Python mathematical operations (deprecated - use split_quality)
- split_quality: Consolidated quality evaluation (NEW - replaces 4 calculation tools)
"""

from src.tools.calculations import (
    calculate_all_participant_totals,
    calculate_total_discrepancy,
    check_accuracy_threshold,
    find_unassigned_items,
)
from src.tools.llm_processing import (
    create_initial_bill_split,
    evaluate_bill_quality_with_llm,
    extract_receipt_ocr,
    refine_split_with_llm,
)
from src.tools.split_quality import SplitQualityMetrics, evaluate_split_quality
from src.tools.state_management import (
    get_participant_description,
    get_receipt_file_id,
    save_receipt_file_id,
    update_participant_description,
)
from src.tools.user_interaction import (
    ask_clarification_question,
    download_telegram_photo,
    extract_file_id_from_message,
    get_latest_text_message,
    request_participant_description,
    request_receipt_photo,
    send_error_message,
    send_formatted_receipt,
    send_formatted_split,
    send_message,
    send_processing_status,
)

__all__ = [
    # User interaction
    "send_message",
    "request_participant_description",
    "request_receipt_photo",
    "ask_clarification_question",
    "send_processing_status",
    "send_error_message",
    "send_formatted_receipt",
    "send_formatted_split",
    "download_telegram_photo",
    "get_latest_text_message",
    "extract_file_id_from_message",
    # State management
    "get_participant_description",
    "get_receipt_file_id",
    "update_participant_description",
    "save_receipt_file_id",
    # LLM processing
    "extract_receipt_ocr",
    "create_initial_bill_split",
    "refine_split_with_llm",
    "evaluate_bill_quality_with_llm",
    # Split quality (NEW - consolidated)
    "evaluate_split_quality",
    "SplitQualityMetrics",
    # Calculations (DEPRECATED - kept for backward compatibility)
    "calculate_all_participant_totals",
    "calculate_total_discrepancy",
    "check_accuracy_threshold",
    "find_unassigned_items",
]
