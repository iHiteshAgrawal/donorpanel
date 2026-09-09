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

`agents/`, `nodes/` and `tools/` are intentionally empty. Do not populate them speculatively.

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
  policies/    condition YAML plus loader
  storage/     empty, session repository
  config.py    environment configuration
  main.py      CLI entrypoint
tests/
```

## Commands

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/donorpanel status
.venv/bin/donorpanel ping --to demo --body "Channel check."
.venv/bin/python -m pytest tests -q
```

Copy `.env.example` to `.env` and fill it in for real channels. Without credentials only `console` is available, which is enough for tests.

## Hackathon context

AWS "Agents for Humans" hackathon, Good Neighbor Agents track. Deadline 14 September 2026, 5pm PDT.

Judged on Technological Implementation, Design, Potential Impact, Creativity and Originality, Presentation. Submissions need a public MIT or Apache licensed repo, a README with an architecture diagram, and a demo video of five minutes or less.

Two presentation constraints that affect what we build:

- The demo must open on the mechanism, not the geography. Roughly thirty seconds establishing the problem before anything is shown, anchored to cases a non-Indian judge already recognizes (NMDP reachability, NHSBT Ro shortfall).
- Consent and request verification must be visible in the architecture and stated out loud, because an agent that contacts people about a medical emergency reads as a robocall unless you preempt it.
