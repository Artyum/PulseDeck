from datetime import datetime, timezone

from app.utils.timefmt import _aware


class TestAware:
    def test_tz_naive_becomes_utc(self):
        dt = datetime(2024, 1, 1)  # noqa: DTZ001
        result = _aware(dt)
        assert result.tzinfo is timezone.utc

    def test_tz_aware_preserved(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert _aware(dt) is dt  # same object

    def test_non_utc_tz_preserved(self):
        from zoneinfo import ZoneInfo

        dt = datetime(2024, 1, 1, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = _aware(dt)
        assert result.tzinfo == ZoneInfo("Europe/Warsaw")
