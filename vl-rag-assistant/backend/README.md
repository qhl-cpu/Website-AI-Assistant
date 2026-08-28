```sh
# Active virtual environment:
source .venv/bin/activate
```

```sh
# Run App:
uvicorn app.main:app --reload
```

The app is in http://127.0.0.1:8000
doc: http://127.0.0.1:8000/docs

## Conversation context

The `/chat` endpoint accepts completed conversation turns in `history`. Send the
current question separately in `message`:

```json
{
  "message": "How much does that treatment cost?",
  "session_id": "vl-session-123",
  "history": [
    {"role": "user", "content": "Tell me about Sofwave."},
    {"role": "assistant", "content": "Sofwave is a non-invasive treatment..."}
  ]
}
```

Up to 60 `user` or `assistant` messages (30 complete exchanges) are accepted,
with a 60,000-character total limit. The backend rewrites follow-up questions
into standalone retrieval queries using the active session, then uses the full
bounded history for answer generation. Clinic facts remain grounded in the
booking policy and retrieved website content.

The website widget stores this bounded conversation state in browser storage so
open tabs share the same active session. Five minutes without opening or using
the assistant expires and removes that state. On the next interaction, the
widget explicitly tells the user that a new conversation has started.

## Chat rate limits

The `/chat` endpoint applies sliding-window limits before retrieval or model
calls. The default limits are intentionally generous:

| Scope | Requests | Window |
| --- | ---: | ---: |
| Visitor burst | 5 | 30 seconds |
| Visitor sustained | 20 | 10 minutes |
| Visitor daily | 100 | 24 hours |
| IP sustained | 300 | 10 minutes |
| IP daily | 2,000 | 24 hours |

Rate-limited requests return HTTP `429`, a `Retry-After` header, and a JSON
`retry_after_seconds` value. Both bundled chat interfaces preserve the unsent
question and show a countdown before enabling Send again.

Every limit can be changed through environment variables:

```dotenv
CHAT_RATE_LIMIT_ENABLED=true
CHAT_VISITOR_BURST_REQUESTS=5
CHAT_VISITOR_BURST_WINDOW_SECONDS=30
CHAT_VISITOR_SUSTAINED_REQUESTS=20
CHAT_VISITOR_SUSTAINED_WINDOW_SECONDS=600
CHAT_VISITOR_DAILY_REQUESTS=100
CHAT_VISITOR_DAILY_WINDOW_SECONDS=86400
CHAT_IP_SUSTAINED_REQUESTS=300
CHAT_IP_SUSTAINED_WINDOW_SECONDS=600
CHAT_IP_DAILY_REQUESTS=2000
CHAT_IP_DAILY_WINDOW_SECONDS=86400
```

The current limiter is stored in process memory, so counters reset when the API
restarts and are not shared by multiple replicas. Use a shared Redis-compatible
backend before scaling the API beyond one active replica. In production, the
trusted ingress address is read from `X-Forwarded-For`; set
`TRUST_X_FORWARDED_FOR=false` if the API is exposed without a proxy that
sanitizes that header.
