# Demo video script

Target 5:00. Two windows: **Telegram** (phone frame or desktop app) and a **browser** with the
landing page. Architecture diagram as a third tab.

**Before recording**

1. Clear the chat with Asha so the conversation starts from nothing.
2. Bump `SESSION_EPOCH` or clear `sessions/session_chat-<your id>/` so the first reply is fast.
3. Send one throwaway message and wait for the reply. This warms the Lambda and the AgentCore
   Runtime; a cold start after a deploy blows past the timeout and the first reply looks broken.
4. Open the landing page and leave it on screen. Note the donor count.
5. Check `curl https://ypw5w9sz6g.execute-api.ap-southeast-2.amazonaws.com/api/public` returns 200.

Replies land in about 4 seconds. Do not cut them out. A judge seeing a real round trip is worth
more than a tight edit, and jump cuts around every reply read as hiding latency.

---

## 0:00 - 0:40 The problem

**On screen:** landing page.

> A child with thalassemia major needs matched blood every two to four weeks. Not once. For life.
>
> In India there are over a hundred thousand of them, and their families arrange the donors
> themselves. Every fortnight. Forever.
>
> The obvious fix is a bigger registry. Registries already exist, and they are mostly dead. Only
> about half of registered donors are reachable when they are finally called.
>
> So the database was never the bottleneck. The bottleneck is coordination work, and it lands on a
> parent whose child is due on Thursday.

---

## 0:40 - 1:55 The product, live

**On screen:** Telegram, full frame. Type each message live.

> This is Asha. There is no dashboard and no account. It is a Telegram bot.

Send: **`Hi`**

Let the reply land.

Send: **`I'm O+, can I donate to B+?`**

> That answer does not come from the model. It comes from a tool.
>
> Early on, Asha got this exact question wrong three times in a row. She said no. The answer is
> yes. For a system that sends people to hospitals, a confident wrong answer is the entire risk,
> so blood compatibility is now a deterministic tool and the model is instructed to state its
> verdict verbatim.

Send: **`who can I help?`**

> A second tool, because the reverse question is one a pairwise comparison cannot answer.

Send: **`I'd like to register`**

Answer her questions as she asks them: name, city, blood group, consent.

**Switch to the browser. Reload the landing page.**

> The counter just moved. That number is read out of S3, not held in the page.

---

## 1:55 - 2:40 The idea that matters

**On screen:** landing page, showing the settled request and the counts.

> Everything so far started because someone opened a conversation. The part that matters is the
> part nobody starts.
>
> Every six hours the system forecasts. A patient on a fixed transfusion cycle is predictable, so
> the last transfusion plus the policy interval is the next one. Requests open before a family
> thinks to ask.
>
> This is a request that already settled. Five donors contacted in ranked order. Two donated, one
> pledged, one declined, one never answered.
>
> That last one is not a flaw in the demo. Roughly half of any registry does not answer, and a
> system that pretends otherwise is lying about the problem it claims to solve.

> The policy says contact at hour zero, widen after a day, once more after two, then stop.
> Stopping is a feature. When the waves run out and the request is still short, that is the signal
> a human is needed, not a reason to keep asking. Donors who decline are never asked again.
>
> A system that spams its donors destroys the reachability it depends on. That is how the existing
> registries died.

---

## 2:40 - 3:45 How it works

**On screen:** architecture diagram.

> A Strands Graph of ten nodes. Only two of them are agents.

Point at the diagram as you go.

> `verify` reads the request against the patient's history and returns a typed verdict through
> structured output. `compose` writes the message a stranger will actually read.
>
> Everything else is deterministic Python. Eligibility, ranking, the branch after verification,
> and the decision to send.
>
> The graph's edges read JSON out of node output, never free text. A model's prose never decides
> where a request goes.

> This node is the autonomy gate, and it is what makes this an agent rather than a workflow. A
> routine scheduled transfusion dispatches on its own. The run stops and asks a human when the
> request is an emergency, when the verifier raised a concern, when the cohort is too small for
> the units needed, or when a donor would go over their monthly contact budget.

---

## 3:45 - 4:25 On AWS

**On screen:** architecture diagram, AWS side. Optionally the AgentCore console.

> Asha runs on Bedrock AgentCore Runtime: one agent, one request, one response, a dedicated
> session per person.
>
> The request graph runs in Lambda, because it is the opposite shape. Ten nodes, up to a minute,
> and nobody waiting on it.
>
> AgentCore Memory keeps what is worth remembering after a conversation ends, with two strategies
> keyed on the person. Writes take two paths on purpose: facts we already hold exactly are written
> directly and readable in about a second and a half, while patterns worth mining from
> conversation go through async extraction and take about seventy. Paying a model to re-derive a
> number we already have would be slower and worse.
>
> EventBridge Scheduler drives the six-hourly tick. CloudFront and S3 serve the page.

---

## 4:25 - 4:50 Honest about what it is not

**On screen:** README security section, or back to Telegram.

> Two things I want to be straight about.
>
> There is no proof of personhood. A Telegram account is free, and for a system that dispatches
> people to hospitals that is the real gap. AgentCore Policy with Cedar rules is the right answer
> and it is not built.
>
> And the demo donors are fictional, so their outreach routes to my own phone. The API calls and
> the delivery receipts are real. Only the recipient is shared.

---

## 4:50 - 5:00 Close

**On screen:** landing page.

> DonorPanel holds the network so no family has to browse it, and does the asking so no family has
> to.
>
> It is live. The link is in the description.

---

## If you need to cut to 3 minutes

Drop 3:45 to 4:25 entirely and compress 2:40 to 3:45 into thirty seconds on the diagram. Keep the
live Telegram section and the forecast section; they carry Design and Impact, which are two of the
five criteria on their own.

## Do not

- Do not speed up or cut around the replies. Real latency, shown, beats hidden latency.
- Do not open a request for blood live unless you want the outreach messages arriving on the same
  phone mid-recording.
- Do not read the architecture section off the diagram word for word. Point at three things.
