"""LLM processing tools for AI-powered bill splitting operations.

These tools use Anthropic Claude for:
- Receipt OCR (vision)
- Bill splitting assignment
- Split refinement based on discrepancies
- Quality evaluation
"""

import json
import logging
from decimal import Decimal
from typing import Any

from src.bot.conversation_manager import conversation_manager
from src.models.bill import BillSplit, ParticipantItem, ParticipantShare, ReceiptData
from src.observability.phoenix import get_tracer
from src.services.anthropic_service import (
    AnthropicService,
    extract_json_from_response,
)

logger = logging.getLogger(__name__)

# Initialize tracer for LLM processing tools
tracer = get_tracer("cheqmate.llm_processing")


async def extract_receipt_ocr(
    chat_id: int, image_bytes: bytes | None = None
) -> ReceiptData:
    """
    Extract items, prices, totals, and currency from a receipt image using Claude Vision.

    This is a wrapper around AnthropicService.extract_receipt_items.
    If image_bytes is not provided, it will be retrieved from the session cache
    (requires download_telegram_photo to have been called first).

    Args:
        chat_id: Telegram chat ID (for session retrieval)
        image_bytes: Raw bytes of the receipt image (optional - uses cached if not provided)

    Returns:
        ReceiptData object with all extracted information including currency

    Raises:
        ValueError: If OCR extraction fails or no image bytes available
    """
    with tracer.start_as_current_span(
        "extract_receipt_ocr", openinference_span_kind="tool"
    ) as span:
        span.set_attribute("llm.operation", "receipt_ocr")
        span.set_attribute("llm.chat_id", str(chat_id))

        # Auto-retrieve from session if not provided
        if image_bytes is None:
            session = conversation_manager.get_session(chat_id)
            if not session.has_image_bytes():
                raise ValueError(
                    "No image bytes available. Call download_telegram_photo first or provide image_bytes parameter."
                )
            image_bytes = session.image_bytes
            logger.info("Retrieved cached image bytes from session for OCR")
            span.set_attribute("llm.image_source", "session_cache")
        else:
            span.set_attribute("llm.image_source", "parameter")

        span.set_attribute("llm.image_size_kb", len(image_bytes) / 1024)

        service = AnthropicService()
        receipt_data = await service.extract_receipt_items(image_bytes)

        # Set output attributes
        span.set_attribute("llm.items_extracted", len(receipt_data.items))
        span.set_attribute("llm.currency", receipt_data.currency)
        span.set_attribute("llm.receipt_total", float(receipt_data.total))

        logger.info(
            f"OCR extracted {len(receipt_data.items)} items in {receipt_data.currency}"
        )
        return receipt_data


async def create_initial_bill_split(chat_id: int, description: str) -> BillSplit:
    """
    Create initial bill split by assigning items to participants.

    This is a TEXT-ONLY operation. The receipt_data is automatically retrieved
    from the session (where it was stored by the workflow manager's OCR process).

    This is a wrapper around AnthropicService.split_bill.

    Args:
        chat_id: Telegram chat ID (for session retrieval)
        description: User's description of who ate what

    Returns:
        BillSplit object with participant assignments

    Raises:
        ValueError: If split creation fails or no receipt data available in session
    """
    with tracer.start_as_current_span(
        "create_initial_bill_split", openinference_span_kind="tool"
    ) as span:
        span.set_attribute("llm.operation", "bill_split_creation")
        span.set_attribute("llm.chat_id", str(chat_id))
        span.set_attribute("llm.description_length", len(description))

        # Auto-retrieve receipt_data from session
        session = conversation_manager.get_session(chat_id)
        if not session.has_receipt_data():
            raise ValueError(
                "No receipt data available in session. OCR must be completed first."
            )
        receipt_data = session.receipt_data
        logger.info("Retrieved cached receipt data from session for bill split")
        span.set_attribute("llm.receipt_source", "session_cache")

        span.set_attribute("llm.receipt_items_count", len(receipt_data.items))
        span.set_attribute("llm.receipt_total", float(receipt_data.total))
        span.set_attribute("llm.currency", receipt_data.currency)

        service = AnthropicService()
        bill_split = await service.split_bill(description, receipt_data)

        # Set output attributes
        span.set_attribute("llm.participants_count", len(bill_split.participants))
        span.set_attribute(
            "llm.participant_names",
            ", ".join([p.name for p in bill_split.participants]),
        )

        logger.info(
            f"Created initial split with {len(bill_split.participants)} participants"
        )
        return bill_split


async def refine_split_with_llm(
    bill_split: BillSplit, receipt_data: ReceiptData, issue_explanation: str
) -> tuple[BillSplit, str]:
    """
    Use LLM to refine bill split based on identified issues.

    This is extracted from the LLM refinement portion of verify_and_refine_split.
    The agent should call this ONLY when it determines refinement is needed.

    Args:
        bill_split: Current bill split with issues
        receipt_data: Original receipt data for reference
        issue_explanation: Description of the issue (e.g., discrepancy details)

    Returns:
        Tuple of (refined_bill_split, explanation_text)

    Raises:
        ValueError: If refinement fails
    """
    with tracer.start_as_current_span(
        "refine_split_with_llm", openinference_span_kind="tool"
    ) as span:
        span.set_attribute("llm.operation", "bill_split_refinement")
        span.set_attribute("llm.participants_count", len(bill_split.participants))
        span.set_attribute("llm.receipt_items_count", len(receipt_data.items))
        span.set_attribute("llm.issue_explanation", issue_explanation[:200])

        service = AnthropicService()

        # Calculate current participant totals for context
        participant_totals: dict[str, Decimal] = {}
        for participant in bill_split.participants:
            try:
                participant_totals[participant.name] = participant.calculate_total(
                    receipt_data.items
                )
            except ValueError as e:
                logger.error(f"Calculation error for {participant.name}: {e}")
                span.set_attribute("llm.error", True)
                span.set_attribute("llm.error_message", str(e))
                raise ValueError(f"Cannot refine split due to item matching error: {e}")

        participants_sum = sum(participant_totals.values())
        total_diff = abs(participants_sum - receipt_data.total)

        # Set discrepancy attributes
        span.set_attribute("llm.participants_sum", float(participants_sum))
        span.set_attribute("llm.total_diff", float(total_diff))

        # Format participant data with calculated totals and items
        participants_text = []
        for participant in bill_split.participants:
            items_list = [
                f"{item.item_name} ({item.item_numerator}/{item.item_denominator})"
                for item in participant.items
            ]
            calculated = participant_totals[participant.name]
            participants_text.append(
                f"- {participant.name}:\n"
                f"  Items: {', '.join(items_list)}\n"
                f"  Calculated total: {calculated}"
            )

        participants_formatted = "\n".join(participants_text)

        # Format receipt items for reference
        receipt_items_text = "\n".join(
            [
                f"- {item.name}: {item.price} (x{item.quantity}) = {item.total_price}"
                for item in receipt_data.items
            ]
        )

        prompt = f"""You are refining a restaurant bill split for mathematical accuracy.

**Receipt Items (GROUND TRUTH):**
{receipt_items_text}

**Receipt Total (TARGET VALUE):**
Currency: {receipt_data.currency}
Total: {receipt_data.total}

**Current Split (Python-calculated totals):**
{participants_formatted}

**Sum of participant totals: {participants_sum}**
**Difference from receipt total: {total_diff}**

**Issue:**
{issue_explanation}

**Task:**
Analyze the item assignments and refine them to ensure:
1. All receipt items are assigned to participants
2. For shared items, numerators/denominators add up correctly (e.g., 2 people sharing = each gets 1/2)
3. The sum of calculated totals matches the receipt total

DO NOT calculate totals yourself - only adjust item assignments (numerators/denominators).
The system will recalculate totals based on receipt prices.

Output ONLY a valid JSON object with this structure (no markdown, no explanations):
{{
  "participants": [
    {{
      "name": "Person Name",
      "items": [
        {{
          "item_name": "item name from receipt",
          "item_numerator": 1,
          "item_denominator": 2
        }}
      ]
    }}
  ],
  "explanation": "Brief explanation of what was adjusted"
}}"""

        # Call Claude API for refinement (async, non-blocking)
        message = await service.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3072,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": [{"type": "text", "text": "{"}]},
            ],
        )

        # Extract and parse response
        response_text = message.content[0].text if message.content else ""
        full_response = "{" + response_text
        logger.info(f"LLM refinement response: {full_response}")

        json_text = extract_json_from_response(full_response)

        try:
            refined_data = json.loads(json_text)

            # Build refined ParticipantShare objects
            refined_participants = []
            for p in refined_data["participants"]:
                participant_items = [
                    ParticipantItem(
                        item_name=item["item_name"],
                        item_numerator=item["item_numerator"],
                        item_denominator=item["item_denominator"],
                    )
                    for item in p["items"]
                ]

                refined_participants.append(
                    ParticipantShare(
                        name=p["name"],
                        items=participant_items,
                    )
                )

            # Build refined BillSplit
            refined_split = BillSplit(
                participants=refined_participants,
                receipt_items=receipt_data.items,
            )

            explanation = refined_data.get("explanation", "Split refined for accuracy")

            # Set success attributes
            span.set_attribute("llm.refined_participants_count", len(refined_participants))
            span.set_attribute("llm.refinement_explanation", explanation[:200])

            logger.info(f"Successfully refined split: {explanation}")

            return (refined_split, explanation)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse refined split: {e}")
            logger.error(f"Raw response: {full_response}")
            span.set_attribute("llm.error", True)
            span.set_attribute("llm.error_message", str(e))
            raise ValueError(f"Failed to refine bill split: {e}")


async def evaluate_bill_quality_with_llm(
    bill_split: BillSplit, receipt_data: ReceiptData
) -> dict[str, Any]:
    """
    Use LLM to evaluate the quality of a bill split.

    This provides a qualitative assessment after the quantitative metrics
    from evaluate_split_quality. The LLM can catch issues that pure math
    might miss (e.g., illogical assignments, missing items, etc.).

    Args:
        bill_split: Complete bill split with participant assignments
        receipt_data: Original receipt data for reference

    Returns:
        Dictionary with evaluation results:
        {
            "overall_quality": "excellent" | "good" | "fair" | "poor",
            "confidence": float (0-1),
            "issues": [list of identified issues],
            "recommendations": [list of recommendations],
            "assessment": "human-readable summary"
        }

    Raises:
        ValueError: If evaluation fails
    """
    with tracer.start_as_current_span(
        "evaluate_bill_quality_with_llm", openinference_span_kind="tool"
    ) as span:
        span.set_attribute("llm.operation", "bill_quality_evaluation")
        span.set_attribute("llm.participants_count", len(bill_split.participants))
        span.set_attribute("llm.receipt_items_count", len(receipt_data.items))

        service = AnthropicService()

        # Calculate participant totals for context
        participant_totals: dict[str, Decimal] = {}
        for participant in bill_split.participants:
            try:
                participant_totals[participant.name] = participant.calculate_total(
                    receipt_data.items
                )
            except ValueError as e:
                logger.error(f"Calculation error for {participant.name}: {e}")
                span.set_attribute("llm.error", True)
                span.set_attribute("llm.error_message", str(e))
                raise ValueError(f"Cannot evaluate split due to item matching error: {e}")

        participants_sum = sum(participant_totals.values())
        total_diff = abs(participants_sum - receipt_data.total)

        # Format split for evaluation
        participants_text = []
        for participant in bill_split.participants:
            items_list = [
                f"{item.item_name} ({item.item_numerator}/{item.item_denominator})"
                for item in participant.items
            ]
            calculated = participant_totals[participant.name]
            participants_text.append(
                f"- {participant.name}:\n"
                f"  Items: {', '.join(items_list)}\n"
                f"  Total: {calculated}"
            )

        participants_formatted = "\n".join(participants_text)

        # Format receipt items
        receipt_items_text = "\n".join(
            [
                f"- {item.name}: {item.price} (x{item.quantity}) = {item.total_price}"
                for item in receipt_data.items
            ]
        )

        prompt = f"""You are evaluating the quality of a restaurant bill split.

**Receipt Items:**
{receipt_items_text}

**Receipt Total**: {receipt_data.total} {receipt_data.currency}

**Bill Split:**
{participants_formatted}

**Mathematical Summary:**
- Sum of participant totals: {participants_sum}
- Discrepancy from receipt: {total_diff}

**Task:**
Evaluate the quality of this bill split. Consider:
1. Are all items from the receipt assigned to participants?
2. Do the assignments make logical sense (no obvious errors)?
3. Is the mathematical accuracy acceptable (discrepancy < 0.02)?
4. Are shared items properly split (fractions add up correctly)?
5. Any items that seem incorrectly assigned?

Output ONLY a valid JSON object (no markdown, no explanations):
{{
  "overall_quality": "excellent" | "good" | "fair" | "poor",
  "confidence": 0.95,
  "issues": ["issue 1", "issue 2"],
  "recommendations": ["recommendation 1"],
  "assessment": "Brief overall assessment"
}}

Quality levels:
- excellent: Perfect split, no issues, discrepancy < 0.01
- good: Minor discrepancy or trivial issues, but acceptable
- fair: Notable issues that should be addressed
- poor: Significant problems, needs refinement"""

        # Call Claude API for evaluation
        message = await service.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": [{"type": "text", "text": "{"}]},
            ],
        )

        # Extract and parse response
        response_text = message.content[0].text if message.content else ""
        full_response = "{" + response_text
        logger.info(f"LLM quality evaluation response: {full_response}")

        json_text = extract_json_from_response(full_response)

        try:
            evaluation = json.loads(json_text)

            # Validate required fields
            required_fields = [
                "overall_quality",
                "confidence",
                "issues",
                "recommendations",
                "assessment",
            ]
            missing_fields = [f for f in required_fields if f not in evaluation]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")

            # Set success attributes
            span.set_attribute("llm.evaluation_quality", evaluation["overall_quality"])
            span.set_attribute("llm.evaluation_confidence", evaluation["confidence"])
            span.set_attribute("llm.issues_count", len(evaluation["issues"]))
            span.set_attribute(
                "llm.recommendations_count", len(evaluation["recommendations"])
            )

            logger.info(
                f"LLM evaluation: {evaluation['overall_quality']} "
                f"(confidence: {evaluation['confidence']}, "
                f"issues: {len(evaluation['issues'])}, "
                f"recommendations: {len(evaluation['recommendations'])})"
            )

            return evaluation

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse quality evaluation: {e}")
            logger.error(f"Raw response: {full_response}")
            span.set_attribute("llm.error", True)
            span.set_attribute("llm.error_message", str(e))
            raise ValueError(f"Failed to evaluate bill quality: {e}")
