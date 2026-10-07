# Worked turns

Three transcripts with the reasoning behind them: a vague answer, a choice with
a real trade-off, and an answer that contradicts an earlier one. Read one when
the method in `interview-method.md` is not concrete enough for the turn in front
of you — not before, and not all three at once.

## Worked turn 1 — the vague answer

The PM has said the app is "for lending, in India, consumer facing", and nothing
about scale.

> **Domain 1 of 14 — product context.** Four questions, then I will write down what
> we have and move on to what the app is made of.
>
> **1. How many people do you expect using it in the first three months, and by the
> end of year one?** A range is fine. I ask because it changes the answer to almost
> everything downstream, and being out by a factor of ten in either direction is
> expensive: too small and it falls over at launch, too large and you pay for
> capacity that sits idle. If you genuinely do not know, say so and I will size for
> a stated assumption and mark it as one.
>
> **2. When it is down, what actually happens?** Not a percentage — tell me what
> breaks for a customer. "Someone cannot finish a loan application and comes back
> later" and "a disbursement fails halfway and money is in limbo" lead to completely
> different architectures, and the second one is worth several times the first in
> infrastructure.
>
> **3. Is there a launch date that is fixed?** I would default to assuming the date
> moves and the scope does not. If it is the other way round, say so now, because it
> changes what I recommend — a fixed date pushes us toward managed services we can
> stand up in days rather than a platform we build properly over weeks.
>
> **4. If we lost the last hour of data, would that be an inconvenience or an
> incident?** I default to assuming an incident for anything financial, which means
> a recovery point of minutes rather than hours, and that costs real money in
> database configuration. Worth confirming rather than assuming.
>
> Next: what the application is actually made of.

What that turn does that a naive one does not:

- Question 2 refuses to ask for an SLA number. Asking a PM for "99.9 or 99.95" gets
  you a number they picked to sound serious. Asking what breaks gets you the truth,
  and you convert it to a target yourself.
- Question 1 pre-authorises "I don't know" and says what happens then. Without that,
  people guess, and a guess recorded as an answer is worse than a recorded unknown.
- Question 3 states a default and asks only to have it overturned. That is faster
  than an open question and it surfaces disagreement immediately.
- Question 4 names the cost consequence. "Recovery point objective" means nothing;
  "that costs real money in database configuration" means something.

## Worked turn 2 — the choice with a real trade-off

Domain 6, compute platform. Domain 14 has already said two engineers, nobody
carrying a pager. Domain 3 has named PCI-DSS.

> **Domain 6 of 14 — what runs the code.** Given two engineers with no dedicated
> ops and PCI in scope, this is the decision I would spend the most time on, because
> it sets the shape of five other domains.
>
> **My recommendation: managed Kubernetes, one cluster, with the cardholder path in
> its own namespace and its own node group.** The reasoning, plainly:
>
> - *Not self-managed Kubernetes.* Somebody has to patch the control plane, hold an
>   etcd backup they have actually restored from, and rotate certificates before they
>   expire. With two engineers and no pager, that work does not happen, and the way
>   you find out is an expired certificate on a Sunday. This is not a close call.
> - *Not serverless containers alone.* They would genuinely be simpler, and if PCI
>   were not in scope I would recommend them. The problem is segmentation evidence:
>   you will need to show an assessor where the cardholder boundary is, and that is
>   harder to demonstrate when the platform owns the network.
> - *Not one cluster per environment.* Three control planes and three node floors on
>   your budget is most of the budget. One cluster with namespace separation for
>   non-production, and production genuinely separate, gets the isolation where it
>   matters.
>
> **What this costs you**, so it is on the record: a managed control plane is a fixed
> monthly charge you pay whether you use it or not, and Kubernetes is a body of
> knowledge two people now have to hold. If either of those is unacceptable, the
> honest alternative is serverless containers plus a longer conversation with your
> assessor about scope.
>
> **Three questions to settle it:**
>
> 1. Managed Kubernetes, or shall I cost the serverless option as well so you can
>    compare? I default to costing both when a budget is tight.
> 2. Are you willing to run non-production on spot capacity? Roughly two thirds off
>    that compute, at the cost of instances disappearing without warning. My default
>    is yes for non-production, never for production.
> 3. Who applies a cluster upgrade, and in what window? I default to a monthly
>    patch window with the provider's automatic minor upgrades off, because an
>    unattended upgrade on an unattended cluster is how a two-person team loses a
>    weekend.
>
> Next: networking, where PCI will do most of the talking.

What makes this turn work is that it rejects options *by name and with a reason*, and
one of the rejections concedes that the rejected option would be better in a
different situation. That is what makes the recommendation credible rather than
tribal, and it is exactly the material `architecture-spec.md` needs for its
"alternatives rejected" section — write it once, here, and reuse it.

## Worked turn 3 — the answer that contradicts an earlier one

Domain 13. The ceiling has just come back as 40,000 a year, and domain 12 already
recorded a warm-standby DR posture.

> Before we go on, that budget contradicts something we already decided, so let me
> put the arithmetic in front of you rather than quietly resizing things.
>
> 40,000 a year is about 3,300 a month. The warm standby we agreed in domain 12 means
> a second environment running continuously in another region — that is roughly a
> second copy of production, so it consumes something close to half the total on its
> own before the primary has run a single request.
>
> Three ways out, and they are genuinely different rather than three flavours of the
> same thing:
>
> 1. **Keep warm standby, cut elsewhere.** Non-production on spot and shut down
>    overnight, single zone outside production, retention down from a year to ninety
>    days. Saves perhaps a third of the non-production spend. Costs you slower
>    non-production and a shorter investigation window.
> 2. **Step down to pilot light.** Infrastructure defined and data replicated, but
>    nothing running until it is needed. Roughly a quarter of the standby cost. Costs
>    recovery time — call it two to four hours rather than minutes. This only works
>    if the recovery target we recorded in domain 1 actually allows it, and it says
>    four hours, so it does.
> 3. **Raise the ceiling.** Say what the number needs to be and I will price the
>    warm standby honestly so you can take that to whoever owns the budget.
>
> **I would recommend 2**, because your recorded recovery target already permits four
> hours, which means we were buying a capability nobody asked for. That is the
> cheapest kind of saving: it costs you nothing you had actually decided you needed.
>
> Whichever you choose, I will re-run the checks, because changing the DR tier can
> break the recovery target and I would rather find that now.

The move that matters: the contradiction is surfaced *immediately*, with arithmetic,
and the recommendation is grounded in an answer the person already gave. Silently
resizing to fit a budget is how a specification ends up promising something the
infrastructure cannot do.
