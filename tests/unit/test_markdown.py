from __future__ import annotations

from app.utils.markdown import render_markdown_safe


class TestRenderMarkdownSafe:
    def test_empty(self):
        assert render_markdown_safe(None) == ""
        assert render_markdown_safe("") == ""
        assert render_markdown_safe("   ") == ""

    def test_bold_italic(self):
        html = render_markdown_safe("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_bullet_list(self):
        html = render_markdown_safe("- a\n- b")
        assert "<ul>" in html
        assert "<li>a</li>" in html
        assert "<li>b</li>" in html

    def test_ordered_list(self):
        html = render_markdown_safe("1. one\n2. two")
        assert "<ol>" in html
        assert "<li>one</li>" in html

    def test_inline_code(self):
        html = render_markdown_safe("use `x` here")
        assert "<code>x</code>" in html

    def test_fenced_code(self):
        html = render_markdown_safe("```\nline\n```")
        assert "<pre>" in html
        assert "<code>" in html
        assert "line" in html

    def test_blockquote(self):
        html = render_markdown_safe("> quote")
        assert "<blockquote>" in html
        assert "quote" in html

    def test_heading_stays_plain(self):
        html = render_markdown_safe("# heading stays")
        assert "<h1>" not in html
        assert "# heading stays" in html

    def test_strips_raw_html_and_script(self):
        html = render_markdown_safe("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "alert(1)" in html

    def test_strips_img_onerror(self):
        html = render_markdown_safe("**x** <img src=x onerror=alert(1)>")
        assert "<img" not in html
        assert "<strong>x</strong>" in html

    def test_no_links(self):
        html = render_markdown_safe("[click](https://evil.example)")
        assert "<a " not in html
        assert "click" in html
