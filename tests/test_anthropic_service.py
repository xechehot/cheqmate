"""Tests for Anthropic API service."""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.models.bill import BillSplit, Receipt, ReceiptItem
from src.services.anthropic_service import (
    AnthropicService,
    detect_image_media_type,
    extract_json_from_response,
)


class TestExtractJsonFromResponse:
    """Test suite for JSON extraction helper."""

    def test_plain_json(self):
        """Test extraction of plain JSON."""
        response = '{"key": "value"}'
        result = extract_json_from_response(response)
        assert result == '{"key": "value"}'

    def test_json_in_markdown_code_block(self):
        """Test extraction from markdown code block."""
        response = '```json\n{"key": "value"}\n```'
        result = extract_json_from_response(response)
        assert result == '{"key": "value"}'

    def test_json_in_code_block_without_language(self):
        """Test extraction from code block without language."""
        response = '```\n{"key": "value"}\n```'
        result = extract_json_from_response(response)
        assert result == '{"key": "value"}'

    def test_json_with_whitespace(self):
        """Test extraction with extra whitespace."""
        response = '  \n```json\n{"key": "value"}\n```\n  '
        result = extract_json_from_response(response)
        assert result == '{"key": "value"}'


class TestDetectImageMediaType:
    """Test suite for image media type detection."""

    def test_detect_jpeg(self):
        """Test JPEG signature detection."""
        jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 10
        assert detect_image_media_type(jpeg_bytes) == "image/jpeg"

    def test_detect_png(self):
        """Test PNG signature detection."""
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
        assert detect_image_media_type(png_bytes) == "image/png"

    def test_detect_gif87(self):
        """Test GIF87a signature detection."""
        gif_bytes = b"GIF87a" + b"\x00" * 10
        assert detect_image_media_type(gif_bytes) == "image/gif"

    def test_detect_gif89(self):
        """Test GIF89a signature detection."""
        gif_bytes = b"GIF89a" + b"\x00" * 10
        assert detect_image_media_type(gif_bytes) == "image/gif"

    def test_detect_webp(self):
        """Test WEBP signature detection."""
        webp_bytes = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 10
        assert detect_image_media_type(webp_bytes) == "image/webp"

    def test_unknown_format_defaults_to_jpeg(self):
        """Test unknown format defaults to JPEG."""
        unknown_bytes = b"UNKNOWN" + b"\x00" * 10
        assert detect_image_media_type(unknown_bytes) == "image/jpeg"


class TestAnthropicServiceReceiptExtraction:
    """Test suite for receipt extraction with Anthropic API."""

    @pytest.mark.asyncio
    async def test_extract_receipt_usd_success(
        self,
        sample_image_bytes: bytes,
        mock_anthropic_receipt_response_usd: dict,
    ):
        """Test successful receipt extraction with USD currency."""
        # Mock the Anthropic client
        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            # Mock the API response
            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(mock_anthropic_receipt_response_usd)[
                1:
            ]  # Remove leading {
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            # Create service and call method
            service = AnthropicService()
            receipt = await service.extract_receipt_items(sample_image_bytes)

            # Verify the result
            assert isinstance(receipt, Receipt)
            assert receipt.restaurant_name == "Test Restaurant"
            assert receipt.restaurant_address == "123 Main St, City, State"
            assert receipt.currency == "USD"
            assert len(receipt.items) == 3
            assert receipt.total == Decimal("45.00")

            # Verify first item
            assert receipt.items[0].description == "Burger"
            assert receipt.items[0].line_total == Decimal("15.00")
            assert receipt.items[0].quantity == 1

    @pytest.mark.asyncio
    async def test_extract_receipt_kzt_success(
        self,
        sample_image_bytes: bytes,
        mock_anthropic_receipt_response_kzt: dict,
    ):
        """Test successful receipt extraction with KZT currency."""
        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(mock_anthropic_receipt_response_kzt)[1:]
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()
            receipt = await service.extract_receipt_items(sample_image_bytes)

            assert receipt.currency == "KZT"
            assert receipt.restaurant_name == "Almaty Cafe"
            assert receipt.total == Decimal("8400")
            assert len(receipt.items) == 3

            # Verify item with quantity > 1
            lagman = receipt.items[1]
            assert lagman.description == "Lagman"
            assert lagman.quantity == 2
            assert lagman.line_total == Decimal("4000")
            assert lagman.unit_price == Decimal("2000")

    @pytest.mark.asyncio
    async def test_extract_receipt_missing_currency_defaults_to_usd(
        self, sample_image_bytes: bytes
    ):
        """Test that missing currency defaults to USD."""
        response_without_currency = {
            "restaurant_name": "Test",
            "items": [{"description": "Item", "line_total": 10.0}],
            "total": 10.0,
        }

        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(response_without_currency)[1:]
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()
            receipt = await service.extract_receipt_items(sample_image_bytes)

            assert receipt.currency == "USD"

    @pytest.mark.asyncio
    async def test_extract_receipt_calculates_unit_price(
        self, sample_image_bytes: bytes
    ):
        """Test that unit_price is calculated when not provided."""
        response = {
            "restaurant_name": "Test",
            "currency": "USD",
            "items": [
                {
                    "description": "Item",
                    "quantity": 2,
                    "line_total": 20.0,
                    # unit_price not provided
                }
            ],
            "total": 20.0,
        }

        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(response)[1:]
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()
            receipt = await service.extract_receipt_items(sample_image_bytes)

            assert receipt.items[0].unit_price == Decimal("10.0")

    @pytest.mark.asyncio
    async def test_extract_receipt_invalid_json(self, sample_image_bytes: bytes):
        """Test error handling for invalid JSON response."""
        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = "invalid json"
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()

            with pytest.raises(ValueError, match="Failed to extract receipt items"):
                await service.extract_receipt_items(sample_image_bytes)


class TestAnthropicServiceBillSplitting:
    """Test suite for bill splitting with Anthropic API."""

    @pytest.mark.asyncio
    async def test_split_bill_success(
        self,
        sample_receipt_usd: Receipt,
        mock_anthropic_split_response: dict,
    ):
        """Test successful bill splitting."""
        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(mock_anthropic_split_response)[1:]
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()
            bill_split = await service.split_bill(
                "Alice had burger, Bob had salad, Charlie had pasta",
                sample_receipt_usd,
            )

            assert isinstance(bill_split, BillSplit)
            assert len(bill_split.participants) == 3
            assert bill_split.receipt == sample_receipt_usd

            # Verify first participant
            alice = bill_split.participants[0]
            assert alice.name == "Alice"
            assert alice.items == ["Burger"]
            assert alice.amount == Decimal("15.00")

    @pytest.mark.asyncio
    async def test_split_bill_with_shared_items(self, sample_receipt_usd: Receipt):
        """Test bill splitting with shared items."""
        shared_response = {
            "participants": [
                {"name": "Alice", "items": ["Burger"], "amount": 15.00},
                {
                    "name": "Bob",
                    "items": ["Salad (shared)", "Pasta (shared)"],
                    "amount": 15.00,
                },
                {
                    "name": "Charlie",
                    "items": ["Salad (shared)", "Pasta (shared)"],
                    "amount": 15.00,
                },
            ]
        }

        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(shared_response)[1:]
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()
            bill_split = await service.split_bill(
                "Alice had burger, Bob and Charlie shared salad and pasta",
                sample_receipt_usd,
            )

            assert len(bill_split.participants) == 3
            # Verify Bob has shared items
            assert "Salad (shared)" in bill_split.participants[1].items

    @pytest.mark.asyncio
    async def test_split_bill_invalid_json(self, sample_receipt_usd: Receipt):
        """Test error handling for invalid JSON in split response."""
        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = "invalid json"
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()

            with pytest.raises(ValueError, match="Failed to split bill"):
                await service.split_bill("test description", sample_receipt_usd)

    @pytest.mark.asyncio
    async def test_split_bill_uses_currency_in_prompt(
        self, sample_receipt_kzt: Receipt
    ):
        """Test that bill splitting uses correct currency in prompts."""
        mock_response = {
            "participants": [
                {"name": "Alice", "items": ["Beshbarmak"], "amount": 3500},
                {"name": "Bob", "items": ["Lagman"], "amount": 4000},
            ]
        }

        with patch("src.services.anthropic_service.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client

            mock_message = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(mock_response)[1:]
            mock_message.content = [mock_content]
            mock_client.messages.create.return_value = mock_message

            service = AnthropicService()
            bill_split = await service.split_bill(
                "Alice had Beshbarmak, Bob had Lagman", sample_receipt_kzt
            )

            # Verify the prompt included KZT formatting
            call_args = mock_client.messages.create.call_args
            messages = call_args.kwargs["messages"]
            user_message = messages[0]["content"][0]["text"]

            # Check that KZT symbol appears in prompt
            assert "₸" in user_message or "KZT" in user_message
