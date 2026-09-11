# Identity and memory plan

Agreed 2026-09-11. Submission is 2026-09-14, 5pm PDT.

Grounded in `awslabs/agentcore-samples`
(`01-features/04-manage-context-of-your-agent/memory`,
`01-features/05-authenticate-and-authorize/01-inbound-auth`) and the Strands
AgentCore integration docs, reconciled against AWS documentation where those
did not cover a detail.

## Two corrections that shaped this

**A browser can call AgentCore Runtime directly.** Earlier notes said it could
not and that the web tier had to proxy with SigV4. AgentCore Runtime supports a
**JWT bearer authorizer**, and AWS guidance names it the right choice for web
and mobile front ends: identity propagates from the token claims automatically,
with no proxy and no header to set by hand. SigV4 remains correct for service
to service calls.

**`AgentCoreMemorySessionManager` allows only one agent per session**, which
would block us because `verify` and `compose` are both agents. The official
multi-agent Strands sample does not use it. It registers a
`MemoryHookProvider(HookProvider)` on `AfterInvocationEvent` per agent, each
writing to its own namespace, which sidesteps the limit.

## The thing that does not change

AgentCore Memory is keyed on `actorId` and `sessionId` and stores **agent
memory**: extracted preferences, facts, session summaries. Donors, patients,
requests, contacts and approvals are S3 objects that no agent ever sees.
**Memory does not partition application data.** Identity supplies the key, but
the partitioning still has to be done.

Runtime state is purged when a session ends (15 minutes idle, 8 hours maximum),
so Memory is the persistence answer across that boundary, not a datastore.

## Steps

### 1. Cognito and the JWT authorizer
Amazon Cognito user pool plus app client in ap-southeast-2. Every visitor gets
an `actorId` from the token's `sub` claim. FastAPI validates the JWT and derives
the actor; the SPA signs in. The `customJWTAuthorizer` goes on the runtime when
we deploy.

Also closes an open gap: the coordinator is currently a self-asserted string
(`--by anita`), which makes the audit trail decorative.

### 2. Partition S3 by actorId
A `prefix` on `ObjectStore`, prepended in `put`, `get`, `touch`, `delete` and
`keys`; `store()` reads the actor from the request. `PanelRepository` never sees
a raw key, so nothing else changes. This is what actually stops one judge seeing
another's requests, and what stops `RequestVerifier` rejecting everything as a
duplicate after the third run.

### 3. AgentCore Memory resource
`USER_PREFERENCE` and `SEMANTIC` strategies, namespaces per agent:

```
/donorpanel/{actorId}/preferences/    what a donor told us
/donorpanel/{actorId}/outreach/       what the composer learned about tone
```

### 4. MemoryHookProvider per agent
Following the sample: `AfterInvocationEvent`, `actor_id` and `session_id` read
from agent state, `client.create_event(...)`. `verify` and `compose` each get
their own namespace. Gives donor preferences somewhere to live at all, which
they currently do not have, and gives `RegistryHygiene` real work.

### 5. IAM
Grants for `bedrock-agentcore`, `bedrock-agentcore-control` and `cognito-idp`.
Verified 2026-09-11: all three are available in ap-southeast-2 and **none are
SCP blocked**, they only need identity based grants.

## Risk

This is meaningful new surface with three days left. **Steps 1 and 2 rescue the
demo; steps 3 and 4 score.** If something has to give, memory is easier to cut
than identity.
