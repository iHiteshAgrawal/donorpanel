# DonorPanel

**Asha finds blood donors, so families don't have to.**

Patients with thalassemia, sickle cell disease and rare phenotypes need matched blood on a recurring basis, often every three weeks, for life. The pool of donors who can match them is systematically smaller than the population that needs them, because matching follows ancestry and donor registries do not mirror their patients. Registries are large but mostly unreachable, so the recruiting burden falls on families, permanently.

DonorPanel holds the donor network so no family has to browse it, and does the asking so no family has to.

The product is a Telegram agent. There is no dashboard to learn and no account to create: you message Asha and she does the rest.

## The three conversations

Asha works out which one you are from what you say.

| You | She |
| --- | --- |
| "My friend needs a transfusion in a week" | Gathers name, city, blood group, units and date, opens a request, searches the network, reports back |
| "I'd like to help" | Registers you: name, city, blood group, consent. Geocodes your city so distance ranking works |
| (answering her outreach) | Records your pledge or decline, tells you the hospital and date |

## How a request actually moves

A Strands `Graph` of ten nodes. Only two are agents. **Everything that decides routing is deterministic code**, which is the point.

```
intake -> verify -> adjudicate -+-> accept -> eligibility -> rank -> compose -> gate -> dispatch
                                 \-> close
```

- `verify` (agent) reads the request and the patient's history, returns a typed `Verdict` via structured output. It can also raise `needs_review` with a reason when a human should look.
- `adjudicate` (code) turns that verdict into a branch and fails closed. Routing never depends on model prose.
- `eligibility`, `rank` (code) apply the policy YAML: compatibility table, haversine distance, donation recency, contact budget.
- `compose` (agent) writes one outreach draft per language and channel group.
- `gate` (code) decides whether the run is routine enough to send without waking anyone.
- `dispatch` (code) actually sends, and records delivery per donor.

Graph edge conditions read JSON blocks out of node output, never free text.

### The autonomy gate

The gate is what makes this an agent rather than a workflow. A routine scheduled transfusion goes out on its own. It stops and asks a human when the request is an emergency, when the verifier raised something, when the matched cohort is too small for the units needed, when a donor is over their monthly contact budget, or when no drafts were produced.

Escalation reasons are written for a coordinator, then translated into plain language before they reach whoever asked.

### Policies, not code

`policies/*.yaml` carry the condition rules: transfusion interval, units per session, donation recency, cohort multiple, required paperwork and the autonomy thresholds. `thalassemia-india` and `sickle-cell-uk` are the same product with different numbers, which is the point.

### Memory

AgentCore Memory, keyed on the person, with two strategies:

```
/donorpanel/{actorId}/shared/preferences/          userPreference
/donorpanel/{actorId}/agents/{agentid}/findings/   semantic
```

Writes take two paths on purpose, because they have very different latencies:

| Path | API | Readable after |
| --- | --- | --- |
| Facts we already know exactly (cohort size, channels, gate decision) | `BatchCreateMemoryRecords` | **~1.5s** |
| Patterns worth mining from conversation | `CreateEvent` then async extraction | **~70s** |

Writing a record we already hold, instead of paying a model to re-derive it from a transcript, is also what the AWS cost guidance recommends. On the next run `compose` reads that memory back with a single prefix query and folds it into its brief.

### The forecast

A patient on a fixed cycle is predictable. Last transfusion plus the policy interval is the next one, so a daily tick opens requests before anyone asks. This is deterministic code, not an agent. Patients with a request still pointing at a future date are skipped, or a daily tick would open a duplicate every day.

## Running it locally

You need Python 3.10+, Node 18+, and AWS credentials for `ap-southeast-2`.

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env          # then fill in the values below
cd web && npm install && npm run build && cd ..
uv run uvicorn donorpanel.entrypoints.devserver:app --port 8077
```

Open **http://127.0.0.1:8077** for the landing page. The dev server also runs the Telegram poller, so messaging your bot works while it is up.

Provision the AWS-side resources once:

```bash
uv run donorpanel init          # S3 bucket
uv run donorpanel memory-init   # AgentCore Memory, ~3 min, prints the id for .env
uv run donorpanel status        # confirms what is wired up
```

### `.env`

| Key | Needed for | Notes |
| --- | --- | --- |
| `AWS_REGION` | everything | `ap-southeast-2`. The account's SCP blocks S3 in `us-east-1`. |
| `BEDROCK_MODEL_ID` | the agents | `apac.amazon.nova-pro-v1:0`. |
| `DONORPANEL_BUCKET` | storage | Unset falls back to `data/local` on disk. |
| `AGENTCORE_MEMORY_ID` | memory | Unset disables memory cleanly; everything else still works. |
| `TELEGRAM_BOT_TOKEN` | the product | From `@BotFather`. |
| `TELEGRAM_BOT_USERNAME` | the landing page CTA | Without the `@`. |
| `TELEGRAM_DEMO_CHAT_ID` | the demo pool | Seeded donors route here, so outreach reaches the operator rather than strangers. |
| `TELEGRAM_ALLOWED_CHAT_IDS` | access control | **Pinned to one chat id means nobody else can reach the bot.** Clear it before sharing. |
| `TELEGRAM_WEBHOOK_SECRET` | deployment | Proves an inbound webhook came from Telegram. |
| `SES_SENDER_EMAIL`, `SES_DEMO_EMAIL` | email outreach | Both the same verified address: SES sandbox only sends to verified recipients. |

### Trying it

1. Message your bot. Ask for blood for someone, or offer to donate.
2. A request that clears the gate sends real Telegram messages, one per matched donor, each personalised by name and language.
3. Reply as a donor. Asha records the pledge and the request tracks toward fulfilment.
4. `uv run python -m donorpanel.services.forecast` shows what a scheduled tick would open today.

## Deployment

Serverless, in `ap-southeast-2`:

```
Telegram ──webhook──► API Gateway ──► Lambda ──► AgentCore Runtime (Asha)
                                        └─────► itself, async (the request graph)
EventBridge Scheduler ──daily──────► Lambda (forecast)
CloudFront ──► S3 (landing page)
```

**Asha runs on AgentCore Runtime** because she is one agent, one request, one response, with a dedicated session per person. **The request graph runs in Lambda** because it is the opposite shape: ten nodes, thirty to seventy seconds, and nobody waiting. Using each service for what it is actually for.

The webhook replaces a polling loop. Polling needs one process running forever, which is the opposite of what serverless is for; `poll()` survives only for local development where there is no public endpoint to point Telegram at.

If AgentCore Runtime is unreachable, the Lambda answers in process with the identical code. A Runtime outage costs the architecture, not the demo.

## Security and privacy, stated honestly

- **Agent output never reaches logs.** `callback_handler=None` on every agent, because Strands prints reasoning to stdout by default and on Lambda stdout is CloudWatch. That would put donor names, dates of birth and blood groups into plaintext logs. A CloudWatch Logs data protection policy is the backstop.
- **The bot token never reaches logs either.** httpx logs full request URLs at INFO and a Telegram URL carries the token in its path, so httpx is pinned to WARNING.
- **Identity is federated from Telegram.** `from.id` identifies the speaker, `chat.id` is only where to reply. In a group those differ, and keying on the chat would give every member one shared identity and one shared memory.
- **There is no authorization model.** Anyone who can reach the bot can open a request and cause real outreach. The webhook secret proves Telegram sent the message; it proves nothing about the human behind it. AgentCore Policy with Cedar rules at a Gateway is the right answer and is not built.
- **Namespaces are organization, not access control.** The real boundary AWS documents is an IAM condition on `bedrock-agentcore:actorId` bound to a per-user principal. One process holding one credential cannot have that.
- Aadhaar numbers are never stored. Verification discards them.

## Not built yet

- **No proof of personhood.** A Telegram account is free. For a system that dispatches people to hospitals, that is the gap.
- **No cross-channel identity.** The same human on email and Telegram are two unrelated identities.
- **Email is outbound only.** Receiving mail through SES needs a verified domain with MX records, so there is no email equivalent of the Telegram conversation.
- **No evaluation harness.** Agent behaviour is covered by unit tests and stubs, not by scored evaluation runs.
- **Cognito is gone.** It existed for a coordinator console that no longer exists.

## Development

```bash
uv run pytest -q
uv run ruff check .
```

The suite avoids AWS: storage tests use moto or a temp directory, agents are stubbed, and channel tests fake the Telegram transport. Tests that call Bedrock are skipped unless `DONORPANEL_LIVE=1`.

## Layout

| Path | Purpose |
| --- | --- |
| `entrypoints/` | How the outside gets in: `cli`, `lambda_fn`, `runtime`, `poller`, `devserver` |
| `services/` | Application logic: `chat`, `outreach`, `forecast`, `pool`, `seed` |
| `graph/` | The Strands graph: `flow`, `hooks`, and `nodes/` one class each |
| `agents/` | The three model-backed agents: `assistant`, `composer`, `verifier` |
| `tools/` | What Asha can actually do, bound per conversation |
| `domain/` | Models and the matching rules. Depends on nothing else |
| `adapters/` | How we reach the outside: `channels/`, `storage/`, `memory`, `geo` |
| `policies/` | Condition rules as YAML, not code |
| `web/` | The landing page: Vite, React, Tailwind v4 |

Dependencies point inward. `entrypoints` and `adapters` know about `domain`; `domain` knows about neither.
