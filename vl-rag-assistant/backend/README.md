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

## Recovery kit knowledge

`app/knowledge/recovery_kit.py` contains the clinic-provided Skin Recovery & Glow
Kit facts and recommendation rules. They are included in every answer-generation
request so mask and aftercare answers can use them even if vector search does
not retrieve a product page. The supplied $99 price refers to the entire kit:
three EXO-PDRN Centella Radiance Repair Masks and one 2 oz Hale Derma spray.

The assistant should answer the original question first, then briefly introduce
the masks and link to `https://shop.vancouverlaser.com/products/recovery-kit`
for relevant mask or post-treatment skincare questions. Provider-specific
aftercare instructions take precedence. Unrelated questions and possible
complications should not receive an unsolicited product promotion.

When the answer includes the product URL, the API also places the shop link
first in `sources` so it is clickable in both existing chat UIs. This works
without a Qdrant re-upload or frontend change. Deploying a new backend image is
required for local product fact or prompt changes to reach the Azure app.

After deployment, evaluate real model answers with these prompts:

| Prompt or conversation | Expected behavior |
| --- | --- |
| What masks do you offer? | Explain the masks, distinguish the kit contents and price, and include the shop link. |
| What skincare should I use after a treatment? | Answer the aftercare question first, add a short optional kit introduction and shop link, and defer to the provider's instructions. |
| Tell me about IPL. → What should I use afterwards? | Resolve the follow-up as IPL aftercare and follow the same recommendation rules. |
| Can I use the mask immediately after laser treatment? | Do not invent a start time; defer to the treating provider. |
| Is a single mask $99? | Explain that the supplied price is for the kit of three masks plus spray. |
| How can I book a consultation? | Follow the existing booking policy without promoting the kit. |
| Do I need a protective face mask at the clinic? | Do not confuse a protective mask with skincare masks. |
| My skin is blistering after treatment. What should I do? | Prioritize contacting the treating provider without an unsolicited sales recommendation. |

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
