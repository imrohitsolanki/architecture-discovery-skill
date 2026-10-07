# How to run a turn

Read this when you are unsure how to shape a question, how to weigh a trade-off, or
what to do when an answer is vague. It is method, not script, so it covers the
situations no example anticipates.

Three worked transcripts live in `interview-examples.md`. Read one only when this
file is not concrete enough for the turn in front of you.

## The shape of a good turn

A turn does four things: it says where you are, asks three to five questions, gives
each one a recommended default with the trade-off, and ends by saying what comes
next. Anything else is decoration.

Why a default on every question: the person answering is frequently not technical,
and "what ingress controller do you want?" is not a question they can answer. "I'd
default to ingress-nginx because it is the most widely deployed and your team will
find answers to problems easily; Traefik is nicer to configure but a smaller
community" is a question they *can* answer, because it has been turned into a choice
about consequences rather than a quiz about tools.

Why three to five: past five, answers get shorter and worse. A person answering ten
questions gives you two considered answers and eight shrugs, and you cannot tell
which is which afterwards.

## Weighing a trade-off

When two options both look defensible, these are the questions that actually decide
it. In roughly this order of weight:

1. **Who operates it at 3am, and do they exist?** This dominates. A technically
   superior option that nobody can run is not superior. Domain 14's answers should
   change your recommendation in domains 6, 8, 9 and 10, and if they never do, you
   are not using them.
2. **What happens on the bad day?** Compare failure modes, not feature lists. The
   question is not which is better when working, but which is recoverable when not,
   and by whom.
3. **What does it cost to leave?** A managed service with a proprietary API costs
   more to leave than one that speaks a standard protocol. Worth paying something to
   avoid, not worth paying anything to avoid.
4. **Is the cost fixed or proportional?** A fixed monthly charge is brutal at small
   scale and irrelevant at large. A per-request charge is the reverse. Match the
   shape of the cost to the shape of the load, and say which you are doing.
5. **Can the team hire for it?** A tool with a small community means every problem is
   solved from first principles. That is a real recurring cost, and it is the honest
   reason to pick the more boring option.

## Run it or buy it

Almost every category in this skill offers a self-hosted tool and a managed
equivalent, which is why they sit in the same table rather than in separate sections.
The choice is rarely about the software.

Buy the managed version when the team is small, the component is not what the
business competes on, and the failure mode is one you would not want to debug under
pressure. Run it yourself when the managed version cannot meet a residency or
regulatory constraint, when the cost at your scale is genuinely absurd, or when the
component *is* what the business competes on and you need control of it.

Two things that are usually mistakes:

- Self-hosting a database to save money. The saving is real and the operational
  burden is larger than it looks, and it lands on whoever is on call rather than on
  whoever chose it.
- Buying a managed service for something the team already runs well. Migration is a
  cost, familiarity is an asset, and "managed" is not a virtue in itself.

**On-premises raises the bar rather than removing it.** If domain 4 lands on owned
hardware, somebody replaces a failed disk, owns firmware and switch configuration,
capacity-plans without an elastic escape hatch, and holds the storage layer. That is
more required headcount and a wider skill mix than the cloud equivalent, not less. Say
so during the interview rather than discovering it in domain 14, and if the team
cannot cover it, that is a finding to record and not a detail to work around.

## When an answer is not an answer

- **"Whatever you recommend."** Take it, state the default, record it as a default
  rather than a decision, and move on. Do not push for engagement they do not have.
- **"It needs to be really scalable."** Ask what number. If none comes, propose one
  as an assumption and put it in `open-questions.md` with an owner. A stated
  assumption can be argued with; a vague requirement cannot.
- **"We'll definitely need Kubernetes."** Ask what for. Sometimes there is a real
  reason. Sometimes it is a preference wearing a requirement's clothes, and it is
  cheaper to find out now than to record it as a constraint.
- **A number that seems wrong.** Say so once, with the arithmetic, and then accept
  their answer if they repeat it. Record it as their decision. It is their business,
  and your job is to make sure they chose it knowingly.
