import os

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ignores_non_completed_event(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/demo")

    called = {"value": False}

    def fake_post_to_slack(*args, **kwargs):
        called["value"] = True

    monkeypatch.setattr("app.main.post_to_slack", fake_post_to_slack)

    response = client.post(
        "/webhooks/bolna",
        json={"id": "call-1", "agent_id": "agent-1", "status": "queued"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert called["value"] is False


def test_completed_event_posts_to_slack(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/demo")

    captured = {}

    def fake_post_to_slack(webhook_url, message):
        captured["webhook_url"] = webhook_url
        captured["message"] = message

    monkeypatch.setattr("app.main.post_to_slack", fake_post_to_slack)

    response = client.post(
        "/webhooks/bolna",
        json={
            "id": "call-2",
            "agent_id": "agent-2",
            "status": "completed",
            "transcript": "Hello from Bolna",
            "telephony_data": {"duration": 42},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert captured["webhook_url"] == os.environ["SLACK_WEBHOOK_URL"]
    assert captured["message"]["text"] == "Bolna call completed: call-2"
    assert "Hello from Bolna" in str(captured["message"]["blocks"])


def test_completed_event_uses_fallback_execution(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/demo")
    monkeypatch.setenv("BOLNA_API_KEY", "demo-key")

    captured = {}

    def fake_fetch_execution(execution_id, api_key):
        assert execution_id == "call-3"
        assert api_key == "demo-key"
        return {
            "id": "call-3",
            "agent_id": "agent-3",
            "status": "completed",
            "transcript": "Fetched transcript",
            "telephony_data": {"duration": 55},
        }

    def fake_post_to_slack(webhook_url, message):
        captured["webhook_url"] = webhook_url
        captured["message"] = message

    monkeypatch.setattr("app.main.fetch_execution", fake_fetch_execution)
    monkeypatch.setattr("app.main.post_to_slack", fake_post_to_slack)

    response = client.post(
        "/webhooks/bolna",
        json={
            "id": "call-3",
            "agent_id": "agent-3",
            "status": "completed",
            "transcript": "",
            "telephony_data": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert captured["webhook_url"] == os.environ["SLACK_WEBHOOK_URL"]
    assert "Fetched transcript" in str(captured["message"]["blocks"])
    assert "55" in str(captured["message"]["blocks"])
