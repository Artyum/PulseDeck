from __future__ import annotations

from html import unescape

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
    "a",
}

_ALLOWED_ATTRIBUTES = {
    "a": {"href"},
}

_URL_SCHEMES = {"http", "https"}

_DISABLED_RULES = (
    "heading",
    "lheading",
    "image",
    "html_inline",
    "html_block",
    "reference",
    "entity",
)

_md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True})
    .enable("linkify")
    .disable(_DISABLED_RULES)
)


def render_markdown_safe(text: str | None) -> Markup:
    if not text or not str(text).strip():
        return Markup("")
    html = _md.render(unescape(str(text)))
    return Markup(
        nh3.clean(
            html,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRIBUTES,
            url_schemes=_URL_SCHEMES,
            link_rel="noopener noreferrer",
            set_tag_attribute_values={"a": {"target": "_blank"}},
        )
    )
