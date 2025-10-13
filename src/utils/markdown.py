"""Markdown formatting utilities for Telegram messages.

This module provides utilities for safely formatting Telegram messages with Markdown,
including escaping special characters and handling formatting errors.
"""


def escape_markdown(text: str) -> str:
    """
    Escape Telegram Markdown special characters in text.

    Telegram uses Markdown V1 by default, which has the following special characters:
    - _ (underscore): italic
    - * (asterisk): bold
    - [ (left bracket): link
    - ` (backtick): code

    This function escapes these characters to prevent them from being interpreted
    as Markdown formatting when they appear in user-generated content (item names,
    participant names, etc.).

    Args:
        text: Text that may contain Markdown special characters

    Returns:
        Text with special characters escaped

    Examples:
        >>> escape_markdown("Fish_n_Chips")
        'Fish\\_n\\_Chips'
        >>> escape_markdown("**Large** Coffee")
        '\\*\\*Large\\*\\* Coffee'
        >>> escape_markdown("Sandwich [Club]")
        'Sandwich \\[Club]'
    """
    if not text:
        return text

    # Telegram Markdown V1 special characters that need escaping
    special_chars = ["_", "*", "[", "`"]

    for char in special_chars:
        text = text.replace(char, f"\\{char}")

    return text
