# Agents for Humans: the blood donor agent where only two of ten nodes are agents

> FIGURE: cover.png

A child with thalassemia major needs matched blood every two to four weeks. Not once. For life.

In India there are between 100,000 and 150,000 of them, and their families arrange the donors themselves. Every fortnight. Forever. A parent spends the week before each transfusion calling people, posting in WhatsApp groups, and asking relatives to ask their relatives.

The obvious fix is a bigger registry. Registries already exist, and they are mostly dead. Only 55 to 60 percent of registered US marrow donors are reachable and available when finally called, and attrition runs 60 percent among minority donors against 40 percent among white donors. NHSBT supplies 3,600 units of Ro blood a month against a need of 7,400.

So the database was never the bottleneck. **The bottleneck is coordination labour, and it lands on whoever is least able to carry it:** a parent whose child is due for a transfusion on Thursday.

Matching follows ancestry, which means the pool of donors who can match a given patient is systematically smaller than the population that needs them. A bigger registry does not fix that. A system that knows who is genuinely reachable, and asks them before anyone is desperate, does.

This post is about building that system on Strands Agents and Amazon Bedrock AgentCore. It covers what we used and what for, five patterns you can lift straight into your own graph, and the three things that broke in production.

The thread running through all of it: most agent write-ups explain what the model decided. This one is mostly about **what we refused to let the model decide.**

## What we built

DonorPanel is a Telegram agent called Asha. There is no dashboard to learn and no account to create. You message her and she does the rest.

She handles three conversations and works out which one you are in from what you say. Someone asking for blood for a friend gets a request opened and the network searched. Someone offering to help gets registered, with their city geocoded so distance ranking works. Someone answering outreach gets their pledge recorded.

The part that matters is the one nobody starts a conversation for. **Every few hours the system forecasts.** A patient on a fixed transfusion cycle is predictable, so last transfusion plus the policy interval is the next one. Requests open before a family thinks to ask, donors are contacted in ranked waves, and the whole thing runs with nobody watching.

That is the difference between an SOS broadcast and a panel. An SOS asks everyone at once, in a crisis, and burns the network's goodwill. A panel asks eight people in a considered order, a week early, and stops when it should.

## The architecture

> FIGURE: architecture-runtime.png
>
> Caption: One Lambda function with four modes. EventBridge drives the tick, which is the part nobody asks for.

> FIGURE: architecture-graph.png
>
> Caption: The request graph. Blue nodes call a model. The gate either dispatches or asks a coordinator.

Following one message end to end:

1. Telegram posts the update to **API Gateway**, which proxies it to **Lambda** in webhook mode.
2. Lambda acknowledges immediately and invokes **itself** asynchronously. That one decision is the subject of the most expensive bug in this post.
3. The async invocation calls **AgentCore Runtime**, which hosts Asha with a session dedicated to that person.
4. Asha calls her tools, reads and writes her conversation thread in **S3**, and writes what is worth keeping to **AgentCore Memory**.
5. The answer returns to Lambda, which sends it to Telegram as a fresh outbound call.
6. If a tool set a `launch` flag, Lambda invokes itself again to run the **ten node graph**.

Separately, **EventBridge Scheduler** wakes the same Lambda on a fixed rate to settle, forecast and chase.

## What we used, and what for

Before any deep dive, here is the whole inventory. If you read nothing else, these two figures are the map.

### Strands Agents

**Orchestration**

- `GraphBuilder` builds the ten node request pipeline, from intake to dispatch.
- **Conditional edges** route on JSON found in node output, never on model prose.
- `invocation_state` carries the repository and request id through every node without globals.

**The eight deterministic nodes**

- `MultiAgentBase` is the base class for every node that is plain Python rather than a model.
- `MultiAgentResult`, `NodeResult` and `Status` are the result shape a Graph expects, which is what lets a node failure route instead of raising.

**The two agents**

- `Agent` for Asha, plus the request verifier and the outreach composer.
- **Structured output** so the verifier returns a typed verdict, not a sentence to be parsed.
- `callback_handler=None` on every agent, because Strands prints to stdout by default and on Lambda stdout is CloudWatch.

**Tools**

- `@tool` for ten conversational tools, plus `request_history` on the verifier.
- `ToolContext` gives a tool the repository and the speaker, bound per conversation.

**State, reliability and telemetry**

- `S3SessionManager` holds the conversation thread per person, so Asha resumes rather than restarts.
- `FileSessionManager` is the same thread on disk for local development.
- `HookProvider` and `HookRegistry` register side effects without touching node code.
- `AfterNodeCallEvent` fires as each node completes, which is where memory is written.
- `ModelRetryStrategy` bounds retry on a throttled model instead of five minutes of backoff.
- `BedrockModel` and `OpenAIModel` sit behind one constructor, so all three agents switch together.
- `EventLoopMetrics` attaches per run telemetry to every node result.

### AWS

**Running the agent**

- **Bedrock AgentCore Runtime** hosts Asha: one agent, one request, one response, a dedicated session per person.
- **Bedrock AgentCore Memory** keeps what is worth remembering after a conversation ends, on two strategies.
- **Amazon Bedrock** serves the model behind all three agents.

**Compute and edge**

- **AWS Lambda** is one function with four modes: the webhook, the reply, the graph run, the tick.
- **API Gateway** receives the Telegram webhook and proxies it. Inbound only.
- **CloudFront and S3** serve the public landing page, with origin access control on the bucket.

**Acting without being asked**

- **EventBridge Scheduler** drives the tick that settles, forecasts and chases.

**Data and delivery**

- **Amazon S3** is the whole store: donors, patients, requests, contacts, and session threads.
- **Amazon Location Service** geocodes a donor's city so distance ranking is real kilometres.
- **Amazon SES** carries outreach to donors who are not on Telegram.

**Operations**

- **Amazon ECR** holds two ARM64 images, deployed by immutable tag so the repository records what is actually running.
- **CloudWatch Logs** carries retention plus a data protection policy masking personal data.
- **IAM** carries three execution roles, each scoped to one job.

The next two sections go deeper on the parts that were not obvious.

## Five Strands patterns you can lift

> FIGURE: graph-strip.png
>
> Caption: The request graph. Green nodes call a model. The other eight are plain Python.

### 1. A `MultiAgentBase` adapter for deterministic nodes

Eight of our ten nodes are plain Python. They do not call a model at all. Strands supports this through `MultiAgentBase`, but you have to produce the result shape a Graph expects, and that shape is not obvious the first time.

We wrote one adapter and every deterministic node inherits it:

```python
class JsonNode(MultiAgentBase):
    """Wraps a dict-returning run() into the NodeResult shape a Graph expects."""

    name = "node"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def invoke_async(self, task, invocation_state=None, **kwargs) -> MultiAgentResult:
        started = time.time()
        state = invocation_state or {}
        try:
            payload = await asyncio.to_thread(self.run, task, state)
            status = Status.COMPLETED
            text = json.dumps(payload, indent=2, default=str)
        except Exception as exc:
            status = Status.FAILED
            text = json.dumps({"node": self.name, "error": str(exc)})

        elapsed = int((time.time() - started) * 1000)
        result = AgentResult(
            stop_reason="end_turn",
            message={"role": "assistant", "content": [{"text": text}]},
            metrics=EventLoopMetrics(),
            state={},
        )
        return MultiAgentResult(
            status=status,
            results={self.name: NodeResult(result=result, status=status,
                                           execution_time=elapsed, execution_count=1)},
            execution_count=1,
            execution_time=elapsed,
        )
```

A node then becomes eleven lines instead of forty:

```python
class CloseRejected(JsonNode):
    name = "close"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request_id = invocation_state["request_id"]
        reason = find_block(task_text(task), "verdict").get("reason") or "not verified"
        request = repo.get_request(request_id)
        if request is not None:
            request.status = RequestStatus.REJECTED
            request.rejection_reason = reason
            repo.put_request(request)
        return {"request_id": request_id, "status": RequestStatus.REJECTED.value,
                "reason": reason}
```

Two things in that adapter are worth stating plainly, because both cost us time.

**`run()` is synchronous and does blocking work.** It calls boto3 and sometimes a model. Calling it directly from `invoke_async` freezes the event loop for the entire node, which stalls server sent event flushes so a UI receives `node_start` and `node_stop` at the same instant. `asyncio.to_thread` fixes it.

**The `except` is broad on purpose.** A node failure has to surface as a `FAILED` NodeResult that the graph can route on. If it escapes as an exception it kills the whole run, and you lose the ability to handle failure as a branch.

### 2. Conditional edges that read JSON, never prose

This is the pattern the whole project rests on. Branching on model prose failed roughly one run in five, so every edge condition reads a JSON block out of the upstream node's output:

```python
def is_rejected(state) -> bool:
    return _verdict(state) == "rejected"

def has_cohort(state) -> bool:
    return find_block(node_text(state, "rank"), "cohort_size").get("cohort_size", 0) > 0

def is_cleared(state) -> bool:
    return find_block(node_text(state, "gate"), "gate").get("gate") in ("auto", "approved")
```

Wired up, the graph reads like the diagram:

```python
builder = GraphBuilder()
builder.add_node(IntakeNormalizer(), "intake")
builder.add_node(agent or RequestVerifier(), "verify")
builder.add_node(Adjudicate(), "adjudicate")
...
builder.add_edge("adjudicate", "accept", condition=is_verified)
builder.add_edge("adjudicate", "close", condition=is_rejected)
builder.add_edge("rank", "compose", condition=has_cohort)
builder.add_edge("compose", "gate")
builder.add_edge("gate", "dispatch", condition=is_cleared)
```

Two gotchas here, and neither is in the documentation.

**A node's input carries every upstream node's output concatenated.** So the obvious parse, from the first brace to the last, spans two separate JSON objects and fails. We scan for balanced blocks and take the last one containing the key we want:

```python
def find_block(text: str, key: str) -> dict[str, Any]:
    for block in reversed(json_blocks(text)):
        if key in block:
            return block
    return {}
```

**`task` is not a string.** A Graph hands a node a list of ContentBlock dicts. Calling `str()` on it escapes the newlines inside each block and breaks any JSON parse downstream:

```python
def task_text(task: Any) -> str:
    if isinstance(task, list):
        return "\n".join(block.get("text", "") for block in task
                          if isinstance(block, dict))
    return str(task)
```

One more design note. The conditional edge cannot be the thing that decides, because an edge can only return true or false, so it cannot fail closed. `adjudicate` is a node that produces a verdict; `is_verified` is an edge that reads it. Keeping those separate is what lets the system default to safe when the verdict is missing or malformed.

### 3. A gate that decides whether a human is needed at all

This is what makes it an agent rather than a workflow.

`AutonomyGate` is a deterministic node that returns a list of reasons to escalate. An empty list means dispatch unattended. A non-empty list means a coordinator sees it first, with the reason written for a human and then translated into plain language before it reaches whoever asked.

It stops and asks a human when the request is an emergency, when the verifier flagged something for review, when the matched cohort is too small for the units needed, when a donor would exceed their monthly contact budget, or when no outreach drafts were produced. Everything else dispatches on its own, which is most runs.

The thresholds live in policy YAML, not in code:

```yaml
outreach:
  cohort_size: 8
  escalation_hours: [0, 24, 48]
```

Which brings us to the second half of autonomy: knowing when to stop.

Contact the ranked cohort at hour zero. Widen to donors not yet asked after a day. One more wave after two. Then stop.

When the waves are exhausted and the request is still short, that is the signal a human is needed, not a reason to widen the net further. Donors who declined are never asked again, and a per donor monthly contact budget caps how often anyone hears from us at all. A system that spams its donors destroys the reachability it depends on, which is precisely how the existing registries died.

### 4. Hooks for side effects, on the right event

We wanted to write to memory as the graph ran, without every node knowing memory exists. Strands hooks do exactly that:

```python
class MemoryWriter(HookProvider):
    """Writes one run to AgentCore Memory once the graph reaches a terminal node."""

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterNodeCallEvent, self.on_node_done)

    async def on_node_done(self, event: AfterNodeCallEvent) -> None:
        state = event.invocation_state or {}
        actor_id = state.get("actor_id")
        if event.node_id not in TERMINAL or not actor_id:
            return
        try:
            await asyncio.to_thread(self.write, state, actor_id)
        except Exception:
            log.warning("memory hook failed for %s", state.get("request_id"), exc_info=True)
```

Three things we learned the hard way.

**Pick `AfterNodeCallEvent`, not the invocation events.** `AfterInvocationEvent.result` is `None` when an agent uses structured output, and both of our agents do, so a hook on that event would have read nothing. `AfterMultiAgentInvocationEvent` is constructed without `invocation_state`, so it cannot see the repository or the request id either.

**Guard the callback.** The registry propagates callback exceptions to the caller, and this event fires from inside a `finally` block. An unguarded hook therefore both kills the run and masks whatever actually failed. Memory is never worth that.

**Do the blocking work off the loop.** Same `asyncio.to_thread` reason as the node adapter.

### 5. One model constructor, two providers, bounded retries

All three agents get their model from one function, so switching provider is one environment variable rather than three code changes:

```python
def llm() -> Model:
    if config.model_provider == "openrouter":
        if not config.openrouter_api_key:
            raise RuntimeError("model provider is openrouter but OPENROUTER_API_KEY is unset")
        return openrouter()
    return bedrock()
```

The retry configuration is small and was surprisingly consequential:

```python
RETRIES = 1
READ_TIMEOUT = 45

def client_config() -> BotoConfig:
    return BotoConfig(retries={"max_attempts": RETRIES, "mode": "standard"},
                      connect_timeout=5, read_timeout=READ_TIMEOUT)

def retries() -> ModelRetryStrategy:
    return ModelRetryStrategy(max_attempts=2, initial_delay=2, max_delay=4)
```

**Two gotchas, both of which bit us.** botocore counts `max_attempts` as retries *on top of* the first call, so `1` means two attempts total. And botocore **rewrites the `Config` object in place**, turning `max_attempts` into `total_max_attempts`, which means a shared `Config` instance gets mutated by whichever client is built from it first. Hence a fresh one per call.

The `ModelRetryStrategy` line matters even more. Strands retries a throttled model *above* botocore, and its defaults sleep 4, 8, 16, 32 then 64 seconds. Left alone, a single throttled call took 152 seconds to fail. More on what that cost us shortly.

## Why each AWS service has the shape it does

**AgentCore Runtime hosts Asha** because she is one agent, one request, one response, with a dedicated session per person. That is exactly what Runtime is for.

**Lambda runs the graph** because it is the opposite shape: ten nodes, thirty to seventy seconds, and nobody waiting on it. One function with four modes rather than four functions, because three extra functions would mean three extra roles, three deployments and three sets of drift. It routes on the event payload and invokes itself for anything slow.

**AgentCore Memory takes two write paths on purpose.**

Facts we already hold exactly, like cohort size, the channels used and what the gate decided, go through `BatchCreateMemoryRecords`. They are written directly, with no extraction and no model call. Patterns worth mining from conversation, like how a donor prefers to be contacted, go through `CreateEvent` and the service derives them on its own schedule.

Paying a model to re-derive a number we already have would be slower, more expensive and less accurate than simply writing it down.

The gotcha: extraction produces nothing useful from a parameter dump. `USER_PREFERENCE` needs preference shaped language, so the event we write states a standing pattern in a sentence rather than listing the fields of a request.

**EventBridge Scheduler drives the tick**, and the target is Lambda rather than the API because Scheduler cannot call an arbitrary HTTPS endpoint.

The tick makes three passes in a fixed order. **Settle** turns requests whose date has passed into fulfilled or short. **Forecast** opens requests for patients whose next transfusion falls inside the policy lead time. **Chase** sends the next escalation wave to donors not yet asked. Every pass is idempotent, so a tick with nothing to do costs a second.

Settle has to run before forecast because a patient with an open request is deliberately never re-forecast. Without something settling old requests, every patient would become permanently invisible to the forecast after their first one.

**S3 is the entire store**, including the Strands session threads. **CloudFront and S3** serve the landing page. **Amazon Location** geocodes a donor's city so ranking uses real kilometres. **SES** carries outreach to donors who are not on Telegram. **ECR** holds two ARM64 images, deployed by immutable tag so the repository records what is actually running.

### Four IAM findings worth writing down

These cost real time and are hard to search for:

- `ecr:GetAuthorizationToken` is account level and **cannot** be scoped to a repository.
- AgentCore needs **five** service linked roles, including `network.bedrock-agentcore` and `runtime-identity.bedrock-agentcore`, even with `networkMode: PUBLIC`.
- `bedrock-agentcore:InvokeAgentRuntimeForUser` is required **alongside** `InvokeAgentRuntime` as soon as you pass `runtimeUserId`.
- `AWS_REGION` is a reserved environment variable in Lambda and setting it is rejected outright.

## Three things that broke in production

### A 30 second cap that cost a day of Bedrock quota

**196 real invocations produced 3,737 throttle events.** Nineteen throttles per message, and not one of the causes was a model.

An API Gateway HTTP API caps an integration at **30 seconds**, and that is the hard maximum, not a setting you can raise. Our webhook did the model call synchronously, so a slow reply became a 503. Telegram reads a 503 as "send it again" and redelivered the same message every two minutes for hours. Each redelivery was a fresh Lambda billed for its full 300 second timeout.

On top of that, two retry layers were multiplying. Strands retried a throttled call above botocore's own retries, sleeping 4, 8, 16, 32 then 64 seconds, so a single throttle took 152 seconds to fail. Long enough for Lambda to be killed at its 300 second timeout, which produced another 503, which produced another redelivery.

Reading CloudWatch rather than guessing was what cracked it, and the guesses were wrong. Switching to a smaller model did nothing, because the cap turned out to be account wide across Nova Pro, Lite and Micro, with and without inference profile prefixes, in three regions.

The fix was architectural. The webhook now acknowledges in 0.03 seconds and replies asynchronously:

```python
    # Acknowledge before answering. API Gateway caps an HTTP API integration at 30s and
    # that is the hard maximum, but a model call plus session load runs past it, so the
    # reply used to arrive as a 503.
    _self_invoke({"mode": "reply", "sender": message.sender, "text": message.body,
                  "reply_to": message.reply_to, "channel": message.channel})
    return {"statusCode": 200, "body": "ok"}
```

End to end, the reply went from never arriving to under four seconds.

### A confidently wrong medical answer

Asked whether O+ can donate to B+, the agent said no. It can.

Three causes had stacked. There was no tool for the question, so the model answered from its own knowledge. The session had persisted its earlier wrong answers, so it anchored on them. And a pairwise tool still could not answer "who can I help", which is the reverse question and needed a second tool of its own.

For a system that dispatches people to hospitals, a plausible sounding wrong answer is the entire risk. The lesson was that the fix belongs in a deterministic tool, not in a better prompt:

```python
@tool
def blood_compatibility(donor_group: str, recipient_group: str) -> str:
    """Whether one blood group can donate to another. Use this for EVERY question about
    compatibility, including ones you believe you already know the answer to.
    """
    donor = donor_group.strip().upper().replace(" ", "")
    recipient = recipient_group.strip().upper().replace(" ", "")
    if donor in compatible_groups(recipient):
        return (f"YES. {donor} can donate to {recipient}. State this plainly and do not "
                f"qualify it.")
    return (f"NO. {donor} cannot donate to {recipient}. The groups that can are: "
            f"{', '.join(compatible_groups(recipient))}.")
```

Worth dwelling on the second cause, because it is a property of session persistence that nobody warns you about. The agent had **persisted its own earlier wrong answers**, so on each retry it anchored on them and said "as previously mentioned". Persistence is a feature, and it will faithfully preserve a mistake until you clear it.

### State we could not reach

One conversation degraded until every call timed out at 20 seconds, while a fresh session answered in 5.7 seconds. Clearing the Strands session store did not help, because **AgentCore keeps its own state per `runtimeSessionId`** and there is no API to reset one.

The answer was to make the session id versionable:

```python
SESSION_EPOCH = "2"

def session_id(sender: str) -> str:
    seed = f"{sender}:{SESSION_EPOCH}"
    return f"tg-{sender}-{hashlib.sha256(seed.encode()).hexdigest()[:24]}"
```

Bumping the epoch abandons every degraded session and starts clean ones. If you deploy long lived agent sessions keyed on a user id, build this in from the start.

## What we deliberately have not built

- **No proof of personhood.** A Telegram account is free. For a system that dispatches people to hospitals, that is the real gap. AgentCore Policy with Cedar rules at a Gateway is the right answer and it is not built.
- **No authorization model.** The webhook secret proves Telegram sent the message. It proves nothing about the human behind it.
- **No cross-channel identity.** The same person on email and Telegram are two unrelated identities.
- **No evaluation harness.** Agent behaviour is covered by unit tests and stubs, not scored runs.

We also never store Aadhaar numbers. Verification discards them, because AWS has no managed data identifier for them and a system that cannot mask a value should not hold it.

One privacy detail that took a while to notice: Strands prints agent reasoning to stdout by default, and on Lambda stdout is CloudWatch. Every agent in the system is constructed with `callback_handler=None`, or donor names, dates of birth and blood groups would land in plaintext logs. A CloudWatch Logs data protection policy is the backstop, not the fix.

## What I would tell someone starting this

The interesting question in agent design turned out not to be what the model can decide. It is what the model **must not** decide. Every routing decision we moved out of the model and into a deterministic node made the system easier to trust, easier to test, and easier to explain to someone who would be affected by it being wrong.

The two agents that remain are doing judgement and language, which is what they are for.

And an agent's failure modes are mostly operational. Nothing that went wrong in production was a reasoning failure. It was a 30 second integration cap, two retry layers multiplying, and session state in a place we did not think to look.

## Try it

- Bot: [t.me/donorpanelbot](https://t.me/donorpanelbot)
- Site: [d2ljcqat7a9ftn.cloudfront.net](https://d2ljcqat7a9ftn.cloudfront.net)
- Code: [github.com/iHiteshAgrawal/donorpanel](https://github.com/iHiteshAgrawal/donorpanel)

Built with Strands Agents, Amazon Bedrock AgentCore Runtime and Memory, AWS Lambda, API Gateway, EventBridge Scheduler, S3, CloudFront, Amazon Location and SES.
