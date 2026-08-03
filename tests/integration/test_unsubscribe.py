from app.utils.unsubscribe import make_unsubscribe_token


class TestUnsubscribeRoutes:
    def test_get_shows_confirmation_without_changing_preference(
        self, client, db_session, client_user
    ):
        client_user.notify_reply = True
        db_session.commit()
        token = make_unsubscribe_token(client_user.id, "notify_reply")

        response = client.get("/email/unsubscribe", params={"token": token})

        db_session.refresh(client_user)
        assert response.status_code == 200
        assert 'name="token"' in response.text
        assert client_user.notify_reply is True

    def test_form_post_unsubscribes_and_returns_html(
        self, client, db_session, client_user
    ):
        client_user.notify_reply = True
        db_session.commit()
        token = make_unsubscribe_token(client_user.id, "notify_reply")

        response = client.post("/email/unsubscribe", data={"token": token})

        db_session.refresh(client_user)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert client_user.notify_reply is False

    def test_one_click_post_unsubscribes_and_returns_ok(
        self, client, db_session, client_user
    ):
        client_user.notify_ticket_update = True
        db_session.commit()
        token = make_unsubscribe_token(client_user.id, "notify_ticket_update")

        response = client.post(
            "/email/unsubscribe",
            params={"token": token},
            data={"List-Unsubscribe": "One-Click"},
        )

        db_session.refresh(client_user)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == "OK"
        assert client_user.notify_ticket_update is False
