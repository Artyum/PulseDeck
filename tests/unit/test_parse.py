from app.utils.parse import parse_positive_int


class TestParsePositiveInt:
    def test_default_for_none(self):
        assert parse_positive_int(None) == 1

    def test_valid(self):
        assert parse_positive_int(3) == 3
        assert parse_positive_int("5") == 5

    def test_invalid_or_non_positive(self):
        assert parse_positive_int(0) == 1
        assert parse_positive_int(-2) == 1
        assert parse_positive_int("x") == 1
        assert parse_positive_int("", default=7) == 7
