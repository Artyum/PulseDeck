from __future__ import annotations

import nh3
from markdown_it import MarkdownIt
from markupsafe import Markup

_ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "blockquote",
}

_DISABLED_RULES = (
    "heading",
    "lheading",
    "link",
    "image",
    "autolink",
    "html_inline",
    "html_block",
    "reference",
    "entity",
)

_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).disable(
    _DISABLED_RULES
)


def render_markdown_safe(text: str | None) -> Markup:
    if not text or not str(text).strip():
        return Markup("")
    html = _md.render(str(text))
    return Markup(nh3.clean(html, tags=_ALLOWED_TAGS, attributes={}))
