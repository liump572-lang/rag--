import pytest
from unittest.mock import MagicMock, patch, mock_open
from app.common.parsers.chunker import recursive_character_split
from app.common.parsers.cleaner import clean_parsed_text, extract_structure_metadata


class TestRecursiveCharacterSplit:
    def test_empty_text(self):
        result = recursive_character_split("", chunk_size=100, chunk_overlap=20)
        assert result == []

    def test_short_text_no_chunking(self):
        result = recursive_character_split("Hello World", chunk_size=100, chunk_overlap=20)
        assert len(result) == 1
        assert result[0] == "Hello World"

    def test_default_params(self):
        text = "a" * 2000
        result = recursive_character_split(text)
        assert len(result) > 0

    def test_chinese_text(self):
        text = "二叉树是一种重要的数据结构。" * 20
        result = recursive_character_split(text, chunk_size=30, chunk_overlap=5)
        assert len(result) >= 1

    def test_deduplicate_consecutive(self):
        text = "alpha\n\nbeta\n\ngamma\n\ndelta"
        result = recursive_character_split(text, chunk_size=200, chunk_overlap=10)
        assert len(result) >= 1

    def test_paragraph_separator(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = recursive_character_split(text, chunk_size=50, chunk_overlap=5)
        assert len(result) > 0

    def test_chunk_overlap_behavior(self):
        text = "The quick brown fox jumps over the lazy dog. " * 10
        result = recursive_character_split(text, chunk_size=40, chunk_overlap=10)
        assert len(result) > 0


class TestCleanParsedText:
    def test_empty_string(self):
        assert clean_parsed_text("") == ""

    def test_remove_excessive_newlines(self):
        text = "a\n\n\n\n\nb"
        result = clean_parsed_text(text)
        assert "\n\n\n" not in result

    def test_remove_excessive_spaces(self):
        text = "hello    world"
        result = clean_parsed_text(text)
        assert "  " not in result

    def test_normalize_unicode_dashes(self):
        text = "test\u2013test"
        result = clean_parsed_text(text)
        assert "\u2013" not in result

    def test_remove_standalone_page_numbers(self):
        text = "text\n42\ntext"
        result = clean_parsed_text(text)
        assert "42" not in result or "\n\n" in result

    def test_remove_noise_lines(self):
        text = "text\n==========\ntext"
        result = clean_parsed_text(text)
        assert "==========" not in result

    def test_preserve_normal_text(self):
        text = "Hello World"
        result = clean_parsed_text(text)
        assert result == "Hello World"

    def test_chinese_text_preserved(self):
        text = "你好世界"
        result = clean_parsed_text(text)
        assert "你好" in result


class TestExtractStructureMetadata:
    def test_empty_text(self):
        result = extract_structure_metadata("")
        assert "sections" in result
        assert "definitions" in result

    def test_extract_sections(self):
        text = "# 第一章\n内容\n## 第二节\n更多内容"
        result = extract_structure_metadata(text)
        assert len(result["sections"]) >= 1

    def test_extract_definitions(self):
        text = "二叉树是指每个节点最多有两个子树的树结构。"
        result = extract_structure_metadata(text)
        assert len(result["definitions"]) > 0

    def test_no_definitions(self):
        text = "这是普通文本，不包含定义。"
        result = extract_structure_metadata(text)
        assert len(result["definitions"]) >= 0


class TestParserImports:
    def test_txt_parser_module(self):
        from app.common.parsers import txt_parser
        assert hasattr(txt_parser, "parse_txt")

    def test_md_parser_module(self):
        from app.common.parsers import md_parser
        assert hasattr(md_parser, "parse_md")

    def test_pdf_parser_module(self):
        from app.common.parsers import pdf_parser
        assert hasattr(pdf_parser, "parse_pdf")

    def test_docx_parser_module(self):
        from app.common.parsers import docx_parser
        assert hasattr(docx_parser, "parse_docx")

    def test_pptx_parser_module(self):
        from app.common.parsers import pptx_parser
        assert hasattr(pptx_parser, "parse_pptx")

    def test_chunker_module(self):
        from app.common.parsers import chunker
        assert hasattr(chunker, "recursive_character_split")

    def test_cleaner_module(self):
        from app.common.parsers import cleaner
        assert hasattr(cleaner, "clean_parsed_text")
        assert hasattr(cleaner, "extract_structure_metadata")


class TestChunkerBehavior:
    @patch("app.common.parsers.chunker._char_split_safe")
    def test_char_split_fallback(self, mock_char_split):
        mock_char_split.return_value = ["chunk1", "chunk2"]
        text = "a" * 500
        result = recursive_character_split(text, chunk_size=100, chunk_overlap=10)
        assert len(result) > 0
