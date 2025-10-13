"""Anthropic API service for receipt OCR and bill splitting."""

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
    ReceiptData,
    ReceiptItem,
)

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

    def _log_api_error(self, operation: str, error: Exception, context_size_kb: float = 0) -> None:
        """
        Log API errors with diagnostic information for debugging.

        Args:
            operation: Name of the operation (e.g., "OCR", "split_bill")
            error: The exception that occurred
            context_size_kb: Size of request context in KB
        """
        error_type = type(error).__name__
        error_msg = str(error)

        # Try to extract status code from Anthropic errors
        status_code = None
        try:
            from anthropic import APIError
            if isinstance(error, APIError) and hasattr(error, 'status_code'):
                status_code = error.status_code
        except ImportError:
            pass

        # Classify error type
        if status_code:
            if status_code == 400:
                error_class = "BAD_REQUEST"
                hint = "Check image format/size or request structure"
            elif status_code == 429:
                error_class = "RATE_LIMIT"
                hint = "Too many requests - will retry with backoff"
            elif status_code in [500, 502, 503, 504]:
                error_class = "SERVER_ERROR"
                hint = "Anthropic API issue - will retry"
            else:
                error_class = "API_ERROR"
                hint = "Unknown API error"
        elif "timeout" in error_msg.lower():
            error_class = "TIMEOUT"
            hint = "Request took too long - will retry"
        elif "connection" in error_msg.lower():
            error_class = "CONNECTION"
            hint = "Network issue - will retry"
        else:
            error_class = "UNKNOWN"
            hint = "Unexpected error"

        logger.error(
            f"{operation} API call failed: {error_class} ({error_type}) - {hint}. "
            f"Context size: {context_size_kb:.1f}KB. Error: {error_msg[:200]}"
        )

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

        # Diagnostic logging
        image_size_kb = len(image_bytes) / 1024
        estimated_request_kb = len(image_base64) / 1024 + 1  # base64 + prompt
        logger.info(
            f"OCR request: image_size={image_size_kb:.1f}KB, "
            f"media_type={media_type}, estimated_request_size={estimated_request_kb:.1f}KB"
        )

        # Create structured prompt for receipt extraction with currency detection
        prompt = """Analyze this receipt image and extract all items with their prices and currency.

First, carefully examine the receipt to identify:
1. The currency used (look for currency symbols like $, €, £, ₸, ₽, etc. or ISO codes)
2. All individual items/dishes with their UNIT prices (price PER SINGLE ITEM, not line total)
3. Quantities (if specified, otherwise default to 1)
4. Subtotal (sum of all items)
5. Total amount

IMPORTANT: For the "price" field, extract the UNIT price (price per single item).
- If receipt shows "Pizza x2 = 25.00", extract: price=12.50 (calculated as 25.00÷2), quantity=2
- If receipt shows "Salad = 8.00", extract: price=8.00, quantity=1
- The "price" field should ALWAYS be the price for ONE unit of the item

Then output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
{
  "currency": "USD",
  "items": [
    {"name": "Pizza", "price": 12.50, "quantity": 2},
    {"name": "Salad", "price": 8.00, "quantity": 1}
  ],
  "subtotal": 33.00,
  "total": 33.00
}

Note: In the example above:
- Pizza: unit price 12.50, quantity 2, line total = 12.50 × 2 = 25.00
- Salad: unit price 8.00, quantity 1, line total = 8.00 × 1 = 8.00
- Subtotal: 25.00 + 8.00 = 33.00

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
        try:
            import time
            start_time = time.time()

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

            api_duration = time.time() - start_time
            logger.info(f"OCR API call completed in {api_duration:.2f}s")

        except Exception as e:
            self._log_api_error("OCR", e, image_size_kb)
            raise

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
                total=Decimal(str(data["total"])),
            )

            logger.info(
                f"Extracted {len(items)} items from receipt in {receipt_data.currency}"
            )
            return receipt_data
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse receipt data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to extract receipt items: {e}")

    async def split_bill(
        self,
        participant_description: str,
        receipt_data: ReceiptData,
    ) -> BillSplit:
        """
        Split the bill among participants based on description and receipt data.

        This is a TEXT-ONLY operation - no image processing. The receipt_data already
        contains all necessary information extracted from OCR.

        Args:
            participant_description: User's description of who ate what
            receipt_data: Complete receipt data including items, currency, and totals

        Returns:
            BillSplit object with complete split information
        """
        logger.info("Starting bill split with Claude (text-only mode)")

        # Format receipt items for prompt
        items_text = "\n".join(
            [
                f"- {item.name}: {item.price} (x{item.quantity})"
                for item in receipt_data.items
            ]
        )

        # Diagnostic logging
        desc_length = len(participant_description)
        items_count = len(receipt_data.items)
        logger.info(
            f"Split request: description_length={desc_length} chars, "
            f"items_count={items_count}, currency={receipt_data.currency}"
        )

        # Create structured prompt for bill splitting
        prompt = f"""You are helping split a restaurant bill among friends.

**What participants ordered (from user description):**
{participant_description}

**Receipt items extracted:**
{items_text}

**Receipt totals:**
Currency: {receipt_data.currency}
Total: {receipt_data.total}

**Task:**
First, analyze the participant description to identify:
1. Each person's name
2. What items each person ordered (match items from the receipt)
3. Handle shared items by indicating fractional ownership

For each person, assign items with fractional ownership using numerator/denominator:
- If a person ate the whole item: item_numerator=1, item_denominator=1
- If 2 people shared equally: item_numerator=1, item_denominator=2 (for each person)
- If 3 people shared equally: item_numerator=1, item_denominator=3 (for each person)
- If someone ate 2/3 of an item: item_numerator=2, item_denominator=3

DO NOT calculate totals or do any math. Only assign items with fractions.
The system will calculate totals automatically based on receipt prices.

Output ONLY a valid JSON object with this exact structure (no markdown, no explanations):
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
  ]
}}

Important:
- Match item names closely to receipt items
- For shared items, ensure denominators add up correctly (e.g., if 2 people share, both get 1/2)
- Use only the item names, numerators, and denominators - no totals"""

        # Call Claude API with response prefilling (text-only, no image)
        try:
            import time
            start_time = time.time()

            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=3072,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,  # Text-only content
                    },
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "{"}],
                    },
                ],
            )

            api_duration = time.time() - start_time
            logger.info(f"Split API call completed in {api_duration:.2f}s")

        except Exception as e:
            # Calculate approximate request size for diagnostics
            prompt_size_kb = len(prompt) / 1024
            self._log_api_error("split_bill", e, prompt_size_kb)
            raise

        # Extract text response
        response_text = message.content[0].text if message.content else ""
        # Prepend the prefilled "{" back to make valid JSON
        full_response = "{" + response_text
        logger.info(f"Claude split response: {full_response}")

        # Extract JSON from potential markdown wrapper
        json_text = extract_json_from_response(full_response)

        # Parse JSON response
        try:
            split_data = json.loads(json_text)

            # Build ParticipantShare objects with items
            participants = []
            for p in split_data["participants"]:
                # Build ParticipantItem objects
                participant_items = [
                    ParticipantItem(
                        item_name=item["item_name"],
                        item_numerator=item["item_numerator"],
                        item_denominator=item["item_denominator"],
                    )
                    for item in p["items"]
                ]

                participants.append(
                    ParticipantShare(
                        name=p["name"],
                        items=participant_items,
                    )
                )

            # Build BillSplit object using receipt data
            bill_split = BillSplit(
                participants=participants,
                receipt_items=receipt_data.items,
                currency=receipt_data.currency,
                total=receipt_data.total,
            )

            logger.info(
                f"Successfully split bill among {len(participants)} participants"
            )
            return bill_split

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse split data: {e}")
            logger.error(f"Raw response: {full_response}")
            raise ValueError(f"Failed to split bill: {e}")

    async def verify_and_refine_split(
        self, bill_split: BillSplit, receipt_data: ReceiptData
    ) -> tuple[BillSplit, bool, str]:
        """
        Verify the bill split is mathematically correct and refine if needed.

        Args:
            bill_split: Initial bill split to verify
            receipt_data: Original receipt data for comparison

        Returns:
            Tuple of (refined_split, was_refined, explanation)
        """
        logger.info("Verifying bill split accuracy")

        # Calculate totals for each participant in Python
        participant_totals: dict[str, Decimal] = {}
        calculation_errors: list[str] = []

        for participant in bill_split.participants:
            try:
                calculated_total = participant.calculate_total(receipt_data.items)
                participant_totals[participant.name] = calculated_total
            except ValueError as e:
                calculation_errors.append(f"{participant.name}: {e}")
                logger.error(f"Calculation error for {participant.name}: {e}")

        # If there were matching errors, fail early
        if calculation_errors:
            error_msg = "Item matching errors:\n" + "\n".join(calculation_errors)
            logger.error(error_msg)
            return (bill_split, False, error_msg)

        # Calculate sum of all participant totals
        participants_total = sum(participant_totals.values())

        # Check for discrepancies (allow 0.02 tolerance for rounding)
        tolerance = Decimal("0.02")
        total_diff = abs(participants_total - receipt_data.total)

        # If all checks pass, return original split
        if total_diff <= tolerance:
            logger.info("Bill split verification passed")
            return (bill_split, False, "Split verified - all totals match")

        # Build verification prompt with calculated values
        logger.warning(f"Split discrepancy detected - Total diff: {total_diff}")

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

        prompt = f"""You are verifying a restaurant bill split for mathematical accuracy.

**Receipt Items (GROUND TRUTH):**
{receipt_items_text}

**Receipt Total (TARGET VALUE):**
Currency: {receipt_data.currency}
Total: {receipt_data.total}

**Current Split (Python-calculated totals):**
{participants_formatted}

**Sum of participant totals: {participants_total}**
**Difference from receipt total: {total_diff}**

**Task:**
The sum of participant totals does not match the receipt total.

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
        logger.info(f"Claude verification response: {full_response}")

        json_text = extract_json_from_response(full_response)

        try:
            refined_data = json.loads(json_text)

            # Build refined ParticipantShare objects
            refined_participants = []
            for p in refined_data["participants"]:
                # Build ParticipantItem objects
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

            # Recalculate totals after refinement to verify it worked
            refined_totals: dict[str, Decimal] = {}
            for participant in refined_split.participants:
                try:
                    refined_totals[participant.name] = participant.calculate_total(
                        receipt_data.items
                    )
                except ValueError as e:
                    logger.error(
                        f"Refinement failed - item matching error for {participant.name}: {e}"
                    )
                    return (bill_split, False, f"Refinement failed: {e}")

            refined_total_sum = sum(refined_totals.values())
            refined_diff = abs(refined_total_sum - receipt_data.total)

            # Log the refinement results
            logger.info(
                f"Refined total sum: {refined_total_sum}, Receipt total: {receipt_data.total}, Diff: {refined_diff}"
            )

            explanation = refined_data.get("explanation", "Split refined for accuracy")
            if refined_diff > tolerance:
                explanation += f" (Note: Refinement reduced error from {total_diff} to {refined_diff})"
                logger.warning(
                    f"Refinement did not fully resolve discrepancy. Remaining diff: {refined_diff}"
                )
            else:
                logger.info("Refinement successful - totals now match within tolerance")

            return (refined_split, True, explanation)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse refined split: {e}")
            # Return original split if refinement fails
            return (bill_split, False, f"Verification failed: {e}")
