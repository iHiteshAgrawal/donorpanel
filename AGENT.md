# AGENT.md

Context for any AI agent working in this repo. Read this before writing code.

## What we are building

DonorPanel is a multi-agent system that coordinates blood donors for patients who need matched blood repeatedly, for life.

The name is provisional. Renaming means changing `src/donorpanel/`, the `[project].name` and script entry in `pyproject.toml`, and the `DONORPANEL_*` environment variables.

### Problem statement

Patients with transfusion-dependent conditions (thalassemia, sickle cell disease, rare phenotypes) need matched blood repeatedly, for life. The pool of donors who can match them is systematically smaller than the population that needs them, because matching follows ancestry and donor registries do not mirror their patients. Registries are large but mostly dead: only 55 to 60 percent of registered US marrow donors are reachable and available when finally called, and attrition runs 60 percent among minority donors against 40 percent among white donors. NHSBT supplies 3,600 units of Ro blood a month against a need of 7,400. India has 100,000 to 150,000 children with thalassemia major, whose families arrange donors themselves, every two weeks, for life.

So the recruiting burden falls on patients and families, permanently, and in crisis. We build the agent that carries that burden instead.

### The core insight

The problem was never the database. Registries already exist (eRaktKosh, NMDP, Friends2Support, hundreds of volunteer WhatsApp groups) and word of mouth persists anyway. The bottleneck is coordination labour landing on whoever is least able to carry it. The system holds the network so no user has to browse it, and does the asking so no family has to.

## Scope

In scope:

- **Thalassemia scheduling** as the primary flow. Recurring transfusions every 2 to 4 weeks, so the system cultivates a donor panel ahead of time rather than broadcasting an SOS.
- **Emergency requests** as the interrupt path, not the main loop.
- **Platelets** as a third resource type. Five day shelf life, so always a live donor problem.
- **Registry hygiene** as a continuous background job. Verifying who is actually reachable, eligible and willing before anyone needs them.
- **Request verification.** Fraud and duplicate detection, because trust is what kills these systems.
- **Cohort ranking.** Who to contact and in what order, instead of blasting everyone.
- **Replacement donation credit tracking.** The Indian obligation where a family must replace units used.

Out of scope, deliberately:

- Generalizing to non-medical donations (money, clothes, food). It removes the constraints that make matching a real reasoning problem.
- Institution-side inventory (hospital beds, antivenom stock, dialysis slots). That data lives inside hospital systems we cannot access, and every project in that category dies on data access.
- Medical eligibility determinations. The system pre-filters on self-reported basics; the blood bank screens.
- Autonomous action. Hard human gate, nothing executes unattended.
- Claiming to actually serve UK or US patients. International cases are demonstrated as configuration only.

## Matching policies

Condition-specific rules are configuration, not code paths. Policies live in `src/donorpanel/policies/*.yaml` and carry cadence, antigen requirements, donor eligibility windows and outreach strategy. Supporting sickle cell is a new YAML file, never a new subsystem.

This is load-bearing rather than a nice-to-have, because the problem statement is global. Never hardcode a region's rules into agent logic.

Existing policies:

- `thalassemia-india` The primary demo case.
- `sickle-cell-uk` NHSBT Ro requirements. Proves the policy layer generalizes.

## Channels

Multi-channel, not voice-only. Telegram and email first because they are cheapest to stand up. Voice, WhatsApp and X come later behind the same interface.

Every channel implements `Channel` in `src/donorpanel/channels/base.py` with `send`, `poll` and `available`. Agents must never know which transport they are on. Add a channel by implementing the interface and registering it in `channels/__init__.py:registry`.

`ConsoleChannel` always reports available and is what tests and local runs use.

## Architecture status

**Undecided. Do not commit to a graph shape without the user.**

The agent roster and orchestration are explicitly pending. The user wants to choose these together using the vocabulary from https://www.srajdev.com/p/understanding-agentic-ai-architecture (triggers, planning agent, agents with prompts and tools and environments, memory, guardrails, observability).

Phase 1 Intake is built. `graphs/intake.py` wires it:

```
intake ──▶ verify ──▶ adjudicate ──┬─ verified ─▶ accept ──▶ eligibility ──▶ rank
                                   └─ rejected ─▶ close    status REJECTED
```

Phase 2 Match is built and is **entirely deterministic**. Blood matching is rules and arithmetic, so no model call belongs in it. `EligibilityResolver` expands the recipient's blood group through the red cell compatibility table, pulls each compatible pool, and filters on the policy's `donor_eligibility` plus consent, reachability and antigen requirements, emitting every exclusion with its reason. `CohortRanker` scores the survivors on rest since last donation, contact fatigue, repeat-donor preference and haversine proximity, writes ranked `Contact` rows, and moves the request to MATCHING.

`domain/matching.py` holds the compatibility table, distance, eligibility rules and scoring as pure functions, so they are testable without any graph or storage.

`CohortRanker` reads the eligible list out of the upstream node's output rather than `invocation_state`, because relying on that dict being shared by reference across nodes is not something the Python SDK documents.

`Adjudicate` exists because a conditional edge must never depend on a model emitting exact JSON. It parses the verdict out of the verifier's prose, and when there is no usable decision it **fails closed**: rejected, `decided_by: fallback`, held for human review. This is not theoretical, it happened on the first live run. Nova reasoned correctly and simply did not print the JSON, so no branch fired and the graph halted at `verify`.

`IntakeNormalizer` is a `DeterministicNode` that resolves the patient, loads the matching policy, computes the fact sheet and persists a DRAFT request. It makes no model call. `RequestVerifier` is an `Agent` that only reasons about the numbers it is handed, and has one tool, `request_history`. Conditional edges read the verdict JSON out of the verify node's output.

`DeterministicNode` in `nodes/base.py` wraps deterministic work into `MultiAgentBase`, so the same subclass can stand in for an agent anywhere in a graph. Tests exploit that: a `StubVerifier` swaps into the verify slot to exercise both branches with no model call.

Two things that will bite anyone extending this. A node receives its input as a **list of ContentBlock dicts**, not a string, so use `task_text()` rather than `str()`, otherwise the repr escapes newlines and JSON parsing fails. And a node's input carries **every upstream node's output concatenated**, so `find_block(text, key)` scans for balanced objects and returns the last one carrying that key rather than naively slicing brace to brace.

Build order agreed with the user: state and memory first (done), then the five request phases left to right, then the scheduled graph, then safety and observability. The FastAPI platform edge is deliberately skipped for the demo.

Two constraints already agreed for whenever that decision lands:

- All matching arithmetic belongs in deterministic custom nodes (`strands.multiagent.base.MultiAgentBase` subclasses with no model call). Agents reason about numbers they are handed; they never compute them.
- Fan-out must be genuine specialisation by function, not one agent per condition or per channel.

## Conventions

- **Never use em dashes.** Anywhere. Not in code, comments, docs, commits or chat. Use commas, colons, parentheses or two sentences.
- **No comments or docstrings** unless explaining a genuine catch: a non-obvious workaround, an ordering constraint, a bug being worked around. No module headers, no restating the next line.
  - One exception: Strands `@tool` functions build their tool spec from the docstring. The first paragraph becomes the tool description and the `Args:` section describes parameters. Those docstrings are functional and required.
- **Clean folder names.** Short, lowercase, readable. No abbreviations, no underscore soup.
- **Use the Strands MCP server** (`search_docs`, then `fetch_doc`) for any Strands API question. Never answer from memory; the SDK moves fast.

## Stack

Python 3.10 or newer, currently running 3.13.

- `strands-agents` 1.55.0, `strands-agents-tools` 0.8.8
- `boto3` for AWS, `httpx` for Telegram, `pyyaml` for policies
- `uv` for environment and dependency management

## AWS account

Account 292368431051, region **ap-southeast-2 (Sydney)**. Two CLI profiles work: `default` (IAM user `donorpanel-dev`, static keys) and `donorpanel` (browser sign-in, 12 hour credentials, renew with `aws login --profile donorpanel`).

A service control policy from the org management account (042269275956) applies. It is **region scoped, not service scoped**. In `us-east-1` it denies DynamoDB, S3 `CreateBucket` and EventBridge `PutRule`. In `ap-southeast-2` none of that is denied. Do not move the region back without re-testing.

The bucket `donorpanel-292368431051` exists in ap-southeast-2 and holds live seeded data.

The AWS Agent Toolkit is installed. Its own commands (`aws configure agent-toolkit`, `aws agent-toolkit ...`) must stay on `us-east-1`, because that service runs nowhere else. Everything the project does runs in ap-southeast-2.

## Bedrock

Model ids are region scoped. In ap-southeast-2 the newer Anthropic models use the `au.` prefix, older ones use `apac.`.

Anthropic models are currently blocked account wide with `ResourceNotFoundException: Model use case details have not been submitted`, for both `Converse` and `ConverseStream`. The account had a brief grace window that has closed. Until the use case form is approved, use `apac.amazon.nova-pro-v1:0`, which works through the full agent loop. Switching back is one line in `.env`.

## Layout

```
src/donorpanel/
  agents/      empty, pending architecture decision
  nodes/       empty, deterministic custom graph nodes
  tools/       empty, @tool functions
  channels/    base interface plus console, telegram, email
  domain/      dataclass models and enums, no AWS imports
  policies/    condition YAML plus loader
  storage/     single table schema, domain repository, session repository
  config.py    environment configuration
  main.py      CLI entrypoint
tests/
```

## Storage

Two interchangeable backends behind one interface (`put`, `get`, `touch`, `delete`, `keys`). `FileStore` writes JSON under `data/local`. `ObjectStore` writes the same JSON to S3. `storage.store()` picks one: S3 when `DONORPANEL_BUCKET` is set, local otherwise. `PanelRepository` never knows which.

Sessions follow the same rule through `storage.session_manager()`, returning the SDK's `S3SessionManager` or `FileSessionManager`. Both implement `create_multi_agent`, `read_multi_agent` and `update_multi_agent`, so an entire graph can checkpoint and resume, not just a single agent.

Key layout, identical in both backends:

```
donors/<donor id>.json
pool/<region>/<blood group>/<donor id>      empty marker
patients/<patient id>.json
credits/<patient id>.json
requests/<request id>.json
contacts/<request id>/<donor id>.json
sessions/...                                 owned by the session manager
```

`list_pool` lists the `pool/` prefix and then reads each donor, which is how the region plus blood group query stays cheap without a secondary index. `put_donor` deletes the stale marker when a donor changes region or blood group, otherwise they would appear in two pools.

DynamoDB was the original design and was cut: the AWS account in use has a service control policy that denies DynamoDB, S3 `CreateBucket` and EventBridge `PutRule` outright. Bedrock and CloudWatch Logs work. Do not reintroduce DynamoDB without checking that policy.

Tests use `moto` for the S3 path and `tmp_path` for the local path, so nothing needs credentials.

## Conventions

- **Never use em dashes.** Anywhere. Not in code, comments, docs, commits or chat. Use commas, colons, parentheses or two sentences.
- **No comments or docstrings** unless explaining a genuine catch: a non-obvious workaround, an ordering constraint, a bug being worked around. No module headers, no restating the next line.
  - One exception: Strands `@tool` functions build their tool spec from the docstring. The first paragraph becomes the tool description and the `Args:` section describes parameters. Those docstrings are functional and required.
- **Clean folder names.** Short, lowercase, readable. No abbreviations, no underscore soup.
- **Use the Strands MCP server** (`search_docs`, then `fetch_doc`) for any Strands API question. Never answer from memory; the SDK moves fast.

## Stack

Python 3.10 or newer, currently running 3.13.

- `strands-agents` 1.55.0, `strands-agents-tools` 0.8.8
- `boto3` for AWS, `httpx` for Telegram, `pyyaml` for policies
- `uv` for environment and dependency management

Planned AWS services: Bedrock for reasoning, DynamoDB behind a custom `SessionRepository` for network state and checkpointing, EventBridge and Lambda for transfusion schedules and registry sweeps, Bedrock Knowledge Base for eligibility rules, Guardrails to block medical determinations, S3 with KMS for records, AgentCore Runtime for session isolation. Amazon Connect, Polly and Transcribe only once voice is added.

Note: Strands ships `FileSessionManager`, `S3SessionManager`, `SnapshotSessionManager` and `RepositorySessionManager`. There is no built-in DynamoDB session manager, so DynamoDB persistence means implementing a `SessionRepository` and passing it to `RepositorySessionManager`.

`BEDROCK_MODEL_ID` is unset by default and the SDK default is used. Verify a real inference profile id with `aws bedrock list-inference-profiles` before pinning one.

## Layout

```
src/donorpanel/
  agents/      empty, pending architecture decision
  nodes/       empty, deterministic custom graph nodes
  tools/       empty, @tool functions
  channels/    base interface plus console, telegram, email
  domain/      dataclass models and enums, no AWS imports
  policies/    condition YAML plus loader
  storage/     single table schema, domain repository, session repository
  config.py    environment configuration
  main.py      CLI entrypoint
tests/
```

## Storage

One DynamoDB table, `donorpanel` by default, with a `pool-index` GSI.

| Entity | pk | sk | gsi1pk | gsi1sk |
| --- | --- | --- | --- | --- |
| Donor | `DONOR#<id>` | `PROFILE` | `POOL#<region>#<group>` | `DONOR#<id>` |
| Patient | `PATIENT#<id>` | `PROFILE` | | |
| Credit | `PATIENT#<id>` | `CREDIT` | | |
| Request | `REQUEST#<id>` | `PROFILE` | | |
| Contact | `REQUEST#<id>` | `CONTACT#<donor id>` | | |
| Session | `SESSION#<id>` | `SESSION` | | |
| SessionAgent | `SESSION#<id>` | `AGENT#<agent id>` | | |
| SessionMessage | `SESSION#<id>` | `MSG#<agent id>#<id padded to 12>` | | |
| MultiAgent | `SESSION#<id>` | `MULTIAGENT#<id>` | | |

Message ids are zero padded because the sort key is lexical. Without padding, message 10 sorts before message 9.

`PanelRepository` handles domain entities. `DynamoDBSessionRepository` implements the Strands `SessionRepository` ABC and is passed to `RepositorySessionManager`. It also implements the optional `create_multi_agent`, `read_multi_agent` and `update_multi_agent` methods, which the base class leaves as `NotImplementedError`, so a whole graph can checkpoint and resume.

Floats are rejected by DynamoDB, so `table.encode` converts them to `Decimal` on the way in and `table.decode` converts back on the way out.

Domain dataclasses coerce their enum fields in `__post_init__`. Without it, anything read back from storage carries raw strings, and because these are `str` enums every comparison still passes, so the inconsistency stays invisible until something touches `.value`.

Tests run against `moto`, so no AWS account or Docker is needed. Set `DYNAMODB_ENDPOINT` to point at DynamoDB Local instead.

## Commands

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/donorpanel status
.venv/bin/donorpanel init
.venv/bin/donorpanel reset
.venv/bin/donorpanel seed
.venv/bin/donorpanel ping --to demo --body "Channel check."
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check src tests
```

Everything above runs with no AWS credentials. Set `DONORPANEL_BUCKET` to switch storage to S3.

Copy `.env.example` to `.env` and fill it in for real channels. Without credentials only `console` is available, which is enough for tests.

## Hackathon context

AWS "Agents for Humans" hackathon, Good Neighbor Agents track. Deadline 14 September 2026, 5pm PDT.

Judged on Technological Implementation, Design, Potential Impact, Creativity and Originality, Presentation. Submissions need a public MIT or Apache licensed repo, a README with an architecture diagram, and a demo video of five minutes or less.

Two presentation constraints that affect what we build:

- The demo must open on the mechanism, not the geography. Roughly thirty seconds establishing the problem before anything is shown, anchored to cases a non-Indian judge already recognizes (NMDP reachability, NHSBT Ro shortfall).
- Consent and request verification must be visible in the architecture and stated out loud, because an agent that contacts people about a medical emergency reads as a robocall unless you preempt it.
