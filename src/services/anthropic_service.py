"""Anthropic API service for receipt OCR and bill splitting."""

import base64
import json
import logging
import re
from decimal import Decimal

from anthropic import Anthropic

from src.config import settings
from src.models.bill import BillSplit, ParticipantShare, ReceiptData, ReceiptItem

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

    async def extract_receipt_items(self, image_bytes: bytes) -> ReceiptData:
        """
        Extract items, prices, totals, and currency from a receipt image using Claude Vision.

        Args:
            image_bytes: Raw bytes of the receipt image

        Returns:
            ReceiptData object with all extracted information including currency
        """
        logger.info("Starting receipt OCR with Claude Vision")

        # Detect image media type and encode to base64
        media_type = detect_image_media_type(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Create structured prompt for receipt extraction with currency detection
        prompt = """Analyze this receipt image and extract all items with their prices and currency.

First, carefully examine the receipt to identify:
1. The currency used (look for currency symbols like $, €, £, ₸, ₽, etc. or ISO codes)
2. All individual items/dishes with their prices
3. Quantities (if specified, otherwise default to 1)
4. Subtotal (sum of all items)
5. Tax amount (if present, otherwise 0)
6. Tip/gratuity (if present, otherwise 0)
7. Grand total

Then output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{
  "currency": "USD",
  "items": [
    {"name": "item name", "price": 12.50, "quantity": 1}
  ],
  "subtotal": 50.00,
  "tax": 4.50,
  "tip": 10.00,
  "grand_total": 64.50
}

For currency, use ISO 4217 codes:
- $ or dollars → USD
- € or euros → EUR
- £ or pounds → GBP
- ₸ or тенге or tenge → KZT
- ₽ or рубли or rubles → RUB
- ¥ or yen → JPY
- ₹ or rupees → INR
If unclear, use USD as default."""

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
            data = json.loads(json_text)

            # Build ReceiptItem objects
            items = [
                ReceiptItem(
                    name=item["name"],
                    price=Decimal(str(item["price"])),
                    quantity=item.get("quantity", 1),
                )
                for item in data["items"]
            ]

            # Build ReceiptData object
            receipt_data = ReceiptData(
                items=items,
                currency=data.get("currency", "USD"),
                subtotal=Decimal(str(data["subtotal"])),
                tax=Decimal(str(data.get("tax", 0))),
                tip=Decimal(str(data.get("tip", 0))),
                grand_total=Decimal(str(data["grand_total"])),
            )

            logger.info(f"Extracted {len(items)} items from receipt in {receipt_data.currency}")
            return receipt_data
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse receipt data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to extract receipt items: {e}")

    async def split_bill(
        self, participant_description: str, receipt_data: ReceiptData, image_bytes: bytes
    ) -> BillSplit:
        """
        Split the bill among participants based on description and receipt data.

        Args:
            participant_description: User's description of who ate what
            receipt_data: Complete receipt data including items, currency, and totals
            image_bytes: Raw bytes of the receipt image (for reference)

        Returns:
            BillSplit object with complete split information
        """
        logger.info("Starting bill split with Claude")

        # Detect image media type and encode to base64
        media_type = detect_image_media_type(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Format receipt items for prompt
        items_text = "\n".join(
            [f"- {item.name}: {item.price} (x{item.quantity})" for item in receipt_data.items]
        )

        # Create structured prompt for bill splitting
        prompt = f"""You are helping split a restaurant bill among friends.

**What participants ordered (from user description):**
{participant_description}

**Receipt items extracted:**
{items_text}

**Receipt totals:**
Currency: {receipt_data.currency}
Subtotal: {receipt_data.subtotal}
Tax: {receipt_data.tax}
Tip: {receipt_data.tip}
Grand Total: {receipt_data.grand_total}

**Task:**
First, analyze the participant description to identify:
1. Each person's name
2. What items each person ordered (match items from the receipt using fuzzy matching)
3. Handle shared items by splitting them proportionally

Then, calculate the bill split:
1. Match each receipt item to one or more participants
2. Calculate each person's subtotal (sum of their item prices)
3. Distribute tax ({receipt_data.tax}) proportionally based on each person's subtotal percentage
4. Distribute tip ({receipt_data.tip}) proportionally based on each person's subtotal percentage
5. Calculate final total for each person

Output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{{
  "participants": [
    {{
      "name": "Person Name",
      "items": ["item1", "item2"],
      "subtotal": 25.50,
      "tax_share": 2.30,
      "tip_share": 5.10,
      "total": 32.90
    }}
  ]
}}

CRITICAL: The sum of all participant subtotals must equal {receipt_data.subtotal}, all tax shares must equal {receipt_data.tax}, and all tip shares must equal {receipt_data.tip}."""

        # Call Claude API with response prefilling
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3072,
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
        logger.debug(f"Claude split response: {full_response}")

        # Extract JSON from potential markdown wrapper
        json_text = extract_json_from_response(full_response)

        # Parse JSON response
        try:
            split_data = json.loads(json_text)

            # Build ParticipantShare objects
            participants = [
                ParticipantShare(
                    name=p["name"],
                    items=p["items"],
                    subtotal=Decimal(str(p["subtotal"])),
                    tax_share=Decimal(str(p["tax_share"])),
                    tip_share=Decimal(str(p["tip_share"])),
                    total=Decimal(str(p["total"])),
                )
                for p in split_data["participants"]
            ]

            # Build BillSplit object using receipt data
            bill_split = BillSplit(
                participants=participants,
                receipt_items=receipt_data.items,
                currency=receipt_data.currency,
                subtotal=receipt_data.subtotal,
                tax=receipt_data.tax,
                tip=receipt_data.tip,
                grand_total=receipt_data.grand_total,
            )

            logger.info(f"Successfully split bill among {len(participants)} participants")
            return bill_split

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse split data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to split bill: {e}")

    async def verify_and_refine_split(self, bill_split: BillSplit, receipt_data: ReceiptData) -> tuple[BillSplit, bool, str]:
        """
        Verify the bill split is mathematically correct and refine if needed.

        Args:
            bill_split: Initial bill split to verify
            receipt_data: Original receipt data for comparison

        Returns:
            Tuple of (refined_split, was_refined, explanation)
        """
        logger.info("Verifying bill split accuracy")

        # Calculate sums from participants
        participants_subtotal = sum(p.subtotal for p in bill_split.participants)
        participants_tax = sum(p.tax_share for p in bill_split.participants)
        participants_tip = sum(p.tip_share for p in bill_split.participants)
        participants_total = sum(p.total for p in bill_split.participants)

        # Check for discrepancies (allow 0.01 tolerance for rounding)
        tolerance = Decimal("0.01")
        subtotal_diff = abs(participants_subtotal - receipt_data.subtotal)
        tax_diff = abs(participants_tax - receipt_data.tax)
        tip_diff = abs(participants_tip - receipt_data.tip)
        total_diff = abs(participants_total - receipt_data.grand_total)

        # If all checks pass, return original split
        if (subtotal_diff <= tolerance and tax_diff <= tolerance and
            tip_diff <= tolerance and total_diff <= tolerance):
            logger.info("Bill split verification passed")
            return (bill_split, False, "Split verified - all totals match")

        # Build verification prompt
        logger.warning(f"Split discrepancies detected - Subtotal: {subtotal_diff}, Tax: {tax_diff}, Tip: {tip_diff}, Total: {total_diff}")

        # Format participant data for prompt
        participants_text = "\n".join([
            f"- {p.name}: subtotal={p.subtotal}, tax={p.tax_share}, tip={p.tip_share}, total={p.total}"
            for p in bill_split.participants
        ])

        prompt = f"""You are verifying a restaurant bill split for mathematical accuracy.

**Receipt Totals (CORRECT VALUES):**
Currency: {receipt_data.currency}
Subtotal: {receipt_data.subtotal}
Tax: {receipt_data.tax}
Tip: {receipt_data.tip}
Grand Total: {receipt_data.grand_total}

**Current Split (MAY HAVE ERRORS):**
{participants_text}

**Calculated Sums from Participants:**
Sum of subtotals: {participants_subtotal} (should be {receipt_data.subtotal})
Sum of tax shares: {participants_tax} (should be {receipt_data.tax})
Sum of tip shares: {participants_tip} (should be {receipt_data.tip})
Sum of totals: {participants_total} (should be {receipt_data.grand_total})

**Task:**
First, identify any discrepancies between the participant sums and the receipt totals.

Then, refine the split to ensure:
1. Sum of all participant subtotals EXACTLY equals {receipt_data.subtotal}
2. Sum of all participant tax shares EXACTLY equals {receipt_data.tax}
3. Sum of all participant tip shares EXACTLY equals {receipt_data.tip}
4. Sum of all participant totals EXACTLY equals {receipt_data.grand_total}

Adjust values proportionally to fix any rounding errors. Keep item assignments the same.

Output ONLY a valid JSON object with this structure (no markdown, no explanations):
{{
  "participants": [
    {{
      "name": "Person Name",
      "items": ["item1", "item2"],
      "subtotal": 25.50,
      "tax_share": 2.30,
      "tip_share": 5.10,
      "total": 32.90
    }}
  ],
  "explanation": "Brief explanation of what was adjusted"
}}"""

        # Call Claude API for verification
        message = self.client.messages.create(
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
        logger.debug(f"Claude verification response: {full_response}")

        json_text = extract_json_from_response(full_response)

        try:
            refined_data = json.loads(json_text)

            # Build refined ParticipantShare objects
            refined_participants = [
                ParticipantShare(
                    name=p["name"],
                    items=p["items"],
                    subtotal=Decimal(str(p["subtotal"])),
                    tax_share=Decimal(str(p["tax_share"])),
                    tip_share=Decimal(str(p["tip_share"])),
                    total=Decimal(str(p["total"])),
                )
                for p in refined_data["participants"]
            ]

            # Build refined BillSplit
            refined_split = BillSplit(
                participants=refined_participants,
                receipt_items=receipt_data.items,
                currency=receipt_data.currency,
                subtotal=receipt_data.subtotal,
                tax=receipt_data.tax,
                tip=receipt_data.tip,
                grand_total=receipt_data.grand_total,
            )

            explanation = refined_data.get("explanation", "Split refined for accuracy")
            logger.info(f"Split refined: {explanation}")

            return (refined_split, True, explanation)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse refined split: {e}")
            # Return original split if refinement fails
            return (bill_split, False, f"Verification failed: {e}")
