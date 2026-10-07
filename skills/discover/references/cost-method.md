# How to produce a cost figure

Read this before writing any number with a currency next to it.

## The rule, and why it is absolute

Never invent pricing. Either derive a range from stated assumptions and show the
arithmetic, or ask, or mark the item unpriced.

The reason is not pedantry. A figure with no assumptions attached cannot be told apart
from one that was made up, and the moment it appears in a document with a currency
symbol beside it, somebody plans against it — a budget gets approved, a client gets
quoted, a decision gets made. When it turns out to be wrong, nobody can reconstruct
what it assumed in order to see where it went wrong. An honest range with visible
assumptions can be corrected; a confident single number cannot.

`check_cost.py` refuses a line item that carries a price without assumptions. That is
a hard failure rather than a warning, because the whole defence rests on it.

## The shape of a line item

```json
{
  "item": "EKS node group",
  "assumptions": [
    "4 x m6i.large, on-demand",
    "ap-south-1 list price",
    "running 24x7",
    "does not include EBS volumes, priced separately"
  ],
  "low": 374,
  "high": 560
}
```

Four things make this usable:

- **The item is specific.** "Compute" is not an item; a named instance type and count
  is.
- **The assumptions name the region and the pricing basis.** Regional prices differ
  materially, and list price is not what a client with a Savings Plan pays.
- **There is a range.** The low end is the steady state, the high end includes the
  headroom or burst you expect. A single number implies a precision you do not have.
- **What is excluded is stated.** The most common estimating error is omission, not
  arithmetic — storage, data transfer and backup are the usual casualties.

## Where the numbers come from

There is no price table in this skill, deliberately. Any table compiled today is
wrong within months, differs by region, and cannot see committed-use or negotiated
rates — and a stale table that looks authoritative is worse than none, because it
removes the prompt to go and check.

So: <https://calculator.aws/> and the equivalent for other providers, at the time of
the estimate, with the region set correctly. Record the date you checked in the
assumptions. If you cannot check, mark the item unpriced.

## Unpriced is a valid answer

```json
{
  "item": "Data transfer",
  "unpriced": true,
  "note": "needs the daily active user figure and an average payload size; tracked as OQ-3"
}
```

Labelled, not guessed. The report lists unpriced items separately so nobody mistakes
the total for complete. Say what would make it priceable, so it becomes a question
with an answer rather than a permanent hole.

## Deriving a range from a stated assumption

Worked, so the method is visible. Suppose domain 1 gave 5,000 daily active users and
nothing else.

1. **State the conversion, and that it is one.** "Assuming 20 requests per user per
   day concentrated over 8 active hours, that is roughly 3.5 requests per second
   average, and I am sizing for 5x that at peak — call it 18 requests per second."
   Every one of those numbers is an assumption and each is written down.
2. **Convert to a resource.** "At 50ms per request and 4 concurrent requests per
   core, 18 per second needs about one core steady state. Two m6i.large gives
   headroom for the peak and one to lose."
3. **Price the resource, with the basis.** Two instances, on-demand, that region,
   checked on a stated date.
4. **Give the range.** Low is two instances; high is four, if the peak assumption is
   out by a factor of two.
5. **Say what would sharpen it.** "A load test against a prototype replaces steps 1
   and 2 with measurements. Until then this is arithmetic over a guess about request
   rate, and the guess is the weakest link."

That last step is what makes the estimate honest. The arithmetic is sound; the input
is a guess, and saying so tells the reader where the risk is.

## The two models

### Cloud — monthly run rate

`"model": "cloud"`. Line items are monthly amounts, and the total is their sum.
Straightforward, and the errors are omissions.

Do not forget: data transfer (cross-zone, NAT gateway processing, internet egress),
storage and snapshots, load balancers, NAT gateways themselves, observability
ingest and retention, and per-cluster or per-service fixed charges. Fixed charges
are brutal at small scale — a per-cluster charge across three environments is three
charges regardless of load.

### On premises — capital plus running costs

`"model": "on-prem"`. A capital purchase cannot be compared to a monthly ceiling
without amortising it, so:

```json
{
  "item": "3 control-plane and 6 worker servers",
  "assumptions": ["Dell R660, 2x Xeon, 256GB", "quoted 2026-09"],
  "capex": 96000,
  "life_years": 5,
  "opex_monthly": 0
}
```

Monthly equivalent is `capex / (life_years x 12) + opex_monthly` — here 1,600 a
month. `check_cost.py` does that arithmetic and shows it.

The recurring costs are where on-premises estimates go wrong, because leaving them
out is how owned hardware comes to look cheaper than it is. The gate reports when a
line for any of these is missing:

- **Power**, and **cooling** which is usually a similar order to power
- **Rack space** or colocation fees
- **Bandwidth** — transit or a commitment. There is no free egress, and no elastic
  escape hatch
- **Hardware support** or spares. A five-year life means failures during it
- **Operations time.** Somebody replaces disks and owns firmware. This is the line
  most often omitted and frequently the largest

Two further asymmetries worth stating in the specification when comparing:

- **Capacity must be bought for peak**, because there is no autoscaling. Cloud lets
  you pay for the average and burst; owned hardware does not.
- **The commitment is longer.** A five-year amortisation is a five-year decision.
  Cloud is expensive per unit and cheap to change your mind about, and that
  optionality has real value when domain 1's growth figure is a guess.

## Sanity checks before you present a number

- Does the total have a data transfer line? If not, it is probably wrong.
- Does it have an observability line? That is often the second largest.
- Are fixed per-cluster or per-service charges multiplied by the environment count?
- Is non-production costed at all, or silently assumed free?
- Is the range wide enough to contain the truth? A ±10% range on an estimate built
  from a guessed request rate is false precision.
- If it is over the ceiling, are the reductions specific to this topology? Generic
  advice is easy to write and easy to ignore. `check_cost.py` generates specific ones
  from the state file.
