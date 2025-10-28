"""Anthropic API service for receipt OCR."""

import base64
import json
import logging
import re
from decimal import Decimal

from anthropic import Anthropic

from src.config import settings
from src.models.bill import (
    BillSplit,
    ParticipantItem,
    ParticipantShare,
    Receipt,
    ReceiptItem,
    SplitDiscrepancy,
    format_currency,
)
from src.utils.bill_calculations import calculate_participant_total

logger = logging.getLogger(__name__)


def extract_json_from_response(text: str) -> str:
    """
    Extract JSON from Claude's response, removing markdown code blocks if present.

    Args:
        text: Raw response text from Claude

    Returns:
        Clean JSON string ready for parsing
    """
    # Remove markdown code blocks if present
    text = text.strip()

    # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
    code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(code_block_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text


def detect_image_media_type(image_bytes: bytes) -> str:
    """
    Detect the media type of an image from its bytes using magic number signatures.

    Args:
        image_bytes: Raw image bytes

    Returns:
        Media type string (e.g., "image/jpeg", "image/png")
    """
    # Check file signatures (magic numbers)
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"

    # Default to JPEG if unknown
    return "image/jpeg"


class AnthropicService:
    """Service for interacting with Anthropic's Claude API."""

    def __init__(self) -> None:
        """Initialize the Anthropic service."""
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key is required")
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    async def extract_receipt_items(self, image_bytes: bytes) -> Receipt:
        """
        Extract restaurant info, items, and total from a receipt image using Claude Vision.

        Args:
            image_bytes: Raw bytes of the receipt image

        Returns:
            Receipt object with restaurant info, items, and total
        """
        logger.info("Starting receipt OCR with Claude Vision")

        # Detect image media type and encode to base64
        media_type = detect_image_media_type(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Create structured prompt for receipt extraction with clear output format
        prompt = """Analyze this receipt image and extract restaurant info, items, currency, and total.

First, carefully examine the receipt to identify:
1. Restaurant name (usually at the top of the receipt)
2. Restaurant address (if visible on the receipt)
3. Currency (look for currency symbols like $, €, ₸, or currency codes like USD, EUR, KZT)
4. All individual items/dishes with their descriptions
5. Quantities (if specified, otherwise default to 1)
6. Line total for each item (the total amount charged for that line - this is ALWAYS shown on receipts)
7. Unit price for each item (if shown separately on the receipt - this is OPTIONAL)
8. Grand total (the final total amount)

IMPORTANT:
- "currency" should be the 3-letter currency code (USD, EUR, KZT, etc.) - identify from symbols or text on receipt
- "line_total" is the total price for that line item (quantity × unit_price) - ALWAYS present on receipt
- "unit_price" is optional - only include it if explicitly shown on the receipt
- If unit_price is not shown, omit it (it will be calculated automatically)
- restaurant_name and restaurant_address can be null if not visible on the receipt
- If currency is unclear, default to "USD"

Then output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{
  "restaurant_name": "Restaurant Name",
  "restaurant_address": "123 Main St, City, State",
  "currency": "USD",
  "items": [
    {"description": "item description", "line_total": 25.00, "quantity": 2, "unit_price": 12.50}
  ],
  "total": 64.50
}

Note: unit_price is optional in the items array. restaurant_name and restaurant_address can be null if not found."""

        # Call Claude API with vision and response prefilling
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "{"}],
                },
            ],
        )

        # Extract text response
        response_text = message.content[0].text if message.content else ""
        # Prepend the prefilled "{" back to make valid JSON
        full_response = "{" + response_text
        logger.debug(f"Claude Vision response: {full_response}")

        # Extract JSON from potential markdown wrapper
        json_text = extract_json_from_response(full_response)

        # Parse JSON response
        try:
            receipt_data = json.loads(json_text)

            # Parse items
            items = [
                ReceiptItem(
                    description=item["description"],
                    line_total=Decimal(str(item["line_total"])),
                    quantity=item.get("quantity", 1),
                    unit_price=Decimal(str(item["unit_price"]))
                    if "unit_price" in item and item["unit_price"] is not None
                    else None,
                )
                for item in receipt_data["items"]
            ]

            # Create Receipt object
            receipt = Receipt(
                restaurant_name=receipt_data.get("restaurant_name"),
                restaurant_address=receipt_data.get("restaurant_address"),
                currency=receipt_data.get("currency", "USD"),
                items=items,
                total=Decimal(str(receipt_data["total"])),
            )

            total_fmt = format_currency(receipt.total, receipt.currency)
            logger.info(
                f"Extracted receipt from {receipt.restaurant_name or 'Unknown'} with {len(items)} items, total: {total_fmt}"
            )
            return receipt
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse receipt data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to extract receipt items: {e}")

    async def split_bill(
        self, participant_description: str, receipt: Receipt
    ) -> BillSplit:
        """
        Split the bill among participants based on description and receipt.

        Args:
            participant_description: User's description of who ate what
            receipt: Receipt object with items and total

        Returns:
            BillSplit object with proportional split information
        """
        logger.info("Starting bill split with Claude")

        # Format receipt items for prompt
        items_text = "\n".join(
            [
                f"- {item.description}: {format_currency(item.line_total, receipt.currency)}"
                + (f" (x{item.quantity})" if item.quantity > 1 else "")
                for item in receipt.items
            ]
        )

        # Format total for display
        total_fmt = format_currency(receipt.total, receipt.currency)

        # Create structured prompt for bill splitting
        prompt = f"""You are helping split a restaurant bill among friends.

**What participants ordered (from user description):**
{participant_description}

**Receipt items extracted:**
{items_text}

**Total bill amount: {total_fmt}**

**Task:**
1. Analyze the participant description to identify each person's name
2. Match what items each person ordered to the receipt items (use exact or fuzzy matching)
3. For each item a person ordered, determine the fractional quantity:
   - line_nominator: how many shares/portions this person has (numerator)
   - line_denominator: total number of shares/portions for this item (denominator)
4. Handle shared items by assigning fractional quantities to each person who shared

**Examples:**
- If Alice had 1 burger and there were 2 burgers total on the receipt: {{"item_name": "Burger", "line_nominator": 1, "line_denominator": 2}}
- If Bob and Carol shared a salad equally: Both get {{"item_name": "Salad", "line_nominator": 1, "line_denominator": 2}}
- If Dave had an entire pasta dish: {{"item_name": "Pasta", "line_nominator": 1, "line_denominator": 1}}

**Important:**
- ONLY include items that exist on the receipt (exclude items not found on receipt)
- Use exact or close-matching item names from the receipt
- line_nominator and line_denominator must be positive integers
- For full (unshared) items, use line_nominator=1 and line_denominator=1
- DO NOT calculate amounts - only provide item names and fractional quantities

Output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{{
  "participants": [
    {{
      "name": "Person Name",
      "items": [
        {{
          "item_name": "Burger",
          "line_nominator": 1,
          "line_denominator": 2
        }},
        {{
          "item_name": "Salad",
          "line_nominator": 1,
          "line_denominator": 1
        }}
      ]
    }}
  ]
}}"""

        # Call Claude API with response prefilling
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3072,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "{"}],
                },
            ],
        )

        # Extract text response
        response_text = message.content[0].text if message.content else ""
        # Prepend the prefilled "{" back to make valid JSON
        full_response = "{" + response_text
        logger.debug(f"Claude split response: {full_response}")

        # Extract JSON from potential markdown wrapper
        json_text = extract_json_from_response(full_response)

        # Parse JSON response
        try:
            split_data = json.loads(json_text)

            # Build ParticipantShare objects with ParticipantItem objects
            participants = []
            for p in split_data["participants"]:
                # Parse ParticipantItem objects
                participant_items = [
                    ParticipantItem(
                        item_name=item["item_name"],
                        line_nominator=item["line_nominator"],
                        line_denominator=item["line_denominator"],
                    )
                    for item in p["items"]
                ]

                # Calculate amount using Python (not from LLM)
                calculated_amount = calculate_participant_total(
                    participant_items, receipt.items
                )

                # Create ParticipantShare with calculated amount
                participant_share = ParticipantShare(
                    name=p["name"],
                    items=participant_items,
                    amount=calculated_amount,
                )
                participants.append(participant_share)

            # Build BillSplit object
            bill_split = BillSplit(
                participants=participants,
                receipt=receipt,
            )

            logger.info(
                f"Successfully split bill among {len(participants)} participants"
            )
            return bill_split

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse split data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to split bill: {e}")

    async def refine_bill_split(
        self,
        receipt: Receipt,
        initial_split: BillSplit,
        discrepancy: SplitDiscrepancy,
    ) -> BillSplit:
        """
        Refine a bill split by analyzing discrepancies and improving assignments.

        This method uses Claude to improve the initial split by:
        1. Assigning missed items to appropriate participants
        2. Adjusting fractional shares to match the receipt total
        3. Balancing the split to minimize discrepancies

        Args:
            receipt: Original receipt with all items
            initial_split: Initial bill split to refine
            discrepancy: Analysis of discrepancies in the initial split

        Returns:
            Refined BillSplit object with improved assignments
        """
        logger.info("Starting bill split refinement with Claude")

        # Format receipt items
        items_text = "\n".join(
            [
                f"- {item.description}: {format_currency(item.line_total, receipt.currency)}"
                + (f" (x{item.quantity})" if item.quantity > 1 else "")
                for item in receipt.items
            ]
        )

        # Format current participant assignments
        participants_text = []
        for participant in initial_split.participants:
            items_list = []
            for item in participant.items:
                if item.line_nominator == item.line_denominator:
                    items_list.append(f"{item.item_name} (full)")
                else:
                    items_list.append(
                        f"{item.item_name} ({item.line_nominator}/{item.line_denominator})"
                    )
            participant_amount = format_currency(participant.amount, receipt.currency)
            participants_text.append(
                f"- {participant.name}: {', '.join(items_list)} → {participant_amount}"
            )
        participants_summary = "\n".join(participants_text)

        # Format missed items
        if discrepancy.missed_items:
            missed_text = "\n".join(
                [
                    f"- {item.description}: {format_currency(item.line_total, receipt.currency)}"
                    for item in discrepancy.missed_items
                ]
            )
        else:
            missed_text = "None - all items assigned"

        # Format detailed item assignment analysis (NEW)
        if discrepancy.item_details:
            item_details_lines = []
            for detail in discrepancy.item_details:
                item_name = detail.receipt_item.description
                assigned_frac = detail.assigned_fraction
                unassigned_frac = detail.unassigned_fraction
                unassigned_amt = abs(detail.unassigned_amount)
                unassigned_amt_fmt = format_currency(unassigned_amt, receipt.currency)

                if detail.status == "under_assigned":
                    item_details_lines.append(
                        f"- {item_name}: {assigned_frac:.2f}/1.0 assigned, "
                        f"{unassigned_frac:.2f} unassigned → {unassigned_amt_fmt} MISSING"
                    )
                elif detail.status == "over_assigned":
                    item_details_lines.append(
                        f"- {item_name}: {assigned_frac:.2f}/1.0 assigned "
                        f"(OVER-ASSIGNED by {abs(unassigned_frac):.2f} → {unassigned_amt_fmt} EXTRA)"
                    )
            item_details_text = "\n".join(item_details_lines)
        else:
            item_details_text = "None - all items perfectly assigned"

        # Format discrepancy information
        total_fmt = format_currency(receipt.total, receipt.currency)
        split_total_fmt = format_currency(discrepancy.split_total, receipt.currency)
        difference_fmt = format_currency(
            abs(discrepancy.total_difference), receipt.currency
        )
        difference_direction = "under" if discrepancy.total_difference > 0 else "over"

        # Create refinement prompt
        prompt = f"""You are refining a bill split that has discrepancies. Your task is to improve the split so that:
1. All receipt items are assigned to participants
2. The sum of participant totals matches the receipt total as closely as possible

**Receipt Items:**
{items_text}
**Receipt Total: {total_fmt}**

**Current Split (INITIAL VERSION):**
{participants_summary}
**Current Split Total: {split_total_fmt}**

**Discrepancy Analysis:**
- Difference: {difference_fmt} {difference_direction} (split is {discrepancy.total_difference:+.2f})
- Percentage: {discrepancy.percentage_difference:.2f}%

**Item Assignment Issues:**
{item_details_text}

**Missed Items (completely unassigned):**
{missed_text}

**Your Task:**
1. Review the current split and identify issues:
   - Which items are under-assigned (not fully assigned to participants)?
   - Which items are over-assigned (assigned more than they should be)?
   - Which items from the receipt are NOT assigned to any participant at all?
2. Refine the split to fix these issues:
   - For UNDER-ASSIGNED items: increase the fractional assignments or assign the missing portions to appropriate participants
   - For OVER-ASSIGNED items: reduce the fractional assignments to match the actual item quantity
   - For MISSED items: assign them to the appropriate participants (infer from context who likely had these items)
   - If you cannot determine who had an item, distribute it equally among all participants
   - Adjust fractional quantities to ensure each receipt item is assigned exactly 1.0 total (not more, not less)
3. Ensure the refined split total matches the receipt total as closely as possible

**Important Rules:**
- ONLY use item names that exist on the receipt (from the "Receipt Items" list above)
- Use exact or close-matching item names from the receipt
- line_nominator and line_denominator must be positive integers
- For full (unshared) items, use line_nominator=1 and line_denominator=1
- For shared items, fractions across all participants should sum to 1.0 (e.g., two people sharing = 1/2 each)
- DO NOT calculate amounts - only provide item names and fractional quantities

Output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{{
  "participants": [
    {{
      "name": "Person Name",
      "items": [
        {{
          "item_name": "Item from receipt",
          "line_nominator": 1,
          "line_denominator": 1
        }}
      ]
    }}
  ]
}}"""

        # Call Claude API with response prefilling
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3072,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "{"}],
                },
            ],
        )

        # Extract text response
        response_text = message.content[0].text if message.content else ""
        # Prepend the prefilled "{" back to make valid JSON
        full_response = "{" + response_text
        logger.debug(f"Claude refinement response: {full_response}")

        # Extract JSON from potential markdown wrapper
        json_text = extract_json_from_response(full_response)

        # Parse JSON response
        try:
            split_data = json.loads(json_text)

            # Build ParticipantShare objects with ParticipantItem objects
            participants = []
            for p in split_data["participants"]:
                # Parse ParticipantItem objects
                participant_items = [
                    ParticipantItem(
                        item_name=item["item_name"],
                        line_nominator=item["line_nominator"],
                        line_denominator=item["line_denominator"],
                    )
                    for item in p["items"]
                ]

                # Calculate amount using Python (not from LLM)
                calculated_amount = calculate_participant_total(
                    participant_items, receipt.items
                )

                # Create ParticipantShare with calculated amount
                participant_share = ParticipantShare(
                    name=p["name"],
                    items=participant_items,
                    amount=calculated_amount,
                )
                participants.append(participant_share)

            # Build refined BillSplit object
            refined_split = BillSplit(
                participants=participants,
                receipt=receipt,
            )

            logger.info(
                f"Successfully refined bill split with {len(participants)} participants"
            )
            return refined_split

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse refined split data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to refine bill split: {e}")
