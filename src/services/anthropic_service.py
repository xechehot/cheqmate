import base64
import logging
from typing import Optional

import anthropic
from src.config import settings

logger = logging.getLogger(__name__)

class AnthropicService:
    """Service to interact with Anthropic API."""

    def __init__(self):
        if not settings.anthropic_api_key:
            logger.warning("Anthropic API key not found. Bill processing will fail.")
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def process_bill(self, image_bytes: bytes, description: str) -> str:
        """
        Process a bill image and description using Claude 3.5 Sonnet.
        
        Args:
            image_bytes: The raw bytes of the image.
            description: The user's description of who ordered what.
            
        Returns:
            The model's response containing the split bill.
        """
        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            media_type = "image/jpeg" # Assuming JPEG for now, Telegram usually converts to JPEG

            prompt = f"""
            You are a helpful assistant that splits restaurant bills.
            
            Here is a description of who ordered what:
            "{description}"
            
            Please look at the attached receipt image and:
            1. Extract all items and their prices.
            2. Assign each item to the correct person based on the description.
            3. If an item is not explicitly mentioned, mark it as "Shared".
            4. Calculate the subtotal for each person.
            5. Calculate the tax and tip proportionally for each person based on their subtotal.
            6. Provide a final total for each person.
            
            Format the output clearly so it can be sent back to the user. 
            Use bolding for names and totals.
            """

            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ],
                    }
                ],
            )
            
            return message.content[0].text

        except Exception as e:
            logger.error(f"Error processing bill with Anthropic: {e}", exc_info=True)
            return "Sorry, I encountered an error while processing your bill. Please try again."
