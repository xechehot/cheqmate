"""Anthropic API service for receipt OCR."""

import base64
import json
import logging
import re
from decimal import Decimal

from anthropic import Anthropic

from src.config import settings
from src.models.bill import Receipt, ReceiptItem

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
        prompt = """Analyze this receipt image and extract restaurant info, items, and total.

First, carefully examine the receipt to identify:
1. Restaurant name (usually at the top of the receipt)
2. Restaurant address (if visible on the receipt)
3. All individual items/dishes with their descriptions
4. Quantities (if specified, otherwise default to 1)
5. Line total for each item (the total amount charged for that line - this is ALWAYS shown on receipts)
6. Unit price for each item (if shown separately on the receipt - this is OPTIONAL)
7. Grand total (the final total amount)

IMPORTANT:
- "line_total" is the total price for that line item (quantity × unit_price) - ALWAYS present on receipt
- "unit_price" is optional - only include it if explicitly shown on the receipt
- If unit_price is not shown, omit it (it will be calculated automatically)
- restaurant_name and restaurant_address can be null if not visible on the receipt

Then output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{
  "restaurant_name": "Restaurant Name",
  "restaurant_address": "123 Main St, City, State",
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
                    unit_price=Decimal(str(item["unit_price"])) if "unit_price" in item and item["unit_price"] is not None else None,
                )
                for item in receipt_data["items"]
            ]

            # Create Receipt object
            receipt = Receipt(
                restaurant_name=receipt_data.get("restaurant_name"),
                restaurant_address=receipt_data.get("restaurant_address"),
                items=items,
                total=Decimal(str(receipt_data["total"])),
            )

            logger.info(f"Extracted receipt from {receipt.restaurant_name or 'Unknown'} with {len(items)} items, total: ${receipt.total:.2f}")
            return receipt
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse receipt data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to extract receipt items: {e}")
