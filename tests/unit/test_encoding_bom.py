from pathlib import Path

from relace_mcp.encoding.codec import (
    decode_text_with_fallback,
    read_text_with_fallback,
)


class TestEncodingBOM:
    """Test various BOM scenarios."""

    def test_utf8_bom_detection(self, tmp_path: Path) -> None:
        """Test UTF-8 with BOM detection and handling."""
        file_path = tmp_path / "utf8_bom.txt"
        # UTF-8 BOM followed by content
        file_path.write_bytes(b"\xef\xbb\xbfHello World")

        content, encoding = read_text_with_fallback(file_path)

        # Should detect UTF-8-SIG (UTF-8 with BOM)
        assert encoding in ("utf-8", "utf-8-sig")
        assert "Hello World" in content
        # Note: BOM may or may not be stripped depending on implementation

    def test_utf16_le_bom(self, tmp_path: Path) -> None:
        """Test UTF-16 LE with BOM - should not be treated as binary."""
        file_path = tmp_path / "utf16_le.txt"
        # UTF-16 LE BOM + "Hello" in UTF-16 LE
        file_path.write_bytes(b"\xff\xfeH\x00e\x00l\x00l\x00o\x00")

        # With our fix, UTF-16 BOM should be recognized as text
        content, encoding = read_text_with_fallback(file_path)
        assert "Hello" in content
        # charset_normalizer should detect UTF-16
        assert "utf" in encoding.lower()

    def test_utf16_be_bom(self, tmp_path: Path) -> None:
        """Test UTF-16 BE with BOM - should not be treated as binary."""
        file_path = tmp_path / "utf16_be.txt"
        # UTF-16 BE BOM + "Hello" in UTF-16 BE
        file_path.write_bytes(b"\xfe\xff\x00H\x00e\x00l\x00l\x00o")

        # With our fix, UTF-16 BOM should be recognized as text
        content, encoding = read_text_with_fallback(file_path)
        assert "Hello" in content
        assert "utf" in encoding.lower()

    def test_utf32_le_bom(self, tmp_path: Path) -> None:
        """Test UTF-32 LE with BOM - should not be treated as binary."""
        file_path = tmp_path / "utf32_le.txt"
        # UTF-32 LE BOM + "A" in UTF-32 LE
        file_path.write_bytes(b"\xff\xfe\x00\x00A\x00\x00\x00")

        # With our fix, UTF-32 BOM should be recognized as text
        content, encoding = read_text_with_fallback(file_path)
        assert "A" in content
        assert isinstance(encoding, str)

    def test_utf32_be_bom(self, tmp_path: Path) -> None:
        """Test UTF-32 BE with BOM - should not be treated as binary."""
        file_path = tmp_path / "utf32_be.txt"
        # UTF-32 BE BOM + "A" in UTF-32 BE
        file_path.write_bytes(b"\x00\x00\xfe\xff\x00\x00\x00A")

        # With our fix, UTF-32 BOM should be recognized as text
        content, encoding = read_text_with_fallback(file_path)
        assert "A" in content
        assert isinstance(encoding, str)

    def test_no_bom_utf8(self, tmp_path: Path) -> None:
        """Test plain UTF-8 without BOM."""
        file_path = tmp_path / "utf8_no_bom.txt"
        file_path.write_bytes(b"Hello World")

        content, encoding = read_text_with_fallback(file_path)

        assert encoding == "utf-8"
        assert content == "Hello World"


class TestEncodingFamily:
    """Test encoding family detection for CJK languages."""

    def test_japanese_shift_jis(self, tmp_path: Path) -> None:
        """Test Japanese Shift-JIS encoding family detection."""

        # Japanese text "こんにちは" in Shift-JIS
        japanese_bytes = "こんにちは".encode("shift_jis")

        # Test with preferred encoding set to another Japanese encoding
        content, encoding = decode_text_with_fallback(
            japanese_bytes,
            preferred_encoding="shift_jis",
            min_coherence=0.0,
        )

        assert "こんにちは" in content
        assert encoding.lower() in ("shift_jis", "shift_jis_2004", "cp932")

    def test_japanese_euc_jp(self, tmp_path: Path) -> None:
        """Test Japanese EUC-JP encoding family detection."""

        # Japanese text "こんにちは" in EUC-JP
        japanese_bytes = "こんにちは".encode("euc_jp")

        content, encoding = decode_text_with_fallback(
            japanese_bytes,
            preferred_encoding="euc_jp",
            min_coherence=0.0,
        )

        assert "こんにちは" in content
        # Should detect as Japanese encoding family
        assert encoding.lower() in ("euc_jp", "euc_jis_2004", "iso-2022-jp")

    def test_korean_euc_kr(self, tmp_path: Path) -> None:
        """Test Korean EUC-KR encoding family detection."""

        # Korean text "안녕하세요" in EUC-KR
        korean_bytes = "안녕하세요".encode("euc_kr")

        content, encoding = decode_text_with_fallback(
            korean_bytes,
            preferred_encoding="euc_kr",
            min_coherence=0.0,
        )

        assert "안녕하세요" in content
        assert encoding.lower() in ("euc_kr", "cp949", "johab")

    def test_encoding_family_prevents_misdetection(self, tmp_path: Path) -> None:
        """Test that encoding family prevents Japanese being detected as Big5."""

        # Japanese text that might be misdetected
        japanese_bytes = "日本語テスト".encode("euc_jp")

        # Even if charset_normalizer suggests Big5, family check should prevent it
        content, encoding = decode_text_with_fallback(
            japanese_bytes,
            preferred_encoding="euc_jp",
            min_coherence=0.0,
        )

        # Should use preferred encoding from same family
        assert encoding.lower() in ("euc_jp", "euc_jis_2004", "iso-2022-jp")
        # Should not be Big5
        assert "big5" not in encoding.lower()


class TestEncodingCorrupted:
    """Test handling of corrupted/truncated encoded files."""

    def test_truncated_utf8_file(self, tmp_path: Path) -> None:
        """Test UTF-8 file truncated mid-multi-byte character."""
        file_path = tmp_path / "truncated_utf8.txt"
        # "世" is E4 B8 96 in UTF-8, truncate to E4 B8 (incomplete)
        file_path.write_bytes(b"Hello \xe4\xb8")

        # Should handle gracefully (may use replacement characters)
        content, encoding = read_text_with_fallback(file_path)
        assert "Hello" in content
        # encoding should be a string
        assert isinstance(encoding, str)

    def test_truncated_gbk_file(self, tmp_path: Path) -> None:
        """Test GBK file truncated mid-character."""
        file_path = tmp_path / "truncated_gbk.txt"
        # GBK character (e.g., 中) is two bytes, truncate to one
        file_path.write_bytes(b"\xd6\xd0"[:1])  # Incomplete GBK sequence

        # Should handle gracefully
        content, encoding = read_text_with_fallback(file_path)
        # Should not crash
        assert isinstance(content, str)
        assert isinstance(encoding, str)

    def test_mixed_encoding_file(self, tmp_path: Path) -> None:
        """Test file with mixed encodings (invalid but should not crash)."""
        file_path = tmp_path / "mixed.txt"
        # Mix of UTF-8 and invalid bytes
        file_path.write_bytes(b"Hello \xff\xfe World")

        content, encoding = read_text_with_fallback(file_path)
        assert "Hello" in content
        assert "World" in content
        assert isinstance(encoding, str)

    def test_file_with_null_bytes(self, tmp_path: Path) -> None:
        """Test file containing null bytes (often indicates binary)."""
        file_path = tmp_path / "null_bytes.txt"
        file_path.write_bytes(b"Hello\x00World")

        # Null bytes often trigger binary detection
        from relace_mcp.encoding.codec import decode_text_best_effort

        result = decode_text_best_effort(file_path.read_bytes(), path=file_path)
        # Should return None or handle as binary
        assert result is None or isinstance(result, str)


class TestEncodingLargeFiles:
    """Test encoding detection on large files."""

    def test_large_utf8_file(self, tmp_path: Path) -> None:
        """Test UTF-8 file larger than sample size."""
        file_path = tmp_path / "large_utf8.txt"
        # Create file larger than 8192 bytes (default sample size)
        content = "x" * 10000
        file_path.write_text(content, encoding="utf-8")

        read_content, encoding = read_text_with_fallback(file_path)

        assert encoding == "utf-8"
        assert len(read_content) == 10000

    def test_large_gbk_file(self, tmp_path: Path) -> None:
        """Test GBK encoded file larger than sample size."""
        file_path = tmp_path / "large_gbk.txt"
        # Create large GBK content
        content = "中文內容" * 1000  # Chinese characters
        file_path.write_bytes(content.encode("gbk"))

        read_content, encoding = read_text_with_fallback(file_path)

        # Should detect GBK or compatible encoding
        assert encoding.lower() in ("gbk", "gb2312", "gb18030")
        assert "中文" in read_content


class TestEncodingPythonSource:
    """Test Python source file encoding declarations."""

    def test_python_coding_cookie_utf8(self, tmp_path: Path) -> None:
        """Test Python file with UTF-8 coding cookie."""
        file_path = tmp_path / "coding_utf8.py"
        file_path.write_bytes(b"# -*- coding: utf-8 -*-\nprint('hello')")

        content, encoding = read_text_with_fallback(file_path)

        # Should detect from coding cookie
        assert encoding == "utf-8"
        assert "hello" in content

    def test_python_coding_cookie_latin1(self, tmp_path: Path) -> None:
        """Test Python file with latin-1 coding cookie."""
        file_path = tmp_path / "coding_latin1.py"
        file_path.write_bytes(b"# -*- coding: latin-1 -*-\n# caf\xe9")

        content, encoding = read_text_with_fallback(file_path)

        # Should detect from coding cookie (latin-1 or iso-8859-1 are equivalent)
        assert encoding in ("latin-1", "iso-8859-1")
        assert "café" in content

    def test_python_pep263_declaration(self, tmp_path: Path) -> None:
        """Test Python file with PEP 263 encoding declaration."""
        file_path = tmp_path / "pep263.py"
        file_path.write_bytes(b"#!/usr/bin/env python\n# coding: gbk\n# \xc4\xe3\xba\xc3")

        content, encoding = read_text_with_fallback(file_path)

        # Verify encoding is detected and is a valid GBK variant
        assert encoding.lower() in ("gbk", "gb2312")
        assert isinstance(encoding, str)
        assert "你好" in content


class TestEncodingFallback:
    """Test encoding fallback behavior."""

    def test_unknown_encoding_fallback(self, tmp_path: Path) -> None:
        """Test fallback when encoding cannot be determined."""
        file_path = tmp_path / "unknown.bin"
        # Valid UTF-8 content that looks like ASCII
        file_path.write_bytes(b"Simple ASCII content")

        content, encoding = read_text_with_fallback(file_path)

        # Should fallback to UTF-8 for ASCII-like content
        assert encoding in ("utf-8", "ascii")
        assert "Simple ASCII content" in content

    def test_preferred_encoding_override(self, tmp_path: Path) -> None:
        """Test that preferred encoding is used when appropriate."""
        from relace_mcp.encoding.codec import set_project_encoding

        set_project_encoding("gbk")
        try:
            file_path = tmp_path / "preferred.txt"
            # GBK content
            file_path.write_bytes("中文測試".encode("gbk"))

            content, encoding = read_text_with_fallback(file_path)

            # Should use preferred encoding
            assert "中文" in content
            assert encoding == "gbk"
        finally:
            set_project_encoding(None)
