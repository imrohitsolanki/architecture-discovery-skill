# From a domain answer to resources

Read this when turning a recorded decision into `.tf` files.

These tables are a starting point for the common shapes, not a catalogue. **A row
here is not permission to write the resource** — rule 1 still holds: the
specification decided it, or it does not get written. Where the specification named
something not in these tables, read the provider documentation rather than
substituting the nearest row.

**Every row names the siblings, not just the headline resource.** That is the whole
discipline of this file. The characteristic defect of a generated stack is not a
wrong resource, it is a required sibling silently absent — a VPC with no flow log, a
load balancer with no access logs, a bucket whose encryption lives in a separate
resource nobody wrote. Those review clean, because nothing on the page is wrong. So
where a decision needs three resources, the row says three.

## AWS

| Spec decision | Resources, or the module that is better than hand-rolling |
|---|---|
| VPC, subnets, routing (domain 7) | `terraform-aws-modules/vpc/aws` — subnet arithmetic and route tables are tedious and easy to get subtly wrong |
| Private subnets, no public data stores | Data stores in subnets with no route to an internet gateway; `publicly_accessible = false` on RDS |
| Egress from private subnets | `aws_nat_gateway` — one per availability zone for resilience, one shared for cost. The specification's SLA and cost ceiling decide which; it is not a default |
| Ingress (domain 7) | `aws_lb` + `aws_lb_listener`, or `aws_apigatewayv2_api` for serverless. TLS from `aws_acm_certificate` |
| Managed Kubernetes (domain 6) | `terraform-aws-modules/eks/aws`. Node groups, or Fargate profiles where the spec chose serverless nodes |
| Containers without Kubernetes | `aws_ecs_cluster`, `aws_ecs_service`, `aws_ecs_task_definition` |
| Serverless (domain 6) | `aws_lambda_function`, `aws_lambda_event_source_mapping`. Concurrency limits are a recorded answer, not a default |
| Relational database (domain 12) | `aws_db_instance` or `aws_rds_cluster`. `storage_encrypted`, `backup_retention_period` and `deletion_protection` come from the spec's RPO and RTO |
| Object storage | `aws_s3_bucket` plus its separate `_versioning`, `_server_side_encryption_configuration`, `_public_access_block` and `_lifecycle_configuration` resources — the bucket resource alone configures none of them |
| Workload identity (domain 8) | IRSA: `aws_iam_openid_connect_provider` + `aws_iam_role` with a condition on the service account. Never an access key |
| Secrets (domain 8) | `aws_secretsmanager_secret` or SSM `SecureString`. The *value* is never in Terraform |
| Encryption keys | `aws_kms_key` with `enable_key_rotation = true`, and an alias. One key per data classification the spec named, not one per resource |
| Logs and metrics (domain 10) | `aws_cloudwatch_log_group` with `retention_in_days` from the spec — PCI-DSS says twelve months, and the gate checked that was recorded |
| Audit trail (domain 11) | `aws_cloudtrail` to a bucket with object lock where the regime requires immutability |
| Multi-account (domain 4) | Provider `assume_role`, one provider alias per account. Never static credentials in the tree |
| CDN (domain 7) | `aws_cloudfront_distribution` plus `aws_cloudfront_response_headers_policy` for the security headers, and an origin access control — the distribution alone sets no headers. Where the spec named a content-security policy, this is where it lives, and PCI-DSS 6.4.3 makes it a named control rather than a nicety |
| WAF (domain 7 or 11) | `aws_wafv2_web_acl` plus `aws_wafv2_web_acl_association` to the load balancer or an association on the distribution, plus `aws_wafv2_web_acl_logging_configuration` — an unassociated ACL inspects nothing and an unlogged one proves nothing |
| DDoS (domain 7) | `aws_shield_protection` per protected resource. Shield Advanced is a paid subscription and a commercial decision the spec records, not a default |
| DNS (domain 7) | `aws_route53_zone` + `aws_route53_record`, and `aws_acm_certificate_validation` where a certificate is validated by DNS |
| Queues (domain 2 or 12) | `aws_sqs_queue` **with a dead-letter queue and a redrive policy** — a queue without one loses the message that keeps failing. Encryption is `kms_master_key_id`, not a default |
| Pub/sub and streams | `aws_sns_topic` + `aws_sns_topic_subscription`; `aws_msk_cluster` where the spec chose Kafka, with encryption in transit and at rest both set |
| Cache (domain 2 or 12) | `aws_elasticache_replication_group` — `at_rest_encryption_enabled`, `transit_encryption_enabled` and `automatic_failover_enabled` are separate attributes and none is on by default. A subnet group and a parameter group are separate resources |
| Autoscaling (domain 6) | ECS: `aws_appautoscaling_target` + `aws_appautoscaling_policy`, two resources, both needed. EKS: the cluster autoscaler or Karpenter is a Helm release, not a Terraform resource — pin the chart version the same way a provider is pinned |
| Runtime security and posture (domain 11) | `aws_guardduty_detector`, `aws_securityhub_account` + `aws_securityhub_standards_subscription`, `aws_config_configuration_recorder` + `_delivery_channel` + `_recorder_status`. Each of these is several resources, and the recorder without its status resource records nothing |

## Azure

| Spec decision | Resources |
|---|---|
| Network (domain 7) | `azurerm_virtual_network`, `azurerm_subnet`, `azurerm_network_security_group` |
| Private data plane | `azurerm_private_endpoint` + `azurerm_private_dns_zone`; public network access disabled on the service |
| Ingress | `azurerm_application_gateway`, or `azurerm_lb` where there is no layer-7 requirement |
| Managed Kubernetes (domain 6) | `azurerm_kubernetes_cluster` + `azurerm_kubernetes_cluster_node_pool` |
| Containers without Kubernetes | `azurerm_container_app` and `azurerm_container_app_environment` |
| Serverless | `azurerm_linux_function_app` + `azurerm_service_plan` |
| Relational database (domain 12) | `azurerm_postgresql_flexible_server` or `azurerm_mssql_database`; geo-redundant backup where the DR tier says so |
| Object storage | `azurerm_storage_account` + `azurerm_storage_container`, public access disabled |
| Workload identity (domain 8) | `azurerm_user_assigned_identity` + `azurerm_federated_identity_credential`. Never a client secret |
| Secrets | `azurerm_key_vault` + `azurerm_key_vault_secret` for the reference, not the value |
| Logs (domain 10) | `azurerm_log_analytics_workspace` + `azurerm_monitor_diagnostic_setting` — the workspace alone collects nothing; the diagnostic setting per resource is what sends to it |
| CDN and WAF (domain 7) | `azurerm_cdn_frontdoor_profile` + `_endpoint` + `_origin_group` + `_route`, and `azurerm_cdn_frontdoor_firewall_policy` associated through a security policy. Security headers go in a rule set, which is a further resource |
| DDoS (domain 7) | `azurerm_network_ddos_protection_plan`, referenced from the virtual network. The plan is billed per plan, not per network |
| DNS (domain 7) | `azurerm_dns_zone` + `azurerm_dns_a_record`, or `azurerm_private_dns_zone` + `_virtual_network_link` for a private data plane |
| Queues and streams (domain 2 or 12) | `azurerm_servicebus_namespace` + `_queue` (with `dead_lettering_on_message_expiration`), or `azurerm_eventhub_namespace` + `_eventhub` + `_consumer_group` |
| Cache | `azurerm_redis_cache` with `public_network_access_enabled = false` and a private endpoint; TLS-only is `minimum_tls_version` |
| Autoscaling (domain 6) | `azurerm_monitor_autoscale_setting`, or AKS node pool `enable_auto_scaling` with min and max counts from the spec |
| Runtime security and posture (domain 11) | `azurerm_security_center_subscription_pricing` + `azurerm_security_center_contact`, and `azurerm_policy_assignment` where the spec named a policy baseline |
| Flow logs (domain 10) | `azurerm_network_watcher_flow_log` — the network watcher is per region and the flow log is per network security group; neither exists by default |

## GCP

| Spec decision | Resources |
|---|---|
| Network (domain 7) | `google_compute_network` with `auto_create_subnetworks = false`, then `google_compute_subnetwork` |
| Private data plane | `google_service_networking_connection` for private service access; `google_compute_router` + `_router_nat` for egress |
| Ingress | `google_compute_global_forwarding_rule` and the URL map chain, or `google_cloud_run_v2_service` with its own ingress control |
| Managed Kubernetes (domain 6) | `google_container_cluster` + `google_container_node_pool`. Private cluster where the spec says private |
| Containers without Kubernetes | `google_cloud_run_v2_service` |
| Relational database (domain 12) | `google_sql_database_instance`; `ipv4_enabled = false` with private IP, backups and PITR from the RPO |
| Object storage | `google_storage_bucket` with `uniform_bucket_level_access` and `public_access_prevention` |
| Workload identity (domain 8) | `google_service_account` + `google_service_account_iam_member` on `workloadIdentityUser`. Never a key file |
| Secrets | `google_secret_manager_secret`, value supplied outside Terraform |
| Logs (domain 10) | `google_logging_project_sink` + `google_project_sink_member` — the sink's writer identity needs the IAM binding, or the sink silently writes nothing |
| CDN and WAF (domain 7) | `google_compute_backend_service` with `enable_cdn`, plus `google_compute_security_policy` for Cloud Armor attached to it. Response headers are a `custom_response_headers` list on the backend service |
| DNS (domain 7) | `google_dns_managed_zone` + `google_dns_record_set` |
| Queues and streams (domain 2 or 12) | `google_pubsub_topic` + `google_pubsub_subscription`, **with a dead-letter topic and its IAM bindings** — the dead-letter policy needs the subscriber role granted to the service agent or it silently does nothing |
| Cache | `google_redis_instance`, private service access, `auth_enabled` and `transit_encryption_mode` both set explicitly |
| Autoscaling (domain 6) | `google_compute_autoscaler` for managed instance groups; GKE node pool `autoscaling` block, or Autopilot where the spec chose it |
| Runtime security and posture (domain 11) | `google_scc_notification_config` and the organisation policy constraints the spec named. Most of Security Command Center is configured at the organisation level, which is often outside the project this stack owns — say so rather than writing it |
| Flow logs (domain 10) | `log_config` on `google_compute_subnetwork`. It is a block on the subnet rather than a resource of its own, so it is easy to leave out of a module that creates subnets in a loop |

## On premises and bare metal

**No table is shipped for this, and that is not an oversight.** Where domain 4
recorded on-premises, the provider depends entirely on what is underneath —
vSphere, Proxmox, OpenStack, MAAS, or nothing declarative at all — and a plausible
mapping written from the nearest cloud analogue is exactly the invented resource
rule 1 exists to prevent.

Read the specification, name the provider the client actually runs, read its
documentation, and where no declarative provider exists say so: Ansible or a
runbook is a legitimate answer, and recording that Terraform does not cover this
layer is more useful than a module that half does.

## Where each of these lands in the stack

The resource goes in a **module** under `modules/<component>/`. The decision about
*which* environments get it, and with what values, goes in a **unit** —
`live/<env>/<component>/terragrunt.hcl` — as `inputs`, with a `dependency` block for
anything it needs from another unit.

A resource that exists in one environment and not another is a unit directory that
exists in one `live/<env>/` and not the other. That is legible in a directory
listing; a `count = var.environment == "prod" ? 1 : 0` buried in a module is not.

The provider itself is configured once, by `root.hcl`. A module that configures its
own provider fails the `conventions` gate — it cannot then be used with `for_each`,
and removing the block later is a breaking change for every caller.

## Things worth getting right whatever the provider

**Tags or labels on everything.** `default_tags` generated in `root.hcl` from
`env.hcl`, merged with a per-module `locals` block, carrying at minimum the
environment, the project and the fact that this is managed by Terraform. Someone will find an unexplained resource in the console; the tag is
what tells them not to delete it.

**`prevent_destroy` on data stores.** A `lifecycle { prevent_destroy = true }` on
databases and state buckets costs nothing until the day it is the only thing between
a refactor and an outage.

**Outputs are an interface.** A module outputs what another unit's `dependency` block
or an operator needs — an endpoint, a cluster name, an id. Not everything it created;
an output nobody depends on is a maintenance cost with no reader. Mark anything sensitive
`sensitive = true`, and remember that does not keep it out of the state file.

**Resource naming from a `locals` convention**, not repeated string interpolation.
Defined once in the module from the `name` input the unit supplies, and every
resource name derived from it. More on this in `references/conventions.md`.
