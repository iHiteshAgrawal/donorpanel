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

1. Press **Run request** under *New request*. The **Agent pipeline** canvas lights up node by node as the run streams. It takes 30 to 70 seconds, almost all of it model latency, so the per-node progress is the point rather than a spinner.
2. A routine scheduled transfusion reads **Sent automatically**, with *Checks passed* listing what the gate verified: cohort covers the units, every donor inside their contact budget, nothing raised for review. Nobody was woken, which is the whole point.
3. Now send one the agent should not handle alone. Set **Source** to `emergency` and run again. The **Autonomy decision** card flips to *Needs coordinator review* and lists why under *Escalation reasons*, including any reason the verifier raised in its own words. Type a name and press **Approve**.
4. **Agent processes** on the right fills in as runs complete. A finding lands within seconds. A *Learned preference* needs a minute or more and at least two prior runs before a pattern exists to extract, then a refresh.
5. Run a third time and open the **Node output** tab on the `compose` node. Its brief now carries `prior_context`, which is what the agent remembered from earlier runs.
6. **Reset sandbox** in the header wipes your data and reseeds. Each browser profile gets its own sandbox, so two windows never see each other's requests.

The detail tabs under the graph are **Cohort** (who was matched and why), **Drafts** (the outreach messages), **Node output** (raw JSON per node) and **Map** (donor geography).

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

The verifier can also ask for a human without rejecting, by returning `needs_review` with a reason. That is the one place model judgment reaches the gate, and it arrives as a typed boolean persisted on the request, never as prose the gate has to interpret. What counts as required paperwork is a policy question, so deterministic code decides whether a prescription is needed and the agent only reads the answer.

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
- Aadhaar numbers are never stored. Verification discards them.

## Not built yet

Honest list, so nothing here reads as more finished than it is.

- **Nothing is actually sent.** The gate decides to dispatch and the drafts are real, but no email or Telegram message leaves the process. The channel interfaces exist; the delivery phase does not.
- **Sign-in has no UI.** Cognito is wired and validated server side, so `Authorization: Bearer <token>` works, but the SPA never sends one. Every visitor is an anonymous sandbox.
- **No CloudWatch alarms or memory log delivery.** The IAM policy grants it and the posture is decided, but the provisioning command is not written.
- **The scheduled graph is not built.** Forecasting the next transfusion date and keeping the registry warm are the predictive half of the thesis and remain a design.
- **`reset` cannot purge raw memory events** unless the IAM policy grants `bedrock-agentcore:ListSessions`. Without it the records are deleted and the underlying events survive; the call degrades quietly rather than failing the reset.

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
