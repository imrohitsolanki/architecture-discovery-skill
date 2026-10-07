# {{Project name}} — what we are building, in plain language

For the product or project manager. No tool names where a plain phrase will do, and
where a tool name is unavoidable, one line explaining what it does.

Written on {{date}} from the discovery session with {{names}}. The full technical
detail is in [`architecture-spec.md`](architecture-spec.md); this page is the summary
you can take to somebody who owns a budget.

## What this is

{{Two or three sentences. What the system does and who it serves.}}

## What we are building to run it

{{Four or five bullets, each one sentence, no jargon. For example: "A managed
Kubernetes cluster — a service that runs your application containers and restarts
them if they fail, without us having to maintain the servers underneath."}}

## What it will cost

{{Amount}} {{currency}} per {{period}}, {{as a range}}, against your stated ceiling
of {{amount}}.

| What | Roughly | Why this much |
|---|---|---|
| {{}} | {{}} | {{one line a non-specialist can follow}} |

These are planning figures worked out from stated assumptions, not quotes. The
assumptions are listed in the technical specification, and if one of them is wrong the
figure moves. {{If any item could not be priced: name it and say what we need in order
to price it.}}

{{If over the ceiling: say so directly here, with the options and what each costs in
capability. Do not bury it.}}

## What we need from you

| What | Why we need it | By when | Who |
|---|---|---|---|
| {{}} | {{}} | {{}} | {{}} |

## What is still undecided

{{The open questions that affect this reader, in their language. For each: what
happens by default if nobody decides, and by when that default takes effect. Leave
the ones that only affect engineers in open-questions.md.}}

## What this means for the timeline

{{Honest assessment. Which parts are quick, which are slow, and what is on the
critical path. If a compliance requirement or a piece of missing information will
delay things, say so here — this is the section that prevents the conversation where
everyone is surprised.}}

## What we are deliberately not doing

{{And why. Prevents the most expensive misunderstanding.}}

## Where the detail lives

- [`architecture-spec.md`](architecture-spec.md) — full technical specification
- [`decisions/`](decisions/) — one page per significant decision, with what was
  rejected and why
- [`open-questions.md`](open-questions.md) — every open item with an owner and a date
