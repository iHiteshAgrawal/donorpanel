# DonorPanel Architecture Analysis

## Project Overview

**DonorPanel** is a multi-agent system that coordinates blood donors for patients who need matched blood repeatedly throughout their lives. It addresses the critical bottleneck of recruitment coordination labor by automating donor matching, verification, and outreach for conditions like thalassemia and sickle cell disease.

## Core Problem Solved

Patients with transfusion-dependent conditions need matched blood repeatedly, for life. The recruitment burden falls on patients and families in crisis. DonorPanel shifts this labor to an intelligent system that holds the network so no user has to browse it.

## Architecture Layers

### 1. API Layer (FastAPI)
**Location**: `src/donorpanel/api/app.py`

The FastAPI server provides REST endpoints for:
- Health checks and system status
- Patient management and queries
- Donor management and pool listings  
- Request submission and tracking
- Human approval gate for outreach

Key endpoints:
- `GET /api/health` - System status including region, model, storage backend
- `GET /api/patients` - List all patients
- `GET /api/donors` - List all donors
- `GET /api/requests` - Check pending requests awaiting approval
- `POST /api/approve` - Human approval for dispatching outreach

### 2. Request Processing Graph (Strands Multi-Agent Framework)
**Location**: `src/donorpanel/graphs/request.py`

The heart of the system - a directed graph that processes blood requests through deterministic and AI-assisted nodes:

#### Flow Phases

**Phase 1: Intake & Verification**
```
intake → verify → adjudicate → {accept | close}
```

- **IntakeNormalizer** (Deterministic)
  - Normalizes raw request data
  - Resolves patient identity and loads matching policy
  - Computes request fact sheet
  - Creates DRAFT request
  - No model calls

- **RequestVerifier** (Agent + Model)
  - Reasons about request validity using one tool: `request_history`
  - Uses two model calls (free reasoning + structured output)
  - Structured output forces Bedrock to return typed `Verdict` instead of prose
  - Detects fraud, duplicate requests, invalid data
  - Returns verdict: `verified` or `rejected`

- **Adjudicate** (Deterministic)
  - Reads verdict from verify node
  - Routes to accept (verified) or close (rejected)
  - Hard gate: fails closed if no usable decision

**Phase 2: Matching (Entirely Deterministic)**
```
accept → eligibility → rank → {compose | end}
```

- **EligibilityResolver** (Deterministic)
  - Expands recipient blood group through compatibility table
  - Pulls donor pools per blood group and region
  - Filters on policy eligibility rules
  - Tracks all exclusion reasons
  - No model calls - pure rules and arithmetic

- **CohortRanker** (Deterministic)
  - Scores eligible donors on multiple factors:
    - Rest since last donation
    - Contact fatigue (outreach frequency)
    - Repeat-donor preference
    - Haversine proximity distance
  - Ranks by composite score
  - Creates Contact records with rankings

**Phase 3: Outreach & Approval**
```
rank → compose → gate
```

- **OutreachComposer** (Agent + Model)
  - Groups cohort by language and communication channel
  - Hands agent a minimal brief (patient first name only)
  - No age, diagnosis, surname, or phone number exposed
  - Gets back typed `Draft` messages per group
  - Enforces tone: professional, not desperate
  - Creates structured outreach drafts

- **HumanGate** (Hard Stop - No Automatic Execution)
  - Reads `approvals/<request_id>.json` from storage
  - If absent: sets request to AWAITING_APPROVAL, returns pending
  - If present: reads approver identity, returns approved
  - **Nothing downstream can run until human writes approval file**
  - This is the key safety mechanism preventing autonomous action

#### Conditional Routing

The graph uses intelligent conditions:
- `is_verified()` - Routes verified requests to accept path
- `is_rejected()` - Routes rejected requests to close path
- `has_cohort()` - Only composes if eligible donors exist (avoids drafting to empty cohort)

If no eligible donors found, request stops at rank with MATCHING status rather than creating worthless drafts.

### 3. Node Architecture (Strands JsonNode Base)
**Location**: `src/donorpanel/nodes/base.py`

All nodes inherit from `JsonNode` and `MultiAgentBase`:

```python
class JsonNode(MultiAgentBase):
    def run(self, task: Any, invocation_state: dict) -> dict[str, Any]:
        # Synchronous, dict-returning work
        # Runs on thread pool to avoid blocking event loop
        pass
```

**Key patterns:**
- `task_text()` - Extracts text from ContentBlock list (handles Strands SDK format)
- `json_blocks()` - Parses balanced JSON objects from concatenated upstream output
- `find_block()` - Finds last JSON block containing a specific key
- All nodes wrap output in JSON for next node consumption
- Input carries every upstream node's output concatenated

**Node categories:**

1. **Deterministic Nodes** (No model calls)
   - IntakeNormalizer, Adjudicate, EligibilityResolver, CohortRanker, MarkVerified, CloseRejected
   - Pure business logic, rules, arithmetic
   - Fully testable without stubs or mocking

2. **Agent Nodes** (Model calls)
   - RequestVerifier (uses Bedrock with structured output)
   - OutreachComposer (uses Bedrock with structured output)
   - These are the only model-calling nodes

### 4. Domain Layer
**Location**: `src/donorpanel/domain/`

Pure Python dataclasses and enums, no AWS imports:

**Core Models:**
```python
@dataclass
class Donor:
    donor_id, name, blood_group, region, channel
    lat, lon, antigens, last_donation, consent, reachable
    last_contacted, contacts_this_month

@dataclass
class Patient:
    patient_id, name, condition, blood_group, policy_id
    region, antigens_required, city, hospital

@dataclass
class Request:
    request_id, patient_id, component, source
    created_at, status

@dataclass
class Contact:
    contact_id, request_id, donor_id, status, rank, eligibility_reason
```

**Enums:**
- `Condition`: THALASSEMIA, SICKLE_CELL, RARE_PHENOTYPE, OTHER
- `Component`: WHOLE_BLOOD, PLATELETS, PACKED_CELLS
- `RequestStatus`: DRAFT → VERIFIED → MATCHING → AWAITING_APPROVAL → DISPATCHED → FULFILLED/SHORT/CLOSED
- `ContactStatus`: PENDING → PLEDGED/DECLINED/NO_RESPONSE → DONATED

**Matching Logic:**
```python
# src/donorpanel/domain/matching.py - Pure functions, testable without graph

blood_type_compatibility(recipient_group) → list[compatible_groups]
is_eligible(donor, policy, request) → (bool, reason)
score(donor, cohort_context) → float  # Composite: recency + fatigue + repeat + proximity
distance_decay(km) → float  # Haversine-based proximity term
```

### 5. Policy Layer
**Location**: `src/donorpanel/policies/`

Condition-specific rules as YAML configuration, not hardcoded:

```yaml
# thalassemia-india.yaml
cadence: "2w"  # Every 2 weeks
component: "whole_blood"
units_per_transfusion: 10
donor_eligibility:
  min_age: 18
  max_age: 60
  min_rest_days: 60
  antigen_requirements: [D, c, E, e, K]
  preferred_donors: true
outreach_strategy:
  language_groups: [Tamil, English]
  channels: [telegram, email]
  max_contacts_per_month: 3
```

New conditions require only new YAML files, no code changes. Policies are loaded and cached at startup.

### 6. Storage Layer
**Location**: `src/donorpanel/storage/`

Dual-backend abstraction for data persistence:

#### Backend Options
```
FileStore (Local Development)
├─ data/local/
│  ├─ donors/<donor_id>.json
│  ├─ patients/<patient_id>.json
│  ├─ requests/<request_id>.json
│  ├─ contacts/<request_id>/<donor_id>.json
│  ├─ pool/<region>/<blood_group>/
│  ├─ credits/<patient_id>.json
│  └─ approvals/<request_id>.json

ObjectStore (S3 Production)
└─ s3://donorpanel-292368431051/
   ├─ donors/<donor_id>.json
   ├─ patients/<patient_id>.json
   ├─ requests/<request_id>.json
   ├─ contacts/<request_id>/<donor_id>.json
   ├─ pool/<region>/<blood_group>/
   ├─ credits/<patient_id>.json
   └─ approvals/<request_id>.json
```

**Selection Logic:**
```python
def store():
    return ObjectStore() if config.bucket else FileStore(config.local_root)
```

#### PanelRepository
High-level interface that never knows which backend is active:
- `put_donor()` - Update donor, manage pool markers
- `get_donor()` - Retrieve donor by ID
- `list_pool()` - Query donors by region + blood group (traverses pool/ prefix)
- `put_request()` - Persist request state transitions
- `get_request()` - Retrieve request
- Similar for Patient, Contact, Credits

Pool queries are cheap: list pool/ prefix, then read each donor by ID (no GSI needed).

#### Session Management
```python
def session_manager(session_id: str) -> SessionManager:
    if config.bucket:
        return S3SessionManager(session_id, bucket=config.bucket, prefix="sessions/")
    return FileSessionManager(session_id, storage_dir="data/local/sessions")
```

Sessions enable graph checkpointing and resume across multiple invocations. Entire request graph can suspend at any node and resume later.

### 7. Communication Channels
**Location**: `src/donorpanel/channels/`

Multi-channel abstraction - agents never know transport mechanism:

```python
class Channel(ABC):
    async def send(self, message: Message) -> bool
    async def poll(self) -> list[Reply]
    async def available(self) -> bool
```

**Implementations:**
- **ConsoleChannel**: Print to stdout (testing, local development)
- **TelegramChannel**: HTTPX-based Bot API calls (cheap, no phone needed)
- **EmailChannel**: Template-based email (for longer messages)
- Voice, WhatsApp, X: Architecture ready, future implementation

Each channel is registered in `channels/__init__.py:registry()` and selected per outreach cohort.

### 8. Agent System (Strands Framework)
**Location**: `src/donorpanel/agents/`

Two Bedrock agents provide the AI reasoning:

#### RequestVerifier Agent
- **System Prompt**: Reasoning about request validity
- **Tools**: `request_history` - Query past requests for same patient/donor pairs
- **Model Calls**: 2 per request
  1. Free reasoning with tools
  2. Structured output call forcing `Verdict` Pydantic schema
- **Output**: Typed `Verdict` (verified | rejected) with reasoning

#### OutreachComposer Agent  
- **System Prompt**: Professional outreach message writing
- **Input**: Minimal brief with patient first name only
- **Rules**: No age, diagnosis, surname, phone - tested and asserted
- **Tone**: Professional volunteer coordinator, not desperate
- **Output**: Structured `Draft` per language+channel group
  - Subject line (email)
  - Body with `{name}` placeholder
  - Plain decline mechanism

### 9. AWS Integration
**Location**: `src/donorpanel/config.py`

**Account**: 292368431051 (ap-southeast-2 Sydney)

**Services Used:**
- **Amazon Bedrock**: Model inference (nova-pro-v1 or Claude 3.5)
  - Region scoped: `au.` prefix for newer, `apac.` for older Anthropic models
  - Structured output forces typed returns instead of prose parsing
  
- **S3**: Data storage bucket `donorpanel-292368431051`
  - Same JSON schema across FileStore and ObjectStore
  - Managed by PanelRepository abstraction

- **CloudWatch Logs**: Observability and auditing
  - Request lifecycle tracking
  - Agent reasoning logs
  - Node execution metrics

**Regions:**
- All project resources in **ap-southeast-2** (Sydney)
- Service control policy from org account (042269275956) applies
- Denies DynamoDB, S3 CreateBucket, EventBridge PutRule in us-east-1 only

**Credentials:**
- CLI profile `default` - IAM user with static keys
- CLI profile `donorpanel` - Browser sign-in, 12-hour sessions (`aws login --profile donorpanel`)

## Data Flow Example: New Transfusion Request

```
1. API: POST /api/requests
   └─ Raw request data: patient_id, component, units, by_date

2. Graph: intake
   └─ Normalize data, load policy, compute fact sheet
   └─ Create DRAFT request in storage

3. Graph: verify
   └─ RequestVerifier Agent reasons: Is this legitimate? Past history?
   └─ Tools: request_history lookup
   └─ Structured output: Verdict (verified | rejected)

4. Graph: adjudicate
   └─ Read verdict
   └─ Route: verified → accept, rejected → close

5. Graph: eligibility (if verified)
   └─ Blood type compatibility check
   └─ Query pool/<region>/<blood_group>/
   └─ Filter: consent, reachability, antigens, policy eligibility
   └─ Track exclusion reasons

6. Graph: rank (if cohort found)
   └─ Score each eligible: recency + fatigue + repeat + proximity
   └─ Create Contact records ranked by score
   └─ Request → MATCHING status

7. Graph: compose (if cohort non-empty)
   └─ Group by language and channel
   └─ OutreachComposer Agent drafts message per group
   └─ Structured output: Draft with subject, body, decline mechanism

8. Graph: gate (Hard Stop)
   └─ Poll for approval: approvals/<request_id>.json
   └─ If absent: request → AWAITING_APPROVAL, return pending
   └─ If present: Human name recorded, ready to dispatch

9. CLI: donorpanel pending
   └─ Shows queue with full drafts awaiting approval

10. CLI: donorpanel approve --request <id> --by <name>
    └─ Admin writes approvals/<request_id>.json
    └─ Gate unblocks on next graph poll

11. Dispatcher (Future)
    └─ Read approved contacts
    └─ Send via respective channels
    └─ Track pledges, declines, donations
```

## Key Architectural Decisions

### 1. Deterministic vs. AI Nodes
- All matching arithmetic: deterministic custom nodes (no model calls)
- Agents reason about numbers handed to them, never compute them
- Keeps reasoning simple, arithmetic auditable

### 2. Structured Output Enforcement
```python
# Instead of: "The request is verified."
# We get: Verdict(decision="verified", reason="...", confidence=0.95)

result = agent.structured_output(Verdict, task)
```

This eliminates parsing errors and edge cases where model reasoning looks correct but prints invalid JSON.

### 3. Hard Human Gate, Not Soft Prompt
```python
# Wrong: Send message on gate node with system prompt "Ask human for approval"
# Right: Hard stop until human writes approval file

if not exists("approvals/<request_id>.json"):
    return "AWAITING_APPROVAL"
```

Nothing executes unattended. No prompt injection risk. Clear audit trail.

### 4. Minimal AI Prompts
- RequestVerifier: Reason about validity
- OutreachComposer: Write professional message
- Both agents are narrow specialists, not general problem solvers
- Reduces token cost and hallucination risk

### 5. Policy-First Configuration
```yaml
# New condition = new YAML file, never new subsystem
# Policies define: cadence, antigen requirements, outreach strategy
# Code never hardcodes region-specific rules
```

Makes the system genuinely global-ready.

### 6. Session Checkpointing
```python
# Entire graph can pause and resume
# Not just single agent state
# Enables long-running transfusion coordination
```

Graph can checkpoint at any node, resume later with full context.

### 7. Channel Abstraction
```python
# Agents never know if they are sending Telegram or Email
# Channel interface is uniform: send(), poll(), available()
# Add new channel = implement interface + register
```

Multi-transport without agent awareness.

## Planned Enhancements

### Phase 1 (Current)
- ✅ Intake normalization and verification
- ✅ Deterministic blood matching
- ✅ Cohort ranking
- ✅ Outreach composition
- ✅ Human approval gate
- ✅ Telegram and Email channels

### Phase 2 (Deferred)
- Geographic matching with Amazon Location Service
- Distance decay curves (not just binary 0/100km cutoff)
- Travel time routing (not straight-line distance)

### Phase 3 (Deferred)
- EventBridge scheduled transfusion reminders
- Lambda background registry hygiene jobs
- Bedrock Knowledge Base for eligibility rules
- Guardrails to block medical determinations

### Phase 4 (Deferred)
- Amazon Connect voice channel
- Polly text-to-speech
- Transcribe incoming voice
- AgentCore Runtime for session isolation
- Multi-agent coordination for complex cases

## Testing Strategy

### Node Testing
```python
# Deterministic nodes: test directly with domain objects
eligibility = EligibilityResolver()
cohort, reasons = eligibility.run(request, donors, policy)
assert len(cohort) == expected_count
```

### Graph Testing
```python
# Both model nodes stubbed to avoid Bedrock calls
graph = build(agent=StubVerifier(), composer_agent=StubComposer())
result = graph("...", invocation_state={...})
assert result.status == "COMPLETED"
```

### Integration Testing
```python
# End-to-end flow with moto (S3) and tmp_path (FileStore)
# No credentials needed
def test_flow(tmp_path):
    repo = PanelRepository(FileStore(tmp_path))
    result = flow.run(request_data, repo=repo)
    assert result["verdict"]["verdict"] == "verified"
```

## Observability & Safety

- CloudWatch Logs for request lifecycle and reasoning
- Request ID and human approver name on every approval
- Audit trail: who approved what, when, why
- Hard gates prevent accidental autonomous action
- Structured output typing reduces hallucination surface

## Regional Constraints

- All services must stay in **ap-southeast-2** (Sydney)
- Service control policy denies DynamoDB/S3 CreateBucket/EventBridge in us-east-1
- If moving region, re-validate SCP and Bedrock model availability
- Bedrock Anthropic models use `au.` prefix in ap-southeast-2

## Configuration

**Environment Variables:**
```bash
# AWS
AWS_REGION=ap-southeast-2
AWS_PROFILE=default  # or 'donorpanel' for browser auth

# DonorPanel
DONORPANEL_ENV=dev  # or 'prod'
DONORPANEL_BUCKET=donorpanel-292368431051  # Set for S3, omit for local FileStore
DONORPANEL_LOCAL_ROOT=data/local  # Used when DONORPANEL_BUCKET not set

# Bedrock
BEDROCK_MODEL_ID=apac.nova-pro-v1  # or your preferred model
```

**Build:**
```bash
# Python 3.10+, managed with uv
uv sync
uv run donorpanel init
uv run donorpanel seed  # Load demo data
```

## Running the System

```bash
# Initialize storage backend
uv run donorpanel init

# Seed with demo data (India thalassemia case)
uv run donorpanel seed

# Start API server
uv run fastapi run src/donorpanel/api/app.py

# Submit a request (Python)
from donorpanel.graphs import request as flow
result = flow.run({"patient_id": "p-1", "component": "whole_blood", ...})

# Check pending approvals
uv run donorpanel pending

# Approve a request  
uv run donorpanel approve --request r-abc123 --by "Dr. Smith"

# Reset all data
uv run donorpanel reset
```

## File Structure Summary

```
src/donorpanel/
├── main.py             # CLI commands (init, seed, reset, pending, approve)
├── config.py           # Environment and AWS configuration
├── geo.py              # Haversine distance calculations
│
├── domain/             # Pure dataclasses, no AWS imports
│   ├── models.py       # Donor, Patient, Request, Contact, Enums
│   └── matching.py     # Blood compatibility, scoring, eligibility rules
│
├── storage/            # Dual backend abstraction
│   ├── local.py        # FileStore implementation
│   ├── objects.py      # ObjectStore (S3) implementation
│   └── repository.py   # PanelRepository interface
│
├── nodes/              # Graph node implementations (Strands JsonNode)
│   ├── base.py         # JsonNode base class, utilities
│   ├── intake.py       # IntakeNormalizer
│   ├── verify.py       # RequestVerifier (Agent + Model)
│   ├── adjudicate.py   # Adjudicate routing
│   ├── approve.py      # MarkVerified, CloseRejected
│   ├── match.py        # EligibilityResolver, CohortRanker
│   └── outcome.py      # OutreachComposer, HumanGate
│
├── agents/             # Bedrock agents
│   ├── verifier.py     # RequestVerifier configuration
│   └── composer.py     # OutreachComposer configuration
│
├── channels/           # Multi-transport abstraction
│   ├── base.py         # Channel interface
│   ├── console.py      # ConsoleChannel
│   ├── telegram.py     # TelegramChannel (HTTPX)
│   └── email.py        # EmailChannel
│
├── tools/              # @tool functions for agents
│   └── history.py      # request_history tool
│
├── policies/           # YAML condition configurations
│   ├── thalassemia-india.yaml
│   └── sickle-cell-uk.yaml
│
├── graphs/             # Graph orchestration
│   └── request.py      # Request processing graph definition
│
└── api/                # FastAPI server
    └── app.py          # REST endpoints
```

## Summary

DonorPanel is a sophisticated multi-agent system that demonstrates:
- **AI reasoning** at exactly the right scale (verify, compose)
- **Deterministic logic** where it matters (matching, scoring)
- **Hard safety gates** blocking autonomous action
- **Policy-first configuration** enabling global deployment
- **Clean abstraction layers** (storage, channels, domain)
- **Production-ready patterns** (structured output, session checkpointing)

The architecture enables rapid iteration on policies and channels while maintaining data integrity and human oversight at every critical decision point.
