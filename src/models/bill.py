"""Data models for receipt processing."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator


def format_currency(amount: Decimal, currency: str) -> str:
    """
    Format a decimal amount with the appropriate currency symbol or code.

    Args:
        amount: The amount to format
        currency: Currency code (e.g., "USD", "EUR", "KZT")

    Returns:
        Formatted string with currency symbol (e.g., "$10.50", "€10.50", "10.50 KZT")
    """
    # Map common currency codes to symbols
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "CNY": "¥",
        "KZT": "₸",
        "RUB": "₽",
    }

    symbol = currency_symbols.get(currency.upper(), "")

    if symbol:
        # Symbol before amount for most currencies
        if currency.upper() in ["EUR", "RUB", "KZT"]:
            return f"{amount:.2f} {symbol}"
        else:
            return f"{symbol}{amount:.2f}"
    else:
        # Use currency code if no symbol available
        return f"{amount:.2f} {currency}"


class ReceiptItem(BaseModel):
    """Represents a single item from a receipt."""

    description: str = Field(description="Description/name of the item")
    quantity: int = Field(default=1, description="Quantity of the item")
    line_total: Decimal = Field(
        description="Total price for this line item (quantity × unit price)"
    )
    unit_price: Decimal = Field(
        description="Price per unit (calculated from line_total/quantity if not provided)"
    )

    @model_validator(mode="before")
    @classmethod
    def calculate_unit_price(cls, data: Any) -> Any:
        """Calculate unit_price from line_total if not provided."""
        if isinstance(data, dict):
            # Only calculate if unit_price is not provided
            if "unit_price" not in data or data["unit_price"] is None:
                quantity = data.get("quantity", 1)
                line_total = data.get("line_total")
                if line_total is not None and quantity > 0:
                    data["unit_price"] = Decimal(str(line_total)) / quantity
                else:
                    data["unit_price"] = Decimal("0")
        return data


class Receipt(BaseModel):
    """Represents a complete receipt with restaurant info and items."""

    restaurant_name: str | None = Field(
        default=None, description="Name of the restaurant/establishment"
    )
    restaurant_address: str | None = Field(
        default=None, description="Address of the restaurant"
    )
    currency: str = Field(
        default="USD", description="Currency code (e.g., USD, EUR, KZT)"
    )
    items: list[ReceiptItem] = Field(description="All items from the receipt")
    total: Decimal = Field(description="Grand total of the receipt")


class ParticipantItem(BaseModel):
    """Represents a single item in a participant's share with fractional quantity."""

    item_name: str = Field(description="Name of the item from the receipt")
    line_nominator: int = Field(
        description="Number of shares this participant has (numerator)",
        gt=0,
    )
    line_denominator: int = Field(
        description="Total number of shares for this item (denominator)",
        gt=0,
    )


class ParticipantShare(BaseModel):
    """Represents a participant's share of the bill."""

    name: str = Field(description="Participant's name")
    items: list[ParticipantItem] = Field(
        default_factory=list,
        description="List of items with fractional quantities assigned to this participant",
    )
    amount: Decimal = Field(
        description="Total amount this participant owes (calculated from items)"
    )


class BillSplit(BaseModel):
    """Complete bill split result with all participants."""

    participants: list[ParticipantShare] = Field(
        description="List of all participants and their shares"
    )
    receipt: Receipt = Field(description="Original receipt data")

    def format_summary(self) -> str:
        """Format the bill split as a human-readable summary."""
        lines = ["🧾 **Bill Split Summary**\n"]

        # Restaurant info
        if self.receipt.restaurant_name:
            lines.append(f"🏪 **{self.receipt.restaurant_name}**")
        if self.receipt.restaurant_address:
            lines.append(f"📍 {self.receipt.restaurant_address}")

        if self.receipt.restaurant_name or self.receipt.restaurant_address:
            lines.append("")  # Empty line for spacing

        # Receipt items
        lines.append("📋 **Receipt Items:**")
        for item in self.receipt.items:
            if item.quantity > 1:
                unit_price_fmt = format_currency(item.unit_price, self.receipt.currency)
                line_total_fmt = format_currency(item.line_total, self.receipt.currency)
                lines.append(
                    f"• {item.description}: {unit_price_fmt} x{item.quantity} = {line_total_fmt}"
                )
            else:
                line_total_fmt = format_currency(item.line_total, self.receipt.currency)
                lines.append(f"• {item.description}: {line_total_fmt}")

        lines.append("")
        total_fmt = format_currency(self.receipt.total, self.receipt.currency)
        lines.append(f"💵 **Total: {total_fmt}**")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Participant shares
        lines.append("**Individual Shares:**")
        for participant in self.participants:
            lines.append(f"\n**{participant.name}:**")
            if participant.items:
                # Format items with fractions
                item_strings = []
                for item in participant.items:
                    if item.line_nominator == item.line_denominator:
                        # Full item (1/1)
                        item_strings.append(f"{item.item_name} (full)")
                    else:
                        # Fractional item
                        item_strings.append(
                            f"{item.item_name} ({item.line_nominator}/{item.line_denominator})"
                        )
                lines.append(f"Items: {', '.join(item_strings)}")
            amount_fmt = format_currency(participant.amount, self.receipt.currency)
            lines.append(f"**Amount: {amount_fmt}**")

        return "\n".join(lines)
