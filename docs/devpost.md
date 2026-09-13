# DonorPanel

**Asha finds blood donors, so families don't have to.**

| | |
| --- | --- |
| Try it | [t.me/donorpanelbot](https://t.me/donorpanelbot) |
| Site | [d2ljcqat7a9ftn.cloudfront.net](https://d2ljcqat7a9ftn.cloudfront.net) |

## Inspiration

A child with thalassemia major needs matched blood every two to four weeks. Not once. For life.

In India there are between 100,000 and 150,000 of them, and their families arrange the donors
themselves. Every fortnight. Forever. A parent spends the week before each transfusion calling
people, posting in WhatsApp groups, and asking relatives to ask their relatives.

The instinct is to build a registry. Registries already exist, and they are mostly dead. Only 55
to 60 percent of registered US marrow donors are reachable and available when finally called, and
attrition runs 60 percent among minority donors against 40 percent among white donors. NHSBT
supplies 3,600 units of Ro blood a month against a need of 7,400.

So the database was never the bottleneck. **The bottleneck is coordination labour, and it lands on
whoever is least able to carry it:** a parent whose child is due for a transfusion on Thursday.

Matching follows ancestry, which means the pool of donors who can match a given patient is
systematically smaller than the population that needs them. A bigger registry does not fix that. A
system that knows who is genuinely reachable, and asks them before anyone is desperate, does.

## What it does

DonorPanel is a Telegram agent called Asha. There is no dashboard to learn and no account to
create. You message her and she does the rest.

She handles three conversations and works out which one you are from what you say:

| You | She |
| --- | --- |
| "My friend needs a transfusion next week" | Gathers name, city, blood group, units and date, opens a request, searches the network, reports back |
| "I'd like to help" | Registers you, geocodes your city so distance ranking works |
| (answering her outreach) | Records your pledge or decline, tells you the hospital and the date |

The part that matters is the one nobody starts a conversation for. **Every six hours the system
forecasts.** A patient on a fixed transfusion cycle is predictable, so last transfusion plus the
policy interval is the next one. Requests open before a family thinks to ask, donors are contacted
in ranked waves, and the whole thing runs with nobody watching.

That is the difference between an SOS broadcast and a panel. An SOS asks everyone at once, in a
crisis, and burns the network's goodwill. A panel asks eight people in a considered order, a week
early, and stops when it should.

## How we built it

A Strands `Graph` of ten nodes. **Only two are agents.**

```
intake -> verify -> adjudicate -+-> accept -> eligibility -> rank -> compose -> gate -> dispatch
                                 \-> close
```

Every node that decides routing is deterministic Python, subclassing `MultiAgentBase`. The two
agents do the two things models are actually good at: `verify` reads a request against the
patient's history and returns a typed `Verdict` through structured output, and `compose` writes
the outreach message a stranger will read.

**Graph edges read JSON blocks out of node output, never free text.** A model's prose never
decides where a request goes. `adjudicate` turns the verdict into a branch and fails closed.

### The autonomy gate

This is what makes it an agent rather than a workflow. A routine scheduled transfusion dispatches
on its own. The run stops and asks a human when the request is an emergency, when the verifier
raised a concern, when the matched cohort is too small for the units needed, when a donor would
exceed their monthly contact budget, or when no drafts were produced.

Escalation reasons are written for a coordinator, then translated into plain language before they
reach whoever asked.

### Knowing when to stop asking

`policies/*.yaml` declares `escalation_hours: [0, 24, 48]`. Contact the first cohort immediately,
widen after a day, once more after two, then **stop**.

Stopping is the feature. When the waves are exhausted and the request is still short, that is the
signal a human is needed, not a reason to keep asking. Donors who declined are never asked again,
and `max_contacts_per_donor_month` caps how often anyone hears from us at all. A system that
spams its donors destroys the reachability it depends on, which is precisely how the existing
registries died.

`thalassemia-india` and `sickle-cell-uk` are the same product with different numbers.

### On AWS

| Piece | Why there |
| --- | --- |
| **AgentCore Runtime** hosts Asha | One agent, one request, one response, a dedicated session per person |
| **Lambda** runs the graph | The opposite shape: ten nodes, 30 to 70 seconds, nobody waiting |
| **AgentCore Memory** | Two strategies, `userPreference` and `semantic`, keyed on the person |
| **EventBridge Scheduler** | The six-hourly tick: close, forecast, chase |
| **API Gateway + CloudFront + S3** | Telegram webhook and the landing page |

Memory writes take two paths on purpose, because their latencies differ by fifty times. Facts we
already hold exactly, like cohort size and the gate decision, go through
`BatchCreateMemoryRecords` and are readable in ~1.5s. Patterns worth mining from conversation go
through `CreateEvent` and async extraction, readable in ~70s. Paying a model to re-derive a number
we already have would be slower and more expensive for a worse answer.

If AgentCore Runtime is unreachable, the Lambda answers in process with identical code. A Runtime
outage costs the architecture story, not the demo.

## Challenges we ran into

**A blood compatibility answer that was confidently wrong, three times.** Asked whether O+ can
donate to B+, the agent said no. It can. Three causes stacked: there was no tool for the question,
so the model answered from its own knowledge; the session had persisted its earlier wrong answers,
so it anchored on them and said "as previously mentioned"; and nothing told it to correct itself.
The fix was a `blood_compatibility` tool that returns a verdict the model is told to state
verbatim, plus `who_can_i_help` for the reverse question a pairwise tool cannot answer. For a
system that dispatches people to hospitals, a plausible-sounding wrong answer is the whole risk,
and the lesson was that the fix belongs in a deterministic tool rather than a better prompt.

**A 30 second cap that cost us a day of Bedrock quota.** An API Gateway HTTP API caps an
integration at 30 seconds, and that is the hard maximum. Our webhook did the model call
synchronously, so a slow reply became a 503. Telegram reads a 503 as "send it again" and
redelivered the same message every two minutes. One greeting became thirteen Lambda invocations,
each billed for a full 300 second timeout. **196 real invocations produced 3,737 throttle
events**, which exhausted the account's daily token budget.

Diagnosing it meant reading CloudWatch rather than guessing, and the guesses were wrong: switching
to a smaller model did nothing, because the cap turned out to be account-wide across Nova Pro,
Lite and Micro, with and without inference profile prefixes, in three regions. The real faults
were architectural. The webhook now acknowledges in 0.03s and replies asynchronously; both retry
layers are bounded; a failed call produces an honest apology instead of silence. **End to end, the
reply went from never arriving to 3.8 seconds.**

**State we could not reach.** One conversation degraded until every call timed out while a fresh
session answered in 5.7s. Clearing the session store did not help, because AgentCore keeps its own
state per `runtimeSessionId` and there is no API to reset one. The answer was a `SESSION_EPOCH`
salt in the session id, so a bad session can be abandoned deliberately.

## Accomplishments that we're proud of

- **The routing is deterministic and we kept it that way** under pressure to let the model decide.
- **The system knows when to stop.** Three waves, then a human. Declined donors are never re-asked.
- **It anticipates.** The forecast pass opens requests before anyone asks, which is the entire
  difference between this and an SOS broadcast.
- **A production failure diagnosed from logs**, with measured before and after, not a guess.
- **137 tests**, with storage on moto, agents stubbed, and the Telegram transport faked.
- **Privacy stated honestly**, including what is not built. Aadhaar numbers are never stored.
  `callback_handler=None` on every agent, because Strands prints reasoning to stdout and on Lambda
  stdout is CloudWatch, which would put donor names and blood groups into plaintext logs.

## What we learned

That the interesting question in agent design is not what the model can decide, but what it must
not. Every routing decision we moved out of the model and into a deterministic node made the
system easier to trust and easier to test. The two agents that remain are doing judgement and
language, which is what they are for.

And that an agent's failure modes are mostly operational. Nothing we got wrong in production was a
reasoning failure. It was a 30 second integration cap, two retry layers multiplying, and session
state in a place we did not think to look.

## What's next

- **Proof of personhood.** A Telegram account is free. For a system that dispatches people to
  hospitals, that is the real gap.
- **AgentCore Policy with Cedar rules at a Gateway.** Today the webhook secret proves Telegram
  sent a message; it proves nothing about the human behind it.
- **Cross-channel identity.** The same person on email and Telegram are currently two strangers.
- **An evaluation harness.** Behaviour is covered by unit tests, not by scored runs.
- **Back onto Bedrock.** The Bedrock path is complete and one environment variable away; the
  deployment runs on OpenRouter today only because of the daily cap described above.

## Built with

`strands-agents` (Graph, `MultiAgentBase`, tools, hooks, structured output, session managers,
retry strategies) · Amazon Bedrock AgentCore Runtime and Memory · AWS Lambda · API Gateway ·
EventBridge Scheduler · S3 · CloudFront · Amazon Location · Python · React · Vite · Tailwind
