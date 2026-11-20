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

## Manual knowledge library

Set `KNOWLEDGE_ADMIN_TOKEN` to a strong random secret in the backend environment
(use the Azure Container App's secret settings when enabling it there). Restart
the API, open `/admin/knowledge` on the API host, and enter the token. For local
testing, point the backend at a test Qdrant collection before using the buttons.
The admin endpoints are disabled when the token is unset.

The list can be previewed without Qdrant payload indexes. Before deploying this
version to Qdrant Cloud, or testing writes against a strict-mode collection,
check and initialize its indexes from the backend directory:

```sh
.venv/bin/python -m scripts.ensure_knowledge_indexes
.venv/bin/python -m scripts.ensure_knowledge_indexes --apply
```

The first command only reports missing or incompatible indexes. Use the second
when the configured target collection is the one you intend to change. It
creates missing field indexes without altering knowledge points or generating
embeddings. The API checks the indexes before permitting edits in strict mode.

- **Add webpage** indexes one public Vancouver Laser URL. To refresh existing
  pages, select their rows and click **Update webpages**. A row tied to a
  WordPress record refreshes that record, even if another page uses the same URL.
- **Upload file** accepts PDF with selectable text, DOCX, UTF-8 TXT, or Markdown
  (up to 10 MB). Use **Replace** to update an existing file's knowledge under
  the same record. Only upload material suitable for the public assistant. The
  collection stores extracted text and vectors, and the original stays with you.
- **Remove selected** takes those sources out of search and cleans up their
  stored chunks. If cleanup fails, the source is already out of search. Select
  the row marked **Cleanup pending** and run removal again.

Each update generates fresh embeddings for the entire selected source, using the
configured OpenAI API. A complete replacement is written to Qdrant before the
assistant starts using it. The library uses the existing collection and lists
its previously indexed website and manual records. No schedule or deployment is
needed for individual changes.

Run this admin feature with one backend writer (the default single Uvicorn
worker and one Azure replica). Use the library for changes to its collection.
The old bulk uploader is intended for separately managed collections. Code-based
booking and product guidance is managed separately in `app/knowledge/`.

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

## Campaign offer coverage

When vector search finds an 11/11 page, retrieval also reads published/manual
sibling chunks from that document (up to 16 chunks per page, for at most two
11/11 documents). Identification uses the `pages-11-11-event` document ID or an
`11-11` / `11/11` marker in the title, never the homepage URL alone. Other
campaigns and ordinary pages keep their original retrieval behavior.
This keeps treatment lists and discount
eligibility together even when only one part of the page ranks in the top hits.
If that additional read fails, the original search results remain available.

`MAX_CONTEXT_CHARS_PER_CHUNK` keeps its original default of `1200`. Only 11/11
chunks use a minimum allowance of 4000 characters, enough to retain the four
existing 11/11 chunks intact. This changes the text passed to the model, not
the 500-token ingestion chunk size, and requires no re-embedding. The answer
instructions request all treatments found in campaign context and distinguish
public, member/pass-holder, and Daily Drop rates. Campaign details continue to
come from indexed website content, so changes require refreshing knowledge;
these backend changes require deployment to affect the hosted assistant.

Run backend regression checks locally without calling external services:

```sh
cd vl-rag-assistant/backend
OPENAI_API_KEY=test QDRANT_URL=http://localhost:6333 QDRANT_API_KEY=test \
QDRANT_COLLECTION_NAME=test .venv/bin/python -m unittest discover -s tests -v
```

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
