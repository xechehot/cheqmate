"""Data models for receipt processing."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ReceiptItem(BaseModel):
    """Represents a single item from a receipt."""

    description: str = Field(description="Description/name of the item")
    quantity: int = Field(default=1, description="Quantity of the item")
    line_total: Decimal = Field(description="Total price for this line item (quantity × unit price)")
    unit_price: Decimal = Field(description="Price per unit (calculated from line_total/quantity if not provided)")

    @model_validator(mode='before')
    @classmethod
    def calculate_unit_price(cls, data: Any) -> Any:
        """Calculate unit_price from line_total if not provided."""
        if isinstance(data, dict):
            # Only calculate if unit_price is not provided
            if 'unit_price' not in data or data['unit_price'] is None:
                quantity = data.get('quantity', 1)
                line_total = data.get('line_total')
                if line_total is not None and quantity > 0:
                    data['unit_price'] = Decimal(str(line_total)) / quantity
                else:
                    data['unit_price'] = Decimal('0')
        return data


class Receipt(BaseModel):
    """Represents a complete receipt with restaurant info and items."""

    restaurant_name: str | None = Field(default=None, description="Name of the restaurant/establishment")
    restaurant_address: str | None = Field(default=None, description="Address of the restaurant")
    items: list[ReceiptItem] = Field(description="All items from the receipt")
    total: Decimal = Field(description="Grand total of the receipt")
