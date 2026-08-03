import pytest

from app.models.enums import TicketPriority, TicketStatus, TicketType, UserRole
from app.utils.timefmt import DATETIME_FORMAT_IDS
from app.validation import (
    FIELDS,
    FieldValidationError,
    ValidationValueError,
    clean,
    clean_many,
    field_attrs,
    field_spec,
    format_error,
)
from app.validation.engine import validate


def _limits():
    return {
        fid: spec.max_len for fid, spec in FIELDS.items() if spec.max_len is not None
    }


class TestRegistryCompleteness:
    def test_expected_fields_present(self):
        expected = {
            "user.email",
            "user.password",
            "user.first_name",
            "user.last_name",
            "user.phone",
            "user.role",
            "user.ui_lang",
            "user.datetime_format",
            "user.timezone",
            "project.name",
            "project.key",
            "project.description",
            "ticket.title",
            "ticket.description",
            "ticket.type",
            "ticket.status",
            "ticket.priority",
            "comment.content",
            "tag.name",
            "search.q",
            "filter.tag",
        }
        assert set(FIELDS) == expected

    def test_declared_max_lengths(self):
        assert _limits() == {
            "user.email": 320,
            "user.password": 72,
            "user.first_name": 120,
            "user.last_name": 120,
            "user.phone": 20,
            "user.timezone": 64,
            "project.name": 200,
            "project.key": 5,
            "project.description": 2000,
            "ticket.title": 300,
            "ticket.description": 10000,
            "comment.content": 10000,
            "tag.name": 80,
            "search.q": 200,
            "filter.tag": 80,
        }

    def test_unknown_field_raises(self):
        with pytest.raises(KeyError):
            field_spec("no.such.field")


class TestTextFields:
    @pytest.mark.parametrize(
        ("field_id", "raw", "expected"),
        [
            ("ticket.title", "  Hello  ", "Hello"),
            ("user.first_name", "\tAda\n", "Ada"),
            ("project.name", " Pulse ", "Pulse"),
            ("tag.name", "  foo   bar  ", "foo bar"),
        ],
    )
    def test_normalize(self, field_id, raw, expected):
        assert clean(field_id, raw) == expected

    @pytest.mark.parametrize(
        "field_id",
        [
            "ticket.title",
            "ticket.description",
            "comment.content",
            "user.first_name",
            "user.last_name",
            "project.name",
            "tag.name",
        ],
    )
    def test_required_rejects_empty(self, field_id):
        with pytest.raises(ValidationValueError) as exc:
            clean(field_id, "   ")
        assert exc.value.code == "required"
        assert exc.value.field == field_id

    @pytest.mark.parametrize(
        "field_id",
        ["project.description", "search.q", "filter.tag", "user.phone"],
    )
    def test_optional_empty_returns_none(self, field_id):
        assert clean(field_id, "") is None
        assert clean(field_id, "  ") is None
        assert clean(field_id, None) is None

    @pytest.mark.parametrize(
        "field_id",
        [
            "ticket.title",
            "ticket.description",
            "comment.content",
            "project.description",
            "project.name",
            "user.first_name",
            "user.last_name",
            "tag.name",
            "search.q",
            "filter.tag",
            "user.email",
        ],
    )
    def test_accepts_exact_max(self, field_id):
        spec = field_spec(field_id)
        assert spec.max_len is not None
        if field_id == "user.email":
            local = "a" * (spec.max_len - len("@b.co"))
            assert clean(field_id, f"{local}@b.co") == f"{local}@b.co"
            return
        value = "x" * spec.max_len
        assert clean(field_id, value) == value

    @pytest.mark.parametrize(
        "field_id",
        [
            "ticket.title",
            "ticket.description",
            "comment.content",
            "project.description",
            "project.name",
            "user.first_name",
            "tag.name",
            "search.q",
            "filter.tag",
        ],
    )
    def test_rejects_over_max(self, field_id):
        spec = field_spec(field_id)
        assert spec.max_len is not None
        with pytest.raises(ValidationValueError) as exc:
            clean(field_id, "x" * (spec.max_len + 1))
        assert exc.value.code == "too_long"


class TestEmail:
    def test_normalizes_case_and_strip(self):
        assert clean("user.email", "  A@B.COM ") == "a@b.com"

    @pytest.mark.parametrize(
        "raw", ["", " ", "plain", "@x.com", "a@", "a@b", "a b@c.com"]
    )
    def test_invalid(self, raw):
        with pytest.raises(ValidationValueError) as exc:
            clean("user.email", raw)
        assert exc.value.code in {"required", "invalid"}


class TestPhone:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("+48123456789", "+48123456789"),
            ("  +48 123 456 789  ", "+48123456789"),
            ("+48-123-456-789", "+48123456789"),
            ("+48(12)3456789", "+48123456789"),
        ],
    )
    def test_valid(self, raw, expected):
        assert clean("user.phone", raw) == expected

    @pytest.mark.parametrize("raw", ["abc", "123", "+", "+48abc", "+0123456789"])
    def test_invalid(self, raw):
        with pytest.raises(ValidationValueError) as exc:
            clean("user.phone", raw)
        assert exc.value.code == "pattern"


class TestProjectKey:
    @pytest.mark.parametrize("raw", ["A", "ab12", " ABCDE ", "12345"])
    def test_valid(self, raw):
        assert clean("project.key", raw) == raw.strip().upper()

    @pytest.mark.parametrize("raw", ["", "ABCDEF", "a b", "a-b", "a_b"])
    def test_invalid(self, raw):
        with pytest.raises(ValidationValueError) as exc:
            clean("project.key", raw)
        assert exc.value.code in {"required", "pattern", "too_long"}


class TestPassword:
    def test_valid(self):
        assert clean("user.password", "Admin123!abcd") == "Admin123!abcd"

    def test_does_not_strip(self):
        assert clean("user.password", " Admin123!abcd ") == " Admin123!abcd "

    def test_too_short(self):
        with pytest.raises(ValidationValueError) as exc:
            clean("user.password", "Ab1!")
        assert exc.value.code == "too_short"

    def test_too_long_bytes(self):
        long_pwd = "Aa1!" + ("x" * 70)
        with pytest.raises(ValidationValueError) as exc:
            clean("user.password", long_pwd)
        assert exc.value.code == "too_long"

    @pytest.mark.parametrize(
        ("raw", "needle"),
        [
            ("ADMIN123!XXXX", "lower"),
            ("admin123!xxxx", "upper"),
            ("Admin!!!!!!!!", "digit"),
            ("Admin1234xxxx", "special"),
        ],
    )
    def test_strength_rules(self, raw, needle):
        with pytest.raises(ValidationValueError) as exc:
            clean("user.password", raw)
        assert needle in str(exc.value).lower()


class TestEnumsAndTimezone:
    @pytest.mark.parametrize(
        ("field_id", "value"),
        [
            ("user.role", UserRole.ADMIN.value),
            ("ticket.type", TicketType.BUG.value),
            ("ticket.status", TicketStatus.NEW.value),
            ("ticket.priority", TicketPriority.HIGH.value),
            ("user.datetime_format", DATETIME_FORMAT_IDS[0]),
        ],
    )
    def test_enum_accepts(self, field_id, value):
        assert clean(field_id, value) == value

    @pytest.mark.parametrize(
        "field_id",
        [
            "user.role",
            "ticket.type",
            "ticket.status",
            "ticket.priority",
            "user.datetime_format",
        ],
    )
    def test_enum_rejects(self, field_id):
        with pytest.raises(ValidationValueError) as exc:
            clean(field_id, "NOT_A_VALUE")
        assert exc.value.code == "invalid"

    def test_timezone_accepts(self):
        assert clean("user.timezone", "Europe/Warsaw") == "Europe/Warsaw"
        assert clean("user.timezone", "UTC") == "UTC"

    def test_timezone_rejects(self):
        with pytest.raises(ValidationValueError) as exc:
            clean("user.timezone", "Not/AZone")
        assert exc.value.code == "invalid"


class TestCleanManyAndErrors:
    def test_clean_many(self):
        data = clean_many(
            {
                "ticket.title": "  T  ",
                "ticket.description": " Body ",
            }
        )
        assert data == {"ticket.title": "T", "ticket.description": "Body"}

    def test_trims_nbsp_edges_on_rich_text(self):
        raw = "&nbsp;\nawdawd\n&nbsp;\n&nbsp;"
        assert clean("comment.content", raw) == "awdawd"
        assert clean("ticket.description", raw) == "awdawd"

    def test_keeps_internal_blank_lines(self):
        raw = "one\n\ntwo"
        assert clean("comment.content", raw) == "one\n\ntwo"

    def test_clean_many_stops_on_first_error(self):
        with pytest.raises(ValidationValueError) as exc:
            clean_many({"ticket.title": "", "ticket.description": "ok"})
        assert exc.value.field == "ticket.title"

    def test_validate_structured(self):
        with pytest.raises(FieldValidationError) as exc:
            validate("ticket.title", "")
        assert exc.value.code == "required"

    def test_format_error_generic(self):
        err = FieldValidationError("too_long", "ticket.title", params={"max": 300})
        msg = format_error("en", err)
        assert "300" in msg
        assert "Title" in msg

    def test_format_error_password_reason(self):
        err = FieldValidationError(
            "too_short",
            "user.password",
            params={"min": 12, "reason": "min_length"},
        )
        assert "12" in format_error("en", err)

    def test_format_error_phone_and_key(self):
        phone_err = FieldValidationError("pattern", "user.phone")
        key_err = FieldValidationError(
            "pattern", "project.key", params={"min": 1, "max": 5}
        )
        assert "+" in format_error("en", phone_err) or "48123" in format_error(
            "en", phone_err
        )
        assert "A–Z" in format_error("en", key_err) or "A-Z" in format_error(
            "en", key_err
        ).replace("–", "-")


class TestFieldAttrs:
    def test_key_attrs(self):
        attrs = str(field_attrs("project.key"))
        assert 'maxlength="5"' in attrs
        assert "required" in attrs
        assert "pattern=" in attrs

    def test_optional_override(self):
        attrs = str(field_attrs("user.password", required=False))
        assert "required" not in attrs.split()
        assert 'maxlength="72"' in attrs
        assert 'minlength="12"' in attrs
        assert 'type="password"' in attrs

    def test_optional_field_no_required(self):
        attrs = str(field_attrs("project.description"))
        assert "required" not in attrs.split()
        assert 'maxlength="2000"' in attrs

    def test_every_field_has_attrs(self):
        for field_id in FIELDS:
            assert isinstance(str(field_attrs(field_id)), str)
