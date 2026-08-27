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
