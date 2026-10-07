---
name: routing-edit-existing-terraform
description: An edit to Terraform that already manages live infrastructure
tags: [anti-trigger]
max_turns: 3
allowed_tools: [Skill, Read, Glob, Grep]
---

Add a `CostCentre` tag to the S3 buckets in our existing terraform, and make sure
versioning is on while you're in there.
