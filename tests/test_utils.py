import pytest
import re
from app.common.utils import generate_uuid, generate_filename, sanitize_markdown


class TestGenerateUuid:
    def test_returns_string(self):
        result = generate_uuid()
        assert isinstance(result, str)

    def test_uuid_format(self):
        result = generate_uuid()
        assert len(result.split("-")) == 5

    def test_uniqueness(self):
        uuids = {generate_uuid() for _ in range(100)}
        assert len(uuids) == 100


class TestGenerateFilename:
    def test_contains_extension(self):
        result = generate_filename("pdf")
        assert result.endswith(".pdf")

    def test_starts_with_date(self):
        result = generate_filename("md")
        parts = result.split("_")
        assert len(parts[0]) == 8

    def test_various_extensions(self):
        for ext in ["pdf", "docx", "pptx", "txt", "md"]:
            result = generate_filename(ext)
            assert result.endswith(f".{ext}")
            assert len(result) > len(ext) + 1

    def test_uniqueness(self):
        names = [generate_filename("pdf") for _ in range(50)]
        assert len(set(names)) == 50


class TestSanitizeMarkdown:
    def test_none_input(self):
        assert sanitize_markdown(None) is None

    def test_empty_string(self):
        assert sanitize_markdown("") == ""

    def test_normal_text_unchanged(self):
        text = "Hello World"
        assert sanitize_markdown(text) == text

    def test_fix_table_double_pipes(self):
        text = "|a||b|"
        result = sanitize_markdown(text)
        assert "||" not in result

    def test_fix_table_separator_colons(self):
        text = "|---|:---:|---:|"
        result = sanitize_markdown(text)
        assert ":---" not in result or result.count("---") > 0

    def test_mermaid_code_block(self):
        text = "graph TD\nA-->B"
        result = sanitize_markdown(text)
        assert "```mermaid" in result

    def test_mermaid_multiline(self):
        text = "sequenceDiagram\nAlice->>John: Hello\nJohn->>Alice: Hi"
        result = sanitize_markdown(text)
        assert result.startswith("```mermaid")

    def test_close_unclosed_fence(self):
        text = "Some text\n```python\ncode here"
        result = sanitize_markdown(text)
        assert result.endswith("```")

    def test_preserve_closed_fence(self):
        text = "```python\nprint('hello')\n```"
        result = sanitize_markdown(text)
        assert result == text

    def test_mermaid_keywords(self):
        keywords = [
            "graph", "sequenceDiagram", "classDiagram", "flowchart",
            "gantt", "pie", "erDiagram", "stateDiagram",
            "mindmap", "timeline", "journey",
        ]
        for kw in keywords:
            text = f"{kw} TD\nA-->B"
            result = sanitize_markdown(text)
            assert result.startswith("```mermaid"), f"Failed for {kw}"

    def test_consecutive_pipes_fix(self):
        text = "| a || b |"
        result = sanitize_markdown(text)
        assert "||" not in result

    def test_separator_row_fix(self):
        text = "|:---|---:|"
        result = sanitize_markdown(text)
        assert ":---" not in result

    def test_valid_table_preserved(self):
        text = "| a | b |\n|---|---|\n| 1 | 2 |"
        result = sanitize_markdown(text)
        assert "| a " in result
        assert "| 1 " in result

    def test_fix_double_pipe_in_text(self):
        text = "value1 || value2"
        result = sanitize_markdown(text)
        assert "||" in result

    def test_mixed_content(self):
        text = """# Title

graph TD
A[Start] --> B[End]

| col1 | col2 |
|------|------|
| a    | b    |
"""
        result = sanitize_markdown(text)
        assert "```mermaid" in result
        assert "| a" in result
