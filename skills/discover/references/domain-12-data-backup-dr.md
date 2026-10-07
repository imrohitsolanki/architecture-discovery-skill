# Domain 12 — Data, backup and disaster recovery

**Blocks a final specification.** Recovery time and recovery point are commercial
decisions about what an outage costs, and guessing them sets a budget nobody agreed
to.

Domain 1 should already have both, in plain language. This domain turns them into a
topology and a price.

## Pre-filled from the repository

`detect_conventions.py` reports Velero, CloudNativePG, Patroni, Kafka or Strimzi,
Ceph with Rook, and Longhorn. Absence of any backup tooling is reported as a gap
with what to ask: what is backed up, how often, and when a restore was last tested.

## Database: managed or operator

The decision is dominated by domain 14, not by the software.

| Option | When it wins | Trade-off |
|---|---|---|
| Managed relational — RDS, Aurora, Cloud SQL, Azure Database | Almost always in cloud. Backups, patching, failover and point-in-time recovery are somebody else's job | Costs more per unit than self-hosted, and there are version and extension constraints |
| CloudNativePG | Postgres on Kubernetes done properly; good backup and failover story | You own it. Storage layer becomes yours too |
| Patroni, or the Zalando operator | Established Postgres HA outside or inside Kubernetes | Same, plus more assembly |
| Percona operators (Postgres, MySQL, MongoDB) | Wants operator-managed with commercial support available | Same |
| MariaDB Galera | Multi-primary MySQL-compatible | Write conflicts are subtle and surprising |
| Vitess | MySQL at very large scale with sharding | Substantial complexity; only at genuine scale |
| MongoDB self-hosted with Percona Backup | Existing replica set, or licensing constraints | Backup and restore of a replica set is its own skill |
| Plain database on a VM | A small internal tool | Backups, patching and failover are all yours, and usually neglected |

Non-relational and analytical:

| Need | Options | Note |
|---|---|---|
| Cache | Redis, Valkey, KeyDB, Memcached, ElastiCache, Memorystore | Confirm again whether it is a cache that can be lost. If not, it is a data store and needs everything below |
| Document | MongoDB, DocumentDB, Postgres JSONB | JSONB frequently removes the second engine |
| Wide column | Cassandra, ScyllaDB | Only at scale that justifies it |
| Analytical | ClickHouse, BigQuery, Redshift, or a read replica | A read replica delays a warehouse a long time |
| Search | OpenSearch, Elasticsearch, Postgres full-text | See domain 2 |

Queues and streaming:

| Option | When it wins | Trade-off |
|---|---|---|
| SQS, Pub/Sub, Service Bus | Simple, managed, nothing to run | Provider-specific semantics |
| RabbitMQ | Routing patterns, existing knowledge | You operate it |
| Kafka with Strimzi, or Redpanda | Real streaming with replay and multiple consumers. Redpanda is much lighter to operate | Kafka is heavy. Frequently chosen for what a queue would do |
| NATS | Light messaging, low cost | Smaller ecosystem |

## Storage, when there is no cloud

On owned hardware this is a first-class decision rather than a detail, because
nothing provides it:

| Option | When it wins | Trade-off |
|---|---|---|
| Ceph with Rook | Block, file and object from one system; the general answer at scale | Substantial to operate; needs enough nodes to be safe |
| Longhorn | Simple replicated block storage for Kubernetes | Less capable at scale; replication is network-hungry |
| OpenEBS, TopoLVM | Local-volume performance with orchestration | Local means node failure is data unavailability unless replicated above |
| NFS | Simple, well understood | A single point of failure unless made HA, and that is work |
| SAN or existing array | Already owned, already supported | Cost, and vendor coupling |
| MinIO, Ceph RGW | S3-compatible object storage on premises | Another system, and backup targets need capacity planning |

## Backup

| Option | When it wins | Trade-off |
|---|---|---|
| Provider snapshots and PITR | Managed databases; nothing to run | Stays inside the provider unless exported, which matters for a provider-level failure |
| pgBackRest, WAL-G, Barman | Postgres, wants control and offsite copies | You run and monitor it |
| Percona XtraBackup | MySQL and MariaDB | Same |
| Percona Backup for MongoDB | MongoDB replica sets | Same |
| Velero | Kubernetes resources and persistent volumes | Backs up cluster state; not a substitute for database-native backup |
| Restic, Kopia | Files, deduplicated, to object storage | Needs a schedule and monitoring |
| Kasten K10 | Kubernetes-native with a commercial tier | Cost |

Three questions that matter more than the tool:

1. **What is the schedule, and what is the retention?** Daily with thirty days is a
   reasonable default; a compliance regime may set a floor.
2. **Where does the copy live?** A backup in the same account and region as the
   primary survives a disk failure and not an account compromise or a region loss.
   Ask specifically whether there is a copy outside the primary blast radius.
3. **When was a restore last tested, and how long did it take?** This is the only
   question in this domain whose answer cannot be inferred, and it is the one that
   decides whether any of the above is real. "Never" is a common and honest answer;
   record it, and put a first restore test in `open-questions.md` with an owner.

## Disaster recovery tiers

| Tier | What it is | Realistic recovery | Relative cost |
|---|---|---|---|
| Backup and restore | Backups exist offsite; infrastructure rebuilt on demand | A day or more | Lowest |
| Pilot light | Infrastructure defined, data replicated, nothing running | Two to four hours | Low |
| Warm standby | A smaller copy running continuously, scaled up on failover | Minutes to an hour | High — roughly a second environment |
| Active-active | Both regions serving | Near zero | Highest, and the application has to be designed for it |

Match the tier to the recovery time from domain 1 and no higher.
`check_contradictions.py` blocks a tier that cannot meet the stated recovery time,
and the reverse — a warm standby against a four-hour target — is buying a capability
nobody asked for, which is the cheapest saving available. Worked turn 3 in
`interview-method.md` is exactly this conversation.

Ask about the **DR region** and whether a residency obligation binds it. A
disaster-recovery copy is still a copy, and this is a common oversight.

## Gating consequences

- Recovery time under a day rules out backup-and-restore; under an hour rules out
  pilot light. The gate enforces it.
- GDPR and DPDP erasure obligations reach backups, so a deletion path that stops at
  the primary database is incomplete. Say how backups are handled — usually by
  retention expiry rather than by surgical deletion, and that reasoning should be
  written down.
- A residency obligation binds the DR region.
- RBI, SEBI and IFSCA expect DR drills at a cadence, which makes the restore test a
  scheduled obligation rather than an intention.
- On premises, DR means a second site, which turns the tier table from a pricing
  question into a capital question.

## What to write

```json
"12-data-dr": {
  "status": "complete",
  "answers": {
    "primary_db": "Amazon RDS for PostgreSQL, Multi-AZ",
    "ha_topology": "one primary, one standby in another zone, automatic failover",
    "other_stores": ["ElastiCache Redis as cache only"],
    "queues": ["SQS"],
    "backup": "automated snapshots plus PITR, 30 days, copied to a second region",
    "backup_offsite": true,
    "restore_tested": "never — OQ-4, owner named, due before launch",
    "dr_tier": "pilot-light",
    "dr_region": "ap-south-2",
    "rto": "4h",
    "rpo": "15m"
  }
}
```

`dr_tier` must be `active-active`, `warm`, `warm-standby`, `pilot-light` or
`backup-restore` for the gate to check it against the recovery time.
