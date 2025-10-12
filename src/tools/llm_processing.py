"""LLM processing tools for AI-powered bill splitting operations.

These tools use Anthropic Claude for:
- Receipt OCR (vision)
- Bill splitting assignment
- Split refinement based on discrepancies
"""

import json
import logging
from decimal import Decimal

from src.models.bill import BillSplit, ParticipantItem, ParticipantShare, ReceiptData
from src.services.anthropic_service import (
    AnthropicService,
    extract_json_from_response,
)

logger = logging.getLogger(__name__)


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
    # Auto-retrieve from session if not provided
    if image_bytes is None:
        from src.bot.conversation_manager import conversation_manager

        session = conversation_manager.get_session(chat_id)
        if not session.has_image_bytes():
            raise ValueError(
                "No image bytes available. Call download_telegram_photo first or provide image_bytes parameter."
            )
        image_bytes = session.image_bytes
        logger.info("Retrieved cached image bytes from session for OCR")

    service = AnthropicService()
    receipt_data = await service.extract_receipt_items(image_bytes)
    logger.info(
        f"OCR extracted {len(receipt_data.items)} items in {receipt_data.currency}"
    )
    return receipt_data


async def create_initial_bill_split(
    description: str, receipt_data: ReceiptData, image_bytes: bytes
) -> BillSplit:
    """
    Create initial bill split by assigning items to participants.

    This is a wrapper around AnthropicService.split_bill.

    Args:
        description: User's description of who ate what
        receipt_data: Complete receipt data including items and totals
        image_bytes: Raw bytes of the receipt image (for reference)

    Returns:
        BillSplit object with participant assignments

    Raises:
        ValueError: If split creation fails
    """
    service = AnthropicService()
    bill_split = await service.split_bill(description, receipt_data, image_bytes)
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
            raise ValueError(f"Cannot refine split due to item matching error: {e}")

    participants_sum = sum(participant_totals.values())
    total_diff = abs(participants_sum - receipt_data.total)

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

    # Call Claude API for refinement
    message = service.client.messages.create(
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
            currency=receipt_data.currency,
            total=receipt_data.total,
        )

        explanation = refined_data.get("explanation", "Split refined for accuracy")
        logger.info(f"Successfully refined split: {explanation}")

        return (refined_split, explanation)

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Failed to parse refined split: {e}")
        logger.error(f"Raw response: {full_response}")
        raise ValueError(f"Failed to refine bill split: {e}")
