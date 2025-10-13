"""Data models for bill splitting and receipt processing."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from src.utils.markdown import escape_markdown

# Currency symbol mapping for common currencies
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "KZT": "₸",
    "RUB": "₽",
    "JPY": "¥",
    "CNY": "¥",
    "INR": "₹",
    "KRW": "₩",
    "TRY": "₺",
    "BRL": "R$",
    "MXN": "$",
    "CAD": "C$",
    "AUD": "A$",
}


def get_currency_symbol(currency_code: str) -> str:
    """
    Get the currency symbol for a given ISO currency code.

    Args:
        currency_code: ISO 4217 currency code (e.g., "USD", "KZT")

    Returns:
        Currency symbol string, or the code itself if not found
    """
    return CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code)


class ReceiptItem(BaseModel):
    """Represents a single item from a receipt."""

    name: str = Field(description="Name of the item")
    price: Decimal = Field(description="Price of the item")
    quantity: int = Field(default=1, description="Quantity of the item")

    @property
    def total_price(self) -> Decimal:
        """Calculate total price for this item (price * quantity)."""
        return self.price * self.quantity


class ReceiptData(BaseModel):
    """Complete receipt data extracted from OCR."""

    items: list[ReceiptItem] = Field(description="All items from the receipt")
    currency: str = Field(description="ISO 4217 currency code (e.g., USD, KZT, EUR)")
    subtotal: Decimal | None = Field(
        default=None,
        description="Sum of all item prices (auto-computed if not provided)",
    )
    total: Decimal = Field(description="Total amount from receipt")

    @model_validator(mode="after")
    def compute_subtotal_if_missing(self) -> "ReceiptData":
        """Auto-compute subtotal from items if not provided."""
        if self.subtotal is None:
            # Compute from items
            computed = sum((item.total_price for item in self.items), Decimal("0"))
            self.subtotal = computed
        return self

    def format_summary(self) -> str:
        """Format receipt data as human-readable summary."""
        symbol = get_currency_symbol(self.currency)
        lines = ["📄 **Receipt Extracted:**\n"]

        # Items (escape item names to prevent Markdown parsing errors)
        for item in self.items:
            lines.append(
                f"• {escape_markdown(item.name)}: {symbol}{item.price:,.2f} (x{item.quantity})"
            )

        lines.append("")

        # Totals
        lines.append(f"Currency: {self.currency}")
        lines.append(f"Subtotal: {symbol}{self.subtotal:,.2f}")
        lines.append(f"**Total: {symbol}{self.total:,.2f}**")

        return "\n".join(lines)


class ParticipantItem(BaseModel):
    """Represents a single item assigned to a participant with fractional ownership."""

    item_name: str = Field(description="Name of the item from the receipt")
    item_numerator: int = Field(description="How many parts this person gets (e.g., 1)")
    item_denominator: int = Field(
        description="Total parts the item is split into (e.g., 2 if shared by 2 people)"
    )

    @field_validator("item_denominator")
    @classmethod
    def validate_denominator(cls, v: int) -> int:
        """Validate that denominator is positive."""
        if v <= 0:
            raise ValueError(f"item_denominator must be positive, got {v}")
        return v

    @field_validator("item_numerator")
    @classmethod
    def validate_numerator(cls, v: int) -> int:
        """Validate that numerator is non-negative."""
        if v < 0:
            raise ValueError(f"item_numerator must be non-negative, got {v}")
        return v

    @property
    def fraction(self) -> Decimal:
        """Calculate the fractional ownership (numerator/denominator)."""
        if self.item_denominator == 0:
            raise ValueError(f"Item denominator cannot be zero for {self.item_name}")
        return Decimal(self.item_numerator) / Decimal(self.item_denominator)

    def format_fraction(self) -> str:
        """Format the fraction for display (e.g., '1/2', '1/3', or '' for whole)."""
        if self.item_numerator == self.item_denominator:
            return ""  # Don't show fraction if person has the whole item
        return f" ({self.item_numerator}/{self.item_denominator})"


def find_receipt_item(
    item_name: str, receipt_items: list[ReceiptItem], threshold: int = 80
) -> ReceiptItem | None:
    """
    Find a receipt item by name using fuzzy string matching.

    Args:
        item_name: Name of the item to find (from participant assignment)
        receipt_items: Complete list of items from the receipt
        threshold: Minimum fuzzy match score (0-100, default 80)

    Returns:
        Matching ReceiptItem or None if no good match found
    """
    from thefuzz import fuzz

    if not receipt_items:
        return None

    best_match = None
    best_score = 0

    for receipt_item in receipt_items:
        # Try multiple fuzzy matching strategies
        ratio_score = fuzz.ratio(item_name.lower(), receipt_item.name.lower())
        partial_score = fuzz.partial_ratio(item_name.lower(), receipt_item.name.lower())
        token_sort_score = fuzz.token_sort_ratio(
            item_name.lower(), receipt_item.name.lower()
        )

        # Use the highest score from all strategies
        score = max(ratio_score, partial_score, token_sort_score)

        if score > best_score:
            best_score = score
            best_match = receipt_item

    # Return match only if it meets threshold
    if best_score >= threshold:
        return best_match

    return None


class ParticipantShare(BaseModel):
    """Represents a participant's share of the bill."""

    name: str = Field(description="Participant's name")
    items: list[ParticipantItem] = Field(
        default_factory=list,
        description="List of items with fractional ownership assigned to this participant",
    )

    def calculate_total(self, receipt_items: list[ReceiptItem]) -> Decimal:
        """
        Calculate the total amount this participant owes based on receipt items.

        Args:
            receipt_items: Complete list of items from the receipt

        Returns:
            Total amount (sum of fractional item prices)

        Raises:
            ValueError: If an item cannot be matched to the receipt
        """
        total = Decimal("0")

        for participant_item in self.items:
            # Find matching receipt item using fuzzy matching
            matched_item = find_receipt_item(participant_item.item_name, receipt_items)

            if not matched_item:
                raise ValueError(
                    f"Could not match item '{participant_item.item_name}' "
                    f"for participant '{self.name}' to any receipt item"
                )

            # Calculate fractional price: (price * quantity) * (numerator/denominator)
            item_total = matched_item.total_price * participant_item.fraction
            total += item_total

        return total.quantize(Decimal("0.01"))  # Round to 2 decimal places


class BillSplit(BaseModel):
    """Complete bill split result with all participants."""

    participants: list[ParticipantShare] = Field(
        description="List of all participants and their shares"
    )
    receipt_items: list[ReceiptItem] = Field(description="All items from the receipt")
    currency: str = Field(description="ISO 4217 currency code (e.g., USD, KZT, EUR)")
    total: Decimal = Field(description="Total of the bill")

    def format_summary(self, title: str = "Bill Split Summary") -> str:
        """Format the bill split as a human-readable summary."""
        symbol = get_currency_symbol(self.currency)
        lines = [f"🧾 **{title}**\n"]

        # Receipt items (escape names to prevent Markdown parsing errors)
        lines.append("**Receipt Items:**")
        for item in self.receipt_items:
            lines.append(
                f"• {escape_markdown(item.name)}: {symbol}{item.price:,.2f} (x{item.quantity})"
            )

        lines.append("")

        # Totals
        lines.append(f"**Total: {symbol}{self.total:,.2f}**")

        lines.append("")
        lines.append("---")
        lines.append("")

        # Participant shares with calculated totals (escape names to prevent Markdown errors)
        lines.append("**Individual Shares:**")
        for participant in self.participants:
            lines.append(f"\n**{escape_markdown(participant.name)}:**")
            if participant.items:
                # Show items with detailed price breakdown
                for participant_item in participant.items:
                    # Find matching receipt item
                    matched_item = find_receipt_item(
                        participant_item.item_name, self.receipt_items
                    )

                    if matched_item:
                        # Format fraction for display
                        if (
                            participant_item.item_numerator
                            == participant_item.item_denominator
                        ):
                            fraction_display = "1"
                        else:
                            fraction_display = f"{participant_item.item_numerator}/{participant_item.item_denominator}"

                        # Calculate this item's cost for participant
                        item_cost = matched_item.total_price * participant_item.fraction

                        # Display with full breakdown like receipt items (escape item name)
                        lines.append(
                            f"• {escape_markdown(matched_item.name)}: {symbol}{matched_item.price:,.2f} "
                            f"(x{matched_item.quantity}) × {fraction_display} = {symbol}{item_cost:,.2f}"
                        )
                    else:
                        # Fallback if item not found (escape item name)
                        lines.append(
                            f"• {escape_markdown(participant_item.item_name)} (not found in receipt)"
                        )

            # Calculate and display total
            try:
                participant_total = participant.calculate_total(self.receipt_items)
                lines.append(f"**Total: {symbol}{participant_total:,.2f}**")
            except ValueError as e:
                lines.append(f"**Total: Error calculating ({e})**")

        return "\n".join(lines)
