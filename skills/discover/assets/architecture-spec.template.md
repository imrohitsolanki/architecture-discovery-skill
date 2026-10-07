# Architecture specification — {{project name}}

| | |
|---|---|
| Status | Draft for review \| Approved |
| Version | {{n}} |
| Date | {{YYYY-MM-DD}} |
| Interview with | {{names and roles}} |
| Author | {{name}} |
| Signed off by | {{name, or "not yet"}} |

> This document advises. It does not certify. Every compliance mapping below states
> the proposed control and the evidence an assessor would ask for, and names the
> owner responsible for verifying it. Every cost figure shows its assumptions.

Replace every `{{...}}` marker. Delete any section that does not apply, and say in
one line why it was deleted — an empty section is better than a plausible one, and a
deleted section with a reason is better than either.

## 1. What is being built

{{Two or three paragraphs, in the client's own terms. What the system does, who uses
it, and the scale it is being built for. This is the section a non-technical reader
reads, so no tool names.}}

## 2. Non-functional requirements

| Requirement | Value | Where it came from |
|---|---|---|
| Availability target | {{99.9%}} | {{domain 1: "customers cannot complete a purchase"}} |
| Recovery time objective | {{4h}} | {{stated by {{name}}}} |
| Recovery point objective | {{15m}} | {{stated by {{name}}}} |
| Expected scale at launch | {{figure}} | {{stated \| assumption, see OQ-n}} |
| Expected scale at 12 months | {{figure}} | {{stated \| assumption, see OQ-n}} |
| Launch date | {{date or none}} | {{fixed \| movable}} |

State which of these are assumptions rather than requirements. An assumption can be
argued with; a requirement recorded from a guess cannot.

## 3. Decisions

One subsection per significant decision. Each links to its ADR in `decisions/`.

### 3.n {{Decision title}}

**Choice:** {{what was chosen}}

**Why:** {{the reasoning, in this project's terms — not general advantages of the
technology}}

**Alternatives rejected:**

| Alternative | Why not here |
|---|---|
| {{option}} | {{reason specific to this project. If it would win in a different situation, say so — that is what makes the recommendation credible rather than tribal}} |

**What this costs us:** {{the honest downside. Every choice has one. A decision
recorded with no downside reads as advocacy}}

**ADR:** [`decisions/ADR-{{nnn}}-{{slug}}.md`](decisions/ADR-{{nnn}}-{{slug}}.md)

## 4. Environment topology

| Environment | Persistent | Isolation | Compute | Zones | Data stores | Notes |
|---|---|---|---|---|---|---|
| {{prod}} | yes | {{vpc}} | {{}} | {{3}} | {{}} | |
| {{staging}} | yes | {{vpc}} | {{}} | {{1}} | {{}} | |

What is shared across environments, and the consequence of that sharing:
{{list, with the failure mode of each shared component}}

## 5. Diagrams

Mermaid, so they diff in git and render in the pull request.

### 5.1 Network topology

```mermaid
graph TD
    subgraph internet[Internet]
        users[Users]
    end
    subgraph vpc["VPC {{cidr}}"]
        subgraph public[Public subnets]
            lb[{{load balancer}}]
        end
        subgraph private[Private subnets]
            compute[{{compute platform}}]
        end
        subgraph isolated[Isolated subnets, no NAT route]
            db[({{database}})]
        end
    end
    users --> lb
    lb --> compute
    compute --> db
```

### 5.2 Delivery flow

```mermaid
flowchart LR
    dev[Developer] -->|push| scm[{{SCM}}]
    scm -->|build, test, scan| ci[{{CI}}]
    ci -->|signed image| reg[{{registry}}]
    reg --> cd[{{CD or GitOps}}]
    cd -->|verified at admission| cluster[{{target}}]
```

### 5.3 Environment promotion

```mermaid
stateDiagram-v2
    [*] --> {{staging}}
    {{staging}} --> {{prod}}: {{gate — same artifact, approval by whom}}
    {{prod}} --> [*]
```

## 6. Security controls

Secure defaults applied by default. Anything absent from this list was not applied,
and appears in section 7 as a waiver.

| Control | How it is implemented | Evidence |
|---|---|---|
| Data stores unreachable from the internet | {{}} | {{}} |
| Compute in private subnets | {{}} | {{}} |
| Least privilege, production write access requested not standing | {{}} | {{}} |
| No long-lived static credentials | {{}} | {{}} |
| Encryption in transit and at rest | {{}} | {{}} |
| Default-deny network policy | {{}} | {{}} |
| Resource requests and limits on all workloads | {{}} | {{}} |
| Backups offsite, restore tested | {{}} | {{}} |

## 7. Waivers

Deviations from the secure defaults, each accepted by a named person.

| Control | Deviation | Reason and alternatives rejected | Compensating control | Owner | Accepted | Review |
|---|---|---|---|---|---|---|
| {{}} | {{}} | {{}} | {{}} | {{}} | {{}} | {{}} |

If there are none, write "None." — do not delete the section. Its absence would be
ambiguous.

## 8. Compliance

One subsection per regime named in the interview. This maps obligations to proposed
controls. **It does not assert compliance**, and verification belongs to the owner
named in each row.

### 8.n {{Regime}} — {{citation}}

**Applicability:** {{who this binds, and the basis on which the client falls inside.
If that is unresolved, say so and reference the open question}}

| Obligation | Proposed control | Evidence required | Owner | Status |
|---|---|---|---|---|
| {{}} | {{}} | {{}} | {{}} | {{addressed \| open, see OQ-n}} |

For a regime this skill has no mapping for, say so plainly and reference the open
question. Do not produce a table of plausible controls.

## 9. Cost

Model: {{cloud \| on-prem}}. Ceiling: {{amount}} {{currency}} {{period}},
{{hard limit \| target}}.

| Item | Low | High | Assumptions |
|---|---|---|---|
| {{}} | {{}} | {{}} | {{region, pricing basis, date checked, what is excluded}} |
| **Total** | {{}} | {{}} | |

**Unpriced items**, labelled rather than guessed:

| Item | What would make it priceable |
|---|---|
| {{}} | {{}} |

Every figure is a planning range derived from the assumptions shown, checked against
the provider's calculator on {{date}}. It is not a quote, and negotiated or
committed-use rates are not visible to it.

{{If over the ceiling: the reductions offered, each with its trade-off, and which was
chosen.}}

## 10. What is not in scope

{{Explicit list. This section prevents the most expensive kind of misunderstanding,
and it is the one most often omitted.}}

## 11. Open questions

See [`open-questions.md`](open-questions.md). {{n}} open, {{n}} blocking.

## 12. Validation

Gates run on {{date}} against `discovery-state.json`:

| Gate | Result |
|---|---|
| Completeness | {{}} |
| Contradictions | {{}} |
| Compliance | {{}} |
| Cost | {{}} |
| Secret scan | {{}} |

{{Any gate that failed, and why it was accepted — or state that all passed.}}
