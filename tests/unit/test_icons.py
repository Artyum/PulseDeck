from __future__ import annotations

from markupsafe import Markup

from app.utils.icons import render_icon


def test_known_icon_has_svg_and_icon_class() -> None:
    html = str(render_icon("search"))
    assert isinstance(render_icon("search"), Markup)
    assert html.startswith("<svg")
    assert 'class="icon"' in html
    assert 'viewBox="0 0 24 24"' in html
    assert 'aria-hidden="true"' in html
    assert 'focusable="false"' in html
    assert 'cx="11"' in html
    assert "stroke-width" not in html


def test_class_override_and_alias() -> None:
    html = str(render_icon("people", "icon icon--lg"))
    assert 'class="icon icon--lg"' in html
    assert str(render_icon("members")) == str(render_icon("people"))
    assert str(render_icon("attachments")) == str(render_icon("attach"))
    assert "M13.73 21" in str(render_icon("bell-off"))


def test_unknown_and_invalid_names_are_empty() -> None:
    assert str(render_icon("no-such-icon")) == ""
    assert str(render_icon("../search")) == ""
    assert str(render_icon("")) == ""
