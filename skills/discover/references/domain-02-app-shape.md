# Domain 2 — Application shape

**Does not block.** A reasonable default exists: a single service, containerised,
with one relational database. Most projects that cannot answer this yet are that.

## Pre-filled from the repository

`detect_conventions.py` reports language manifests, Dockerfiles and a service-count
heuristic based on how many directories contain a Dockerfile. Present these as
inferences and confirm. If the repository holds an existing application, read it
before recommending a shape — a recommendation that contradicts the code is an
argument you will lose and should.

## Questions

**1. Monolith, several services, or functions?** Options with the trade-off:

| Option | When it wins | Trade-off |
|---|---|---|
| Single deployable (monolith) | Small team, one domain, launch speed matters | Scales as one unit; a hot path forces you to scale everything |
| Several services | Distinct domains with different scaling or compliance needs, or teams that must deploy independently | Every boundary adds network calls, failure modes and operational surface. Below roughly five engineers this usually costs more than it returns |
| Functions (FaaS) | Spiky or infrequent load, event-driven work, small scope | Cold starts, execution ceilings, and per-invocation cost that is excellent at low volume and poor at sustained high volume |
| Batch or scheduled | Reporting, reconciliation, ML training | Needs a scheduler and a failure story. Frequently forgotten until launch week |

Default: single deployable unless there is a specific reason. State that a service
boundary is cheap to add later and expensive to remove.

**2. What holds state?** Enumerate rather than asking "which database":

| Need | Options | Note |
|---|---|---|
| Relational | PostgreSQL, MySQL or MariaDB | Default PostgreSQL absent a reason. Domain 12 decides managed versus operator |
| Document | MongoDB, DocumentDB, PostgreSQL with JSONB | JSONB often removes the need for a second engine entirely |
| Cache or ephemeral | Redis, Valkey, KeyDB, Memcached | Confirm whether it is a cache that can be lost or a store that cannot. This is asked wrong more often than any other question here |
| Search | OpenSearch, Elasticsearch, PostgreSQL full-text | Full-text search in the primary database is enough far more often than it is used |
| Analytical | ClickHouse, BigQuery, Redshift, a read replica | A read replica delays the need for a warehouse considerably |
| Object storage | S3, GCS, Azure Blob, MinIO, Ceph RGW | MinIO or Ceph on owned hardware |
| Time series | Prometheus, VictoriaMetrics, TimescaleDB, InfluxDB | If this is application data rather than telemetry, say so — it changes retention |

**3. Anything asynchronous?** Queue, stream or scheduled work.

| Option | When it wins | Trade-off |
|---|---|---|
| Managed queue (SQS, Pub/Sub, Service Bus) | Simple work distribution | Provider-specific API; ordering and exactly-once semantics vary and are usually misunderstood |
| RabbitMQ | Routing patterns, established team knowledge | A component you now operate |
| Kafka, Redpanda, Strimzi | Real event streaming with replay, multiple consumers | Substantial operational weight. Frequently chosen for what a queue would do |
| NATS | Lightweight messaging, low operational cost | Smaller ecosystem |
| Cron, Kubernetes CronJob, EventBridge | Scheduled work | Needs a failure and alerting story or it fails silently for months |

**4. Real-time to the browser?** WebSockets, server-sent events or long polling
change the ingress and connection-draining story in domain 7, so this needs asking
even though it sounds like an application detail.

**5. Any ML or GPU work?** Its own node group, its own cost profile, and often its
own data-residency question. Easy to leave out and expensive to add later.

## Gating consequences

- **Functions** closes the node-strategy and ingress-controller branches in 6 and 7,
  and opens cold-start tolerance, concurrency limits and per-invocation cost.
- **Single deployable plus a team of two or fewer** biases domain 6 toward serverless
  containers over Kubernetes, and closes the service-mesh branch in 7.
- **Several services, eight or more** opens service discovery and inter-service
  authentication in 7 and 8.
- **A cache that cannot be lost** is not a cache. It becomes a data store in domain
  12, with backup and a recovery point.
- **GPU or ML work** opens a dedicated node group in 6 and its own line in 13.

## What to write

```json
"02-app-shape": {
  "status": "complete",
  "answers": {
    "shape": "monolith | services | functions | mixed",
    "service_count": 1,
    "stack": ["language and framework"],
    "datastores": ["postgresql", "redis-as-cache"],
    "async": ["sqs"],
    "realtime": "none | websockets | sse",
    "ml_gpu": "none | description"
  }
}
```
