"""Unit tests for Markdown utilities."""

from src.utils.markdown import escape_markdown


class TestEscapeMarkdown:
    """Tests for escape_markdown function."""

    def test_escape_underscore(self):
        """Test escaping underscores (italic delimiter)."""
        assert escape_markdown("Fish_n_Chips") == "Fish\\_n\\_Chips"
        assert (
            escape_markdown("Some_text_with_underscores")
            == "Some\\_text\\_with\\_underscores"
        )

    def test_escape_asterisk(self):
        """Test escaping asterisks (bold delimiter)."""
        assert escape_markdown("**Large**") == "\\*\\*Large\\*\\*"
        assert escape_markdown("Coffee*2") == "Coffee\\*2"

    def test_escape_bracket(self):
        """Test escaping brackets (link delimiter)."""
        assert escape_markdown("Sandwich [Club]") == "Sandwich \\[Club]"
        assert escape_markdown("[Important]") == "\\[Important]"

    def test_escape_backtick(self):
        """Test escaping backticks (code delimiter)."""
        assert escape_markdown("`Code`") == "\\`Code\\`"
        assert escape_markdown("Item `special`") == "Item \\`special\\`"

    def test_escape_multiple_special_chars(self):
        """Test escaping multiple special characters at once."""
        assert (
            escape_markdown("Fish_n_Chips**[Large]")
            == "Fish\\_n\\_Chips\\*\\*\\[Large]"
        )
        assert (
            escape_markdown("**Bold** and _italic_")
            == "\\*\\*Bold\\*\\* and \\_italic\\_"
        )

    def test_empty_string(self):
        """Test handling of empty string."""
        assert escape_markdown("") == ""

    def test_none_value(self):
        """Test handling of None value."""
        assert escape_markdown(None) is None

    def test_no_special_chars(self):
        """Test strings without special characters pass through unchanged."""
        assert escape_markdown("Regular Text") == "Regular Text"
        assert escape_markdown("Hello World 123") == "Hello World 123"

    def test_real_world_item_names(self):
        """Test with realistic receipt item names."""
        assert escape_markdown("Coca_Cola") == "Coca\\_Cola"
        assert escape_markdown("Pizza [Large]") == "Pizza \\[Large]"
        assert escape_markdown("Coffee**2") == "Coffee\\*\\*2"
        assert escape_markdown("Fish & Chips") == "Fish & Chips"  # & is OK
        assert escape_markdown("Price: $15.99") == "Price: $15.99"  # $ is OK

    def test_participant_names(self):
        """Test with realistic participant names that might have special chars."""
        assert escape_markdown("John_Doe") == "John\\_Doe"
        assert escape_markdown("Sarah*Smith") == "Sarah\\*Smith"
        assert escape_markdown("Alice [Lead]") == "Alice \\[Lead]"
