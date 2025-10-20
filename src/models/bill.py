"""Data models for receipt processing."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    items: list[ReceiptItem] = Field(description="All items from the receipt")
    total: Decimal = Field(description="Grand total of the receipt")


class ParticipantShare(BaseModel):
    """Represents a participant's share of the bill."""

    name: str = Field(description="Participant's name")
    items: list[str] = Field(
        default_factory=list, description="List of items assigned to this participant"
    )
    amount: Decimal = Field(description="Total amount this participant owes")


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
                lines.append(
                    f"• {item.description}: ${item.unit_price:.2f} x{item.quantity} = ${item.line_total:.2f}"
                )
            else:
                lines.append(f"• {item.description}: ${item.line_total:.2f}")

        lines.append("")
        lines.append(f"💵 **Total: ${self.receipt.total:.2f}**")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Participant shares
        lines.append("**Individual Shares:**")
        for participant in self.participants:
            lines.append(f"\n**{participant.name}:**")
            if participant.items:
                lines.append(f"Items: {', '.join(participant.items)}")
            lines.append(f"**Amount: ${participant.amount:.2f}**")

        return "\n".join(lines)
