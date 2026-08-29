from typing import cast

from starlette.requests import Request

from app.utils.i18n import _flatten, resolve_lang, translations_prefix


class TestFlatten:
    def test_simple_dict(self):
        data = {"a": "1", "b": "2"}
        assert _flatten(data) == {"a": "1", "b": "2"}

    def test_nested_dict(self):
        data = {"a": {"b": "1", "c": "2"}}
        assert _flatten(data) == {"a.b": "1", "a.c": "2"}

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": "deep"}}}
        assert _flatten(data) == {"a.b.c": "deep"}

    def test_none_values_skipped(self):
        data = {"a": None, "b": "keep"}
        assert _flatten(data) == {"b": "keep"}

    def test_none_in_nested_dict(self):
        data = {"a": {"b": None, "c": "val"}}
        assert _flatten(data) == {"a.c": "val"}

    def test_non_string_values(self):
        data = {"a": 42, "b": True}
        result = _flatten(data)
        assert result["a"] == "42"
        assert result["b"] == "True"


class TestResolveLang:
    def test_explicit_valid(self):
        assert resolve_lang(explicit="pl") == "pl"

    def test_explicit_invalid_falls_back(self):
        lang = resolve_lang(explicit="de")
        assert lang in ("en", "pl")  # defaults to default

    def test_cookie_preferred(self):
        request = cast(
            Request, type("Request", (), {"cookies": {"pulsedeck_lang": "pl"}})()
        )
        assert resolve_lang(request=request) == "pl"

    def test_explicit_overrides_cookie(self):
        request = cast(
            Request, type("Request", (), {"cookies": {"pulsedeck_lang": "pl"}})()
        )
        assert resolve_lang(request=request, explicit="en") == "en"

    def test_normalize_lang_valid(self):
        from app.utils.i18n import normalize_lang

        assert normalize_lang("pl") == "pl"
        assert normalize_lang("EN") == "en"

    def test_normalize_lang_invalid(self):
        from app.utils.i18n import normalize_lang

        assert normalize_lang("de") == "en"
        assert normalize_lang(None) == "en"

    def test_default_lang(self):
        assert resolve_lang() == "en"


class TestTranslationsPrefix:
    def test_known_prefix(self):
        result = translations_prefix("en", "messages.password")
        assert "min_length" in result

    def test_unknown_prefix(self):
        result = translations_prefix("en", "nonexistent.prefix")
        assert result == {}

    def test_enum_labels(self):
        from app.utils.i18n import enum_labels

        labels = enum_labels("en", "ticket_status")
        # Just check it returns something reasonable
        assert isinstance(labels, dict)
