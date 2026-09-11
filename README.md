# DonorPanel

Multi-agent donor coordination for patients who need matched blood repeatedly, for life.

Patients with thalassemia, sickle cell disease and rare phenotypes need matched blood on a recurring basis. The pool of donors who can match them is systematically smaller than the population that needs them, because matching follows ancestry and donor registries do not mirror their patients. Registries are large but mostly unreachable, so the recruiting burden falls on families, permanently.

DonorPanel holds the donor network so no family has to browse it, and does the asking so no family has to.

## Running the full stack

You need Python 3.10+, Node 18+, and AWS credentials for `ap-southeast-2`.

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env          # then fill in the values below
cd web && npm install && npm run build && cd ..
uv run uvicorn donorpanel.api.app:app --port 8077
```

Open **http://127.0.0.1:8077**. FastAPI serves the built SPA from `web/dist`, so this one process is the whole app.

### Working on the frontend

For hot reload, run the API and Vite side by side. Vite proxies `/api` to port 8077, so **the backend must be on 8077** for this to work.

```bash
uv run uvicorn donorpanel.api.app:app --port 8077   # terminal 1
cd web && npm run dev                               # terminal 2, opens :5173
```

### `.env`

| Key | Needed for | Notes |
| --- | --- | --- |
| `AWS_REGION` | everything | `ap-southeast-2`. The account's SCP blocks S3 and EventBridge in `us-east-1`. |
| `AWS_PROFILE` | everything | Or use ambient credentials. |
| `BEDROCK_MODEL_ID` | the two agents | `apac.amazon.nova-pro-v1:0`. |
| `DONORPANEL_BUCKET` | storage | Unset falls back to `data/local` on disk, which is enough to click around. |
| `AGENTCORE_MEMORY_ID` | the memory panel | Unset disables memory cleanly; everything else still works. |
| `COGNITO_POOL_ID`, `COGNITO_CLIENT_ID` | signed-in coordinators | Unset means every visitor is an anonymous sandbox. |

Provision the AWS-side resources once:

```bash
uv run donorpanel init          # S3 bucket
uv run donorpanel memory-init   # AgentCore Memory, ~3 min, prints the id for .env
uv run donorpanel status        # confirms what is wired up
```

### What to click

1. **Run request graph** in the left panel. The centre canvas lights up node by node as the graph streams; the whole run takes 30 to 70 seconds, mostly model latency.
2. The first run for a patient **escalates** and lands in `awaiting_approval`, because the autonomy gate treats a first-ever request as something a human should see. Approve it under **Drafts**.
3. Run it again with a later date. This one **auto-sends**: routine repeat, cohort covers the units, every donor inside their contact budget. Click the `gate` node to see which checks passed.
4. **Agent memory** (right column) fills in as runs complete. See below for what to expect.
5. **Reset sandbox** wipes your data and reseeds. Each browser gets its own sandbox, so two browser profiles never see each other's requests.

## How it works

A Strands `Graph` of nine nodes. Only two are agents; everything that decides routing is deterministic code, which is deliberate.

```
intake -> verify -> adjudicate -+-> accept -> eligibility -> rank -> compose -> gate
                                 \-> close
```

- `verify` (agent) reads the request and the patient's transfusion history and returns a typed `Verdict` via structured output.
- `adjudicate` (code) reads that verdict and fails closed. Routing never depends on model prose.
- `eligibility`, `rank` (code) apply the policy YAML: compatibility table, haversine distance, donation recency, contact budget.
- `compose` (agent) writes one outreach draft per language and channel group.
- `gate` (code) decides whether the run is routine enough to send without waking anyone.

Conditions on the graph edges read JSON blocks out of node output, never free text.

### Policies, not code

`src/donorpanel/policies/*.yaml` carry the condition rules: transfusion interval, units per session, donation recency, cohort multiple, and the autonomy thresholds. `thalassemia-india` and `sickle-cell-uk` are the same product with different numbers, which is the point.

### Memory

AgentCore Memory, keyed on the actor, with two strategies:

```
/donorpanel/{actorId}/shared/preferences/          userPreference
/donorpanel/{actorId}/agents/{agentid}/findings/   semantic
```

Writes take two paths on purpose, because they have very different latencies:

| Path | API | Readable after |
| --- | --- | --- |
| Facts we already know exactly (cohort size, channels, gate decision) | `BatchCreateMemoryRecords` | **~1.5s** |
| Patterns worth mining from the conversation | `CreateEvent` then async extraction | **~70s or longer** |

So a **finding** appears in the panel within seconds of a run finishing, and a **preference** appears a minute or more later, when you hit refresh. Writing a record we already hold directly, instead of paying a model to re-derive it from a transcript, is also what the AWS cost guidance recommends.

On the next run, `compose` reads that memory back with a single prefix query and folds it into its brief as `prior_context` — click the `compose` node after a second run to see it.

`verify` writes but never reads. Feeding retrieved prose into the node that produces the routing verdict would trade away the determinism the rest of the design is built on.

### Security posture, stated honestly

- **Namespaces are organization, not access control.** The real boundary AWS documents is an IAM condition on `bedrock-agentcore:actorId` bound to a per-user principal. One FastAPI process holding one credential for every visitor cannot have that. Actor scoping here is enforced by the application, not by IAM.
- **Anonymous actor ids come from a client-supplied header.** `X-DonorPanel-Session` is a UUID the browser generates and persists. Good enough to give each visitor a private sandbox; not an authentication boundary. Under Cognito the actor is the token's `sub` claim and this caveat does not apply.
- **Alarms have no SNS action.** They report state in the CloudWatch console and page nobody. Deliberate for a demo account.
- Aadhaar numbers are never stored. Verification discards them.

## Development

```bash
uv run pytest -q
uv run ruff check .
```

The suite avoids AWS: storage tests use moto or a temp directory, and both agents are stubbed. Tests that call Bedrock are skipped unless `DONORPANEL_LIVE=1`.

## Layout

| Path | Purpose |
| --- | --- |
| `src/donorpanel/graphs` | The Strands graph: nodes, edges, conditions |
| `src/donorpanel/nodes` | Node implementations, one class each |
| `src/donorpanel/agents` | The two model-backed agents |
| `src/donorpanel/policies` | Condition rules as YAML, not code |
| `src/donorpanel/channels` | Outreach transports behind one interface |
| `src/donorpanel/memory.py` | AgentCore Memory client |
| `src/donorpanel/hooks.py` | Graph hook that writes a finished run to memory |
| `src/donorpanel/api` | FastAPI, SSE streaming, serves the SPA |
| `web/` | Vite, React, Tailwind v4, React Flow, Leaflet |
