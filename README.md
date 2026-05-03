# Bolna AI Integration

This project receives Bolna webhook events and sends a Slack alert when a call reaches the `completed` status.

## Features

- FastAPI service with `GET /health` and `POST /webhooks/bolna`
- Logs the full raw webhook payload at `INFO` level on every request before processing
- Sends Slack alerts using an Incoming Webhook URL
- Includes optional fallback to the Bolna execution API when the webhook payload is missing `duration` or `transcript`
- Focused pytest coverage for completed and ignored events

## Requirements

- Python 3.11+
- A Slack Incoming Webhook URL
- A public webhook URL for Bolna, typically via `ngrok`
- Optional: a `BOLNA_API_KEY` if you want fallback execution fetches

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` with:

```env
SLACK_WEBHOOK_URL=...
BOLNA_API_KEY=...
PORT=8000
LOG_LEVEL=INFO
```

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

## Tests

```bash
pytest
```

## Expose the webhook

```bash
ngrok http 8000
```

Use the public URL in Bolna Analytics:

```text
https://your-ngrok-subdomain.ngrok.app/webhooks/bolna
```

Bolna sends POST requests to that endpoint as call status updates happen. The assignment only posts to Slack when `status == "completed"`.

## Sample request

```bash
curl -X POST http://localhost:8000/webhooks/bolna \
  -H "Content-Type: application/json" \
  -d '{
    "id": "call-123",
    "agent_id": "agent-456",
    "status": "completed",
    "transcript": "Candidate is interested in the role.",
    "telephony_data": {
      "duration": 87
    }
  }'
```

## Submission

Zip the project directory and email it to `ie+submissions@bolna.ai`.
