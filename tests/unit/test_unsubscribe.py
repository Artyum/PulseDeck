import pytest

from app.utils.unsubscribe import (
    apply_unsubscribe,
    make_unsubscribe_token,
    make_unsubscribe_url,
    parse_unsubscribe_token,
)


class TestUnsubscribeToken:
    def test_round_trip(self):
        token = make_unsubscribe_token(42, "notify_reply")
        assert parse_unsubscribe_token(token) == (42, "notify_reply")

    def test_rejects_bad_input(self):
        token = make_unsubscribe_token(1, "notify_new_ticket")
        assert parse_unsubscribe_token(token[:-4] + "abcd") is None
        assert parse_unsubscribe_token("") is None
        assert parse_unsubscribe_token("1.notify_reply") is None
        with pytest.raises(ValueError):
            make_unsubscribe_token(1, "notify_assignment")

    def test_make_url(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("APP_BASE_URL", "https://pulsedeck.example")
        get_settings.cache_clear()
        try:
            url = make_unsubscribe_url(7, "notify_ticket_update")
            assert url.startswith("https://pulsedeck.example/email/unsubscribe?token=")
            assert parse_unsubscribe_token(url.rsplit("token=", 1)[-1]) == (
                7,
                "notify_ticket_update",
            )
        finally:
            get_settings.cache_clear()


class TestApplyUnsubscribe:
    def test_disables_pref(self, db_session, staff_user):
        staff_user.notify_reply = True
        db_session.commit()
        user = apply_unsubscribe(db_session, staff_user.id, "notify_reply")
        assert user is not None
        assert user.notify_reply is False

    def test_idempotent_and_missing(self, db_session, client_user):
        client_user.notify_ticket_update = False
        db_session.commit()
        user = apply_unsubscribe(db_session, client_user.id, "notify_ticket_update")
        assert user is not None
        assert user.notify_ticket_update is False
        assert apply_unsubscribe(db_session, 999_999, "notify_reply") is None
