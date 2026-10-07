# Evals

Six cases, and all six ask one question: **does the right skill fire, and does the
wrong one stay out of the way?**

## Why this and nothing else

`docs/DISCOVERY.md` states that model behaviour is not evaluated here, and that
remains true of everything that needs a judgement: whether the interview asks good
questions, holds the three-to-five limit, or labels a pre-fill as an inference. A
grader scoring those is slow, noisy and weakly informative, and a suite people stop
believing is worse than no suite.

Routing is not a judgement. A skill either fired or it did not, and
`LIMITATIONS.md` L11 names the exact hazard: every anti-trigger instruction this
plugin has lives in `when_to_use`, and nothing measured whether any of it works. The
two skills also overlap by design — one scopes infrastructure, the other writes it,
and both are about infrastructure that does not exist yet — so the failure that
matters is `iac` firing on a conversation that has not produced a specification, and
generating Terraform from a document nobody agreed.

Each case is a `tool_used` grader over `Skill`: it fires, or it must not.

## Running them

```bash
claude plugin eval . --ablation none
```

`--ablation none` matters: under the default with/without ablation a
`tool_used: Skill` grader becomes a display-only trigger indicator rather than part
of the score, because it can never move the delta between the two arms. Here the
trigger *is* the thing being measured, so the single-arm run is the right one.

Useful flags: `--runs 1` while iterating on wording, `--case 'routing-*'` to select,
`--threshold 1.0` (the default) to fail on any case that is not clean.

**Not in CI.** Every run costs model calls, and the thing being measured — how a
description and a `when_to_use` block read to a model — changes when that text
changes, not when a script does. Run it when either skill's frontmatter changes, and
before a release. `.github/workflows/checks.yml` stays free and deterministic.

`max_turns` is 3, so a run that fired the right skill and then started working is
reported as `exit 1: Reached maximum number of turns` while still scoring 1.00. That
note is expected: the case is answered by the first tool call, and letting the run
continue would spend money on work no grader reads.

A full pass is six cases at 1.00, about $0.5 and under three minutes at `--runs 1`.

## What a failure means

A trigger case failing means the description does not reach a phrasing a client
actually uses. An anti-trigger case failing is the more serious direction: the
plugin is volunteering for work on infrastructure that already exists, where it has
no state file, no interview and no business being involved.

Fix the frontmatter, not the case — unless the case is testing a phrasing nobody
would say, in which case delete it. A case kept because it passes is not evidence.
