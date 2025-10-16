"""Anthropic API service for receipt OCR and bill splitting."""

import base64
import json
import logging
import re
from decimal import Decimal

from anthropic import Anthropic

from src.config import settings
from src.models.bill import BillSplit, ParticipantShare, ReceiptItem

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

    async def extract_receipt_items(self, image_bytes: bytes) -> list[ReceiptItem]:
        """
        Extract items, prices, and totals from a receipt image using Claude Vision.

        Args:
            image_bytes: Raw bytes of the receipt image

        Returns:
            List of ReceiptItem objects extracted from the receipt
        """
        logger.info("Starting receipt OCR with Claude Vision")

        # Detect image media type and encode to base64
        media_type = detect_image_media_type(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Create structured prompt for receipt extraction with clear output format
        prompt = """Analyze this receipt image and extract all items with their prices.

First, carefully examine the receipt to identify:
1. All individual items/dishes with their descriptions
2. Quantities (if specified, otherwise default to 1)
3. Line total for each item (the total amount charged for that line - this is ALWAYS shown on receipts)
4. Unit price for each item (if shown separately on the receipt - this is OPTIONAL)
5. Subtotal (sum of all line totals)
6. Tax amount
7. Tip/gratuity (if present, otherwise 0)
8. Grand total

IMPORTANT:
- "line_total" is the total price for that line item (quantity × unit_price) - ALWAYS present on receipt
- "unit_price" is optional - only include it if explicitly shown on the receipt
- If unit_price is not shown, omit it (it will be calculated automatically)

Then output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{
  "items": [
    {"description": "item description", "line_total": 25.00, "quantity": 2, "unit_price": 12.50}
  ],
  "subtotal": 50.00,
  "tax": 4.50,
  "tip": 10.00,
  "total": 64.50
}

Note: unit_price is optional in the items array."""

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
            items = [
                ReceiptItem(
                    description=item["description"],
                    line_total=Decimal(str(item["line_total"])),
                    quantity=item.get("quantity", 1),
                    unit_price=Decimal(str(item["unit_price"])) if "unit_price" in item and item["unit_price"] is not None else None,
                )
                for item in receipt_data["items"]
            ]
            logger.info(f"Extracted {len(items)} items from receipt")
            return items
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse receipt data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to extract receipt items: {e}")

    async def split_bill(
        self, participant_description: str, receipt_items: list[ReceiptItem], image_bytes: bytes
    ) -> BillSplit:
        """
        Split the bill among participants based on description and receipt items.

        Args:
            participant_description: User's description of who ate what
            receipt_items: List of items extracted from receipt
            image_bytes: Raw bytes of the receipt image (for reference)

        Returns:
            BillSplit object with complete split information
        """
        logger.info("Starting bill split with Claude")

        # Detect image media type and encode to base64
        media_type = detect_image_media_type(image_bytes)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Format receipt items for prompt
        items_text = "\n".join([
            f"- {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}"
            if item.quantity > 1
            else f"- {item.description}: ${item.line_total:.2f}"
            for item in receipt_items
        ])

        # Calculate totals from receipt items for context
        subtotal = sum(item.line_total for item in receipt_items)

        # Create structured prompt for bill splitting
        prompt = f"""You are helping split a restaurant bill among friends.

**What participants ordered (from user description):**
{participant_description}

**Receipt items extracted:**
{items_text}

**Task:**
First, analyze the participant description to identify:
1. Each person's name
2. What items each person ordered (match items from the receipt using fuzzy matching)
3. Handle shared items by splitting them proportionally

Then, calculate the bill split:
1. Match each receipt item to one or more participants
2. Calculate each person's subtotal (sum of their item prices)
3. Calculate total subtotal, tax, and tip from the receipt image
4. Distribute tax and tip proportionally based on each person's subtotal percentage
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
  ],
  "subtotal": {subtotal},
  "tax": 4.50,
  "tip": 10.00,
  "grand_total": 64.50
}}

Important: All amounts must sum correctly. Each person's tax/tip share should be proportional to their subtotal."""

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

            # Build BillSplit object
            bill_split = BillSplit(
                participants=participants,
                receipt_items=receipt_items,
                subtotal=Decimal(str(split_data["subtotal"])),
                tax=Decimal(str(split_data["tax"])),
                tip=Decimal(str(split_data["tip"])),
                grand_total=Decimal(str(split_data["grand_total"])),
            )

            logger.info(f"Successfully split bill among {len(participants)} participants")
            return bill_split

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse split data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to split bill: {e}")
