# Project 1 — Entra ID Identity Lifecycle Automation

Project 1 is a **dry-run-first identity lifecycle automation package** for Microsoft Entra ID, on-premises Active Directory, Microsoft Graph, PowerShell, Python, and Azure Automation. It automates joiner, mover, and leaver actions from a controlled worker feed while producing a tamper-evident local execution log and relying on Microsoft Entra audit logs for tenant-side evidence.

## What is included

| Component | Purpose |
| --- | --- |
| `python/identity_lifecycle.py` | Dependency-light Python implementation using Microsoft Graph v1.0 and Azure Identity credentials. |
| `python/check_graph_connection.py` | Read-only token acquisition and Graph connectivity check for local VS Code testing. |
| `powershell/Invoke-IdentityLifecycle.ps1` | Microsoft Graph PowerShell implementation for an operator workstation or CI runner. |
| `azure-automation/Invoke-IdentityLifecycle.runbook.ps1` | Self-contained Azure Automation PowerShell 7.4 runbook using managed identity authentication. |
| `config/policy.json` | Tenant-neutral policy, group mappings, and safety controls. |
| `data/sample-workers.csv` | Example HR/identity source feed. |
| `tests/test_lifecycle.py` | Offline unit tests for planning and safety behavior. |
| `docs/ARCHITECTURE.md` | Architecture, permissions, deployment, operations, and security guidance. |

## Safety defaults

1. **Dry run is the default.** No tenant write is performed unless `--apply` or `-Apply` is explicitly supplied.
2. **Deletion is disabled.** Terminated users are disabled, sessions are revoked, managed group memberships are removed, and direct licenses are removed when configured. Users are not deleted.
3. **License assignment is group-based by default.** The lifecycle engine adds a user to a role/license group. The group owns the Microsoft 365 license assignment. Direct SKU assignment is an opt-in exception.
4. **Secrets are never read from the policy file or worker CSV.** Use managed identity in Azure Automation. For local execution, use Azure CLI login, workload identity, or a certificate-backed app registration.
5. **Every planned and executed action is logged.** Secrets, passwords, and access tokens are excluded from logs.
6. **Hybrid source-of-authority is explicit.** A user mastered by on-premises Active Directory should be created and disabled in AD, then synchronized to Entra ID. Do not create a duplicate cloud user for a synced identity.

## Quick start: offline plan

```bash
cd /home/ubuntu/project-1-entra-identity-automation
python3 python/identity_lifecycle.py \
  --input data/sample-workers.csv \
  --config config/policy.json \
  --dry-run
```

The command writes JSON Lines audit output under `logs/` and prints the planned actions. The sample policy contains placeholders and intentionally cannot modify a real tenant.

## Connect to Microsoft Graph later

When you are ready to test authentication, install the dependencies and sign in with Azure CLI:

```bash
python -m pip install -r python/requirements.txt
az login --tenant YOUR_TENANT_ID
python python/check_graph_connection.py --tenant-id YOUR_TENANT_ID
```

The connectivity checker acquires a Microsoft Graph token through `DefaultAzureCredential` and performs one read-only request to `/organization`. With a delegated developer sign-in, Microsoft Graph documents `User.Read` as sufficient to read the organization ID, display name, and verified domains. With an application or managed-identity token, grant `Organization.Read.All` for this check. It does not create users, change groups, assign licenses, disable accounts, revoke sessions, or modify any tenant data. The identity used for the test must be in the intended tenant.

For local development, `DefaultAzureCredential` can use the Azure CLI login. For unattended execution, use a managed identity or a workload/service identity rather than a human login. The checker also compares the returned organization ID with `--tenant-id` when that argument is supplied.

After the read-only check succeeds, run the lifecycle planner in dry-run mode against the real worker feed. Only after tenant-specific permissions, group IDs, SKU IDs, and change approval are in place should you use `--apply`.

## Apply to a tenant

1. Register or select a dedicated Entra application or managed identity.
2. Grant only the Microsoft Graph application permissions listed in `docs/ARCHITECTURE.md`, then obtain admin consent.
3. Replace every `REPLACE_WITH_*` value in `config/policy.json`.
4. Provide a production worker feed through an approved HR export or an HRIS integration.
5. Run the offline test suite:

   ```bash
   python3 -m unittest discover -s tests -v
   ```

6. Run a dry-run against the real tenant and review the proposed changes.
7. Start with one pilot group and a small feed. Apply changes only after a documented change approval.
8. For recurring execution, import the Azure Automation runbook and schedule it at a cadence appropriate to the HR feed’s SLA.

## Input contract

The worker CSV must contain these columns:

`worker_id,first_name,last_name,upn,display_name,department,job_title,employment_status,start_date,termination_date,cost_center,location`

`employment_status` is case-insensitive and should be one of `Active`, `Leave`, `Terminated`, or `PreHire`. A user is treated as terminated when the status is `Terminated` or when `termination_date` is today or earlier. Dates must use ISO format `YYYY-MM-DD`.

## Important production boundary

This package is a starting implementation, not a substitute for tenant-specific design review. Before production use, validate licensing behavior, synced-user authority, privileged-role protections, retention obligations, HR data quality, break-glass exclusions, and the organization’s approval process. See `docs/ARCHITECTURE.md` for the full operating model.
