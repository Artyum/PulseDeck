from fastapi.exceptions import RequestValidationError

from app.error_handlers import friendly_validation_message


def _make_error(errors_list):
    """Create a RequestValidationError from a list of error dicts."""
    try:
        raise RequestValidationError(errors_list)
    except RequestValidationError as e:
        return e


def _error(loc, typ, msg=None):
    d = {"loc": loc, "type": typ}
    if msg:
        d["msg"] = msg
    return d


class TestFriendlyValidationMessage:
    def test_missing_title(self):
        exc = _make_error([_error(["body", "title"], "missing")])
        msg = friendly_validation_message(exc, "en")
        assert msg  # returns some message

    def test_missing_description(self):
        exc = _make_error([_error(["body", "description"], "missing")])
        msg = friendly_validation_message(exc, "en")
        assert msg

    def test_missing_user_id(self):
        exc = _make_error([_error(["body", "user_id"], "missing")])
        msg = friendly_validation_message(exc, "en")
        assert msg

    def test_missing_email(self):
        exc = _make_error([_error(["body", "email"], "missing")])
        msg = friendly_validation_message(exc, "en")
        assert msg

    def test_missing_generic_field(self):
        exc = _make_error([_error(["body", "some_unknown_field"], "missing")])
        msg = friendly_validation_message(exc, "en")
        assert "required" in msg

    def test_int_parsing_error(self):
        exc = _make_error([_error(["body", "count"], "int_parsing")])
        msg = friendly_validation_message(exc, "en")
        assert msg

    def test_int_parsing_user_id(self):
        exc = _make_error([_error(["body", "user_id"], "int_parsing")])
        msg = friendly_validation_message(exc, "en")
        assert "user" in msg.lower()

    def test_custom_message(self):
        exc = _make_error([_error(["body", "x"], "value_error", msg="Custom error")])
        msg = friendly_validation_message(exc, "en")
        assert msg == "Custom error"

    def test_no_errors(self):
        # Should not happen in practice but be resilient
        exc = _make_error([])
        msg = friendly_validation_message(exc, "en")
        assert msg

    def test_field_from_query(self):
        # loc containing non-body items
        exc = _make_error([_error(["query", "user_id"], "missing")])
        msg = friendly_validation_message(exc, "en")
        assert "user" in msg.lower()

    def test_polish_lang(self):
        exc = _make_error([_error(["body", "password"], "missing")])
        msg = friendly_validation_message(exc, "pl")
        assert msg
