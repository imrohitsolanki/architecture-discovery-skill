# Domain 10 — Observability

**Does not block.** A default exists: metrics and logs centralised with a retention
period, alerts routed to somebody who has agreed to receive them.

The question people forget is the cost of the telemetry itself. Observability is
routinely among the largest single lines in a cloud bill, and retention multiplied
by cardinality is what drives it. Ask about cost here, not in domain 13.

## Pre-filled from the repository

`detect_conventions.py` reports kube-prometheus-stack, VictoriaMetrics, Thanos, Loki,
OpenSearch or Elasticsearch, Fluent Bit, Fluentd, Vector, Promtail, Grafana,
OpenTelemetry, Tempo or Jaeger, and Alertmanager. Absence of metrics or logs is
reported as a gap with what to ask, because "how is a production incident
investigated today" is more useful than a proposal.

## Metrics

| Option | When it wins | Trade-off |
|---|---|---|
| Prometheus, usually via kube-prometheus-stack | The default on Kubernetes; enormous ecosystem of exporters and dashboards | Single-node storage, so long retention and high availability need Thanos, Mimir or Cortex. Cardinality mistakes are expensive and easy |
| VictoriaMetrics | Better compression and resource use, drop-in Prometheus compatibility | Smaller community; fewer worked examples |
| Thanos | Long retention and global query over Prometheus | Several components, and object storage costs |
| Mimir, Cortex | Horizontally scalable Prometheus-compatible storage | Substantial operational weight; disproportionate for one project |
| Managed Prometheus (AMP), Cloud Monitoring, Azure Monitor | Nothing to operate | Per-sample or per-metric cost that grows quietly; less control over retention |
| CloudWatch metrics | Already there for AWS resources | Expensive per custom metric; a weaker query language |

## Logs

| Option | When it wins | Trade-off |
|---|---|---|
| Loki | Cheap by design — indexes labels, not content; pairs with Grafana | Full-text search is weaker than Elasticsearch. Label cardinality is the thing that breaks it |
| OpenSearch or Elasticsearch | Real full-text search and analysis | Heavy: memory-hungry, and storage grows fast. The most common source of surprise cost |
| ClickHouse | Very efficient at large log volume, SQL access | Not purpose-built for logs; more assembly required |
| CloudWatch Logs, Cloud Logging | Nothing to operate, already integrated | Ingest and retention charges add up quickly at volume |

Shippers:

| Option | When it wins | Trade-off |
|---|---|---|
| Fluent Bit | Light, fast, the current default on Kubernetes | Configuration is its own dialect |
| Fluentd | Richer plugin ecosystem | Heavier; Fluent Bit covers most needs |
| Vector | Excellent transformation, good performance | Newer; another configuration language |
| Promtail | Named so it is rejected rather than adopted | Deprecated by Grafana. Do not start here; use the Loki-supported alternative |

## Traces

Default: OpenTelemetry for instrumentation and collection regardless of backend, so
the backend stays replaceable.

| Option | When it wins | Trade-off |
|---|---|---|
| Tempo | Pairs with Grafana and Loki; cheap object-storage backend | Query by trace ID primarily; less ad-hoc analysis |
| Jaeger | Mature, good UI | Storage backend is a separate decision |
| Zipkin | Simple, long-established | Smaller ecosystem now |
| X-Ray, Cloud Trace | Nothing to operate | Provider-specific; sampling controls are coarse |

Tracing is the one that gets deferred most and pays back most in a distributed
system. Ask whether it is wanted at launch or later, and record the answer.

## Dashboards, alerting and on-call

- **Grafana** is the default front end for all of the above.
- **Alertmanager** for routing if Prometheus is in the stack.
- **Where do alerts go?** This is the question that matters. An alert to a shared
  inbox nobody watches is not an alert. Options: Grafana OnCall, PagerDuty or
  Opsgenie (commercial), or a chat channel with an agreed response expectation.
- **Who receives it at 2am?** Cross-check against domain 14. If the answer is nobody,
  then alerting is a dashboard, and the specification should say so rather than
  implying a response that will not happen.

## SLO tooling

Optional, and worth it once there is an availability target from domain 1 that
someone is accountable for. Sloth generates Prometheus rules from an SLO
specification; Pyrra provides a UI over the same idea; OpenSLO is a vendor-neutral
format. Skip it at launch unless the target is contractual.

## The cost question, asked here

Four questions that between them determine most of the bill:

1. **Retention per signal.** Metrics, logs and traces each need a number. A
   compliance regime may set a floor — PCI-DSS wants twelve months of logs with three
   immediately available — and where it does, that floor is not negotiable and needs
   pricing.
2. **Sampling.** Traces are usually sampled; logs sometimes should be. Say the rate.
3. **Cardinality.** A label with a user ID or a request ID in it will multiply the
   series count without limit. This is the single most common cause of an
   observability bill nobody predicted.
4. **What is actually looked at?** Retaining a signal nobody queries is paying to
   store data to delete later.

## Gating consequences

- PCI-DSS sets twelve-month log retention with three months immediately available,
  and requires the logs be tamper-evident. That is a cost line, not a checkbox.
- GDPR and DPDP pull the other way: personal data in logs is subject to erasure, so
  either keep it out of logs or have a deletion path that reaches them. Naming the
  conflict is the job here, not resolving it silently.
- RBI, SEBI and IFSCA add incident detection and reporting obligations with
  deadlines, which means the alerting path has to be able to scope what was affected.
- Nobody on the pager, from domain 14, means alerting is a dashboard. Record it.

## What to write

```json
"10-observability": {
  "status": "complete",
  "answers": {
    "metrics": "kube-prometheus-stack, 15d local",
    "logs": "Loki with S3 backend",
    "traces": "OpenTelemetry Collector to Tempo, 10% sampled",
    "shipper": "Fluent Bit",
    "dashboards": "Grafana",
    "retention": {"metrics": "15d", "logs": "12 months", "traces": "7d"},
    "retention_driver": "PCI-DSS requires 12 months of logs",
    "alert_routing": "Alertmanager to Grafana OnCall, escalating to phone",
    "on_call": "two engineers, weekly rotation, business hours only",
    "telemetry_cost_estimate": "included as a line in domain 13"
  }
}
```
