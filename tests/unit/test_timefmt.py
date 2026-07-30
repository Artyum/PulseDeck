from datetime import datetime, timezone

from app.utils.timefmt import _aware, age_since, format_relative, gap_between


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


class TestFormatRelative:
    def test_seconds(self):
        assert format_relative(0) == "0 s"
        assert format_relative(30) == "30 s"
        assert format_relative(59) == "59 s"

    def test_minutes(self):
        assert format_relative(60) == "1 min"
        assert format_relative(120) == "2 min"
        assert format_relative(3540) == "59 min"

    def test_hours(self):
        assert format_relative(3600) == "1 h"
        assert format_relative(7200) == "2 h"
        assert format_relative(172_200) == "47 h"  # < 48h

    def test_almost_48h(self):
        assert format_relative(172_500) == "47 h"

    def test_days(self):
        assert format_relative(172_800) == "2 d"  # 48h = 2 days
        assert format_relative(86400 * 30) == "30 d"
        assert format_relative(86400 * 59) == "59 d"

    def test_months(self):
        assert format_relative(86400 * 60) == "2 mies."
        assert format_relative(86400 * 365) == "12 mies."
        assert format_relative(86400 * 30 * 23) == "23 mies."

    def test_years(self):
        assert format_relative(86400 * 365 * 2) == "2 lat"
        assert format_relative(86400 * 365 * 10) == "10 lat"

    def test_negative_delta(self):
        assert format_relative(-30) == "30 s"
        assert format_relative(-3600) == "1 h"


class TestAgeSince:
    def test_none(self):
        assert age_since(None) == "\u2014"

    def test_seconds_ago(self, monkeypatch):
        now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        dt = datetime(2024, 6, 15, 11, 59, 30, tzinfo=timezone.utc)
        assert age_since(dt, now=now) == "30 s"

    def test_minutes_ago(self, monkeypatch):
        now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        dt = datetime(2024, 6, 15, 11, 55, 0, tzinfo=timezone.utc)
        assert age_since(dt, now=now) == "5 min"


class TestGapBetween:
    def test_none(self):
        assert gap_between(None, datetime.now(timezone.utc)) == ""
        assert gap_between(datetime.now(timezone.utc), None) == ""
        assert gap_between(None, None) == ""

    def test_positive_gap(self):
        earlier = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        later = datetime(2024, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
        assert gap_between(earlier, later) == "2 h"
