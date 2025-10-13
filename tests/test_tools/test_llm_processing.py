"""Unit tests for LLM processing tools.

These tests cover the 3 LLM-powered tools WITH MOCKED Anthropic API (NO direct LLM calls):
- extract_receipt_ocr
- create_initial_bill_split
- refine_split_with_llm
"""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from src.models.bill import BillSplit, ParticipantItem, ParticipantShare, ReceiptItem
from src.tools.llm_processing import (
    create_initial_bill_split,
    extract_receipt_ocr,
    refine_split_with_llm,
)


class TestExtractReceiptOCR:
    """Tests for extract_receipt_ocr with mocked Anthropic API."""

    @pytest.mark.asyncio
    @patch("src.tools.llm_processing.AnthropicService")
    async def test_extract_receipt_success(self, mock_service_class, mock_ocr_response):
        """Test successful receipt OCR extraction."""
        # Mock the service instance and its method
        from unittest.mock import AsyncMock

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        # Create expected ReceiptData from mock response
        from src.models.bill import ReceiptData

        expected_receipt_data = ReceiptData(
            items=[
                ReceiptItem(name="Burger", price=Decimal("15.00"), quantity=1),
                ReceiptItem(name="Salad", price=Decimal("12.00"), quantity=1),
                ReceiptItem(name="Fries", price=Decimal("5.00"), quantity=2),
            ],
            currency="USD",
            subtotal=Decimal("37.00"),
            total=Decimal("37.00"),
        )
        mock_service.extract_receipt_items = AsyncMock(return_value=expected_receipt_data)

        # Execute - pass image_bytes directly
        image_bytes = b"fake_image_data"
        result = await extract_receipt_ocr(chat_id=12345, image_bytes=image_bytes)

        # Verify
        assert result.currency == "USD"
        assert len(result.items) == 3
        assert result.items[0].name == "Burger"
        assert result.items[0].price == Decimal("15.00")
        assert result.total == Decimal("37.00")

        # Verify service was called correctly
        mock_service.extract_receipt_items.assert_called_once_with(image_bytes)

    @pytest.mark.asyncio
    @patch("src.tools.llm_processing.AnthropicService")
    async def test_extract_receipt_failure(self, mock_service_class):
        """Test OCR extraction failure."""
        from unittest.mock import AsyncMock

        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.extract_receipt_items = AsyncMock(
            side_effect=ValueError("Failed to parse OCR response")
        )

        with pytest.raises(ValueError, match="Failed to parse OCR response"):
            await extract_receipt_ocr(chat_id=12345, image_bytes=b"fake_image_data")


class TestCreateInitialBillSplit:
    """Tests for create_initial_bill_split with mocked Anthropic API."""

    @pytest.mark.asyncio
    @patch("src.tools.llm_processing.AnthropicService")
    async def test_create_split_success(
        self, mock_service_class, sample_receipt_data, mock_split_response
    ):
        """Test successful bill split creation."""
        from unittest.mock import AsyncMock

        # Mock the service
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        # Create expected BillSplit
        expected_split = BillSplit(
            participants=[
                ParticipantShare(
                    name="Alice",
                    items=[
                        ParticipantItem(item_name="Burger", item_numerator=1, item_denominator=1),
                        ParticipantItem(item_name="Fries", item_numerator=1, item_denominator=2),
                    ],
                ),
                ParticipantShare(
                    name="Bob",
                    items=[
                        ParticipantItem(item_name="Salad", item_numerator=1, item_denominator=1),
                        ParticipantItem(item_name="Fries", item_numerator=1, item_denominator=2),
                    ],
                ),
            ],
            receipt_items=sample_receipt_data.items,
            currency=sample_receipt_data.currency,
            total=sample_receipt_data.total,
        )
        mock_service.split_bill = AsyncMock(return_value=expected_split)

        # Execute (TEXT-ONLY - no image needed)
        description = "Alice had burger and half the fries, Bob had salad and half the fries"
        result = await create_initial_bill_split(
            description=description,
            receipt_data=sample_receipt_data,
        )

        # Verify
        assert len(result.participants) == 2
        assert result.participants[0].name == "Alice"
        assert result.participants[1].name == "Bob"
        assert len(result.participants[0].items) == 2

        # Verify service was called
        mock_service.split_bill.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.tools.llm_processing.AnthropicService")
    async def test_create_split_parsing_error(self, mock_service_class, sample_receipt_data):
        """Test split creation with parsing error."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.split_bill = Mock(
            side_effect=ValueError("Failed to parse split response")
        )

        with pytest.raises(ValueError, match="Failed to parse split response"):
            await create_initial_bill_split(
                description="Alice had burger",
                receipt_data=sample_receipt_data,
            )


class TestRefineSplitWithLLM:
    """Tests for refine_split_with_llm with mocked Anthropic API."""

    @pytest.mark.asyncio
    @patch("src.services.anthropic_service.Anthropic")
    async def test_refine_split_success(
        self, mock_anthropic_class, sample_bill_split, sample_receipt_data
    ):
        """Test successful split refinement."""
        # Mock Anthropic client
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Mock Claude API response
        # NOTE: refine_split_with_llm prepends "{" to the response
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text='''
  "participants": [
    {
      "name": "Alice",
      "items": [
        {"item_name": "Burger", "item_numerator": 1, "item_denominator": 1},
        {"item_name": "Fries", "item_numerator": 1, "item_denominator": 1},
        {"item_name": "Soda", "item_numerator": 1, "item_denominator": 1}
      ]
    },
    {
      "name": "Bob",
      "items": [
        {"item_name": "Salad", "item_numerator": 1, "item_denominator": 1},
        {"item_name": "Fries", "item_numerator": 1, "item_denominator": 1},
        {"item_name": "Soda", "item_numerator": 1, "item_denominator": 1}
      ]
    }
  ],
  "explanation": "Adjusted item assignments to match receipt total"
}'''
            )
        ]
        mock_client.messages.create = Mock(return_value=mock_response)

        # Execute
        refined_split, explanation = await refine_split_with_llm(
            bill_split=sample_bill_split,
            receipt_data=sample_receipt_data,
            issue_explanation="Discrepancy of 5.00 detected",
        )

        # Verify
        assert len(refined_split.participants) == 2
        assert explanation == "Adjusted item assignments to match receipt total"
        mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.anthropic_service.Anthropic")
    async def test_refine_split_parsing_error(
        self, mock_anthropic_class, sample_bill_split, sample_receipt_data
    ):
        """Test refinement with invalid JSON response."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Mock invalid JSON response
        mock_response = Mock()
        mock_response.content = [Mock(text="invalid json {incomplete")]
        mock_client.messages.create = Mock(return_value=mock_response)

        with pytest.raises(ValueError, match="Failed to refine bill split"):
            await refine_split_with_llm(
                bill_split=sample_bill_split,
                receipt_data=sample_receipt_data,
                issue_explanation="Discrepancy detected",
            )

    @pytest.mark.asyncio
    @patch("src.services.anthropic_service.Anthropic")
    async def test_refine_split_calculation_error(
        self, mock_anthropic_class, sample_bill_split, sample_receipt_data
    ):
        """Test refinement when refined items cannot be matched."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Mock response with invalid item names
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text='''{
  "participants": [
    {
      "name": "Alice",
      "items": [
        {"item_name": "NonexistentItem", "item_numerator": 1, "item_denominator": 1}
      ]
    }
  ],
  "explanation": "Invalid refinement"
}'''
            )
        ]
        mock_client.messages.create = Mock(return_value=mock_response)

        with pytest.raises(ValueError, match="Cannot refine split due to item matching error|Failed to refine bill split"):
            await refine_split_with_llm(
                bill_split=sample_bill_split,
                receipt_data=sample_receipt_data,
                issue_explanation="Test error",
            )


class TestIntegration:
    """Integration tests for LLM processing workflow (all mocked)."""

    @pytest.mark.asyncio
    @patch("src.tools.llm_processing.AnthropicService")
    async def test_full_workflow_ocr_to_split(
        self, mock_service_class, sample_receipt_data, sample_bill_split
    ):
        """Test full workflow from OCR to split (all mocked)."""
        from unittest.mock import AsyncMock

        # Mock service
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.extract_receipt_items = AsyncMock(return_value=sample_receipt_data)
        mock_service.split_bill = AsyncMock(return_value=sample_bill_split)

        # Execute OCR - pass image_bytes directly
        image_bytes = b"fake_image"
        receipt_data = await extract_receipt_ocr(chat_id=12345, image_bytes=image_bytes)

        # Verify OCR result
        assert receipt_data == sample_receipt_data

        # Execute split (TEXT-ONLY - no image needed)
        description = "Alice and Bob split the bill"
        bill_split = await create_initial_bill_split(
            description=description,
            receipt_data=receipt_data,
        )

        # Verify split result
        assert bill_split == sample_bill_split
