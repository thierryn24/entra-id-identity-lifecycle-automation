# Portfolio Demo Script

## Goal

Demonstrate the project in approximately 10 minutes without making unapproved tenant changes.

## 1. Explain the scenario — 1 minute

> This is a fictional healthcare IAM lab. The project models joiner–mover–leaver automation for employees using Microsoft Entra ID, Microsoft Graph, Python, PowerShell, and Azure Automation.

Emphasize that the identities are synthetic and the environment contains no patient data.

## 2. Show the repository — 1 minute

Point out:

- `python/` for the planner and connectivity check
- `powershell/` for operator and hybrid AD paths
- `azure-automation/` for the managed-identity runbook
- `config/` and `data/` for policy and sample feed
- `tests/` for offline validation
- `docs/` for architecture, permissions, operations, and evidence

## 3. Run the tests — 1 minute

```powershell
python -m unittest discover -s tests -v
```

Show:

```text
Ran 7 tests
OK
```

Explain that these tests do not call Microsoft Graph.

## 4. Run the sample dry-run — 2 minutes

```powershell
python python\identity_lifecycle.py `
  --input data\sample-workers.csv `
  --config config\policy.json `
  --dry-run
```

Explain the active-worker and terminated-worker actions. Point out that the policy contains placeholders and the sample run cannot modify a real tenant.

## 5. Show the authentication design — 2 minutes

Explain:

- Local development uses Azure CLI through `DefaultAzureCredential`.
- The connectivity check uses a read-only organization request.
- Azure Automation is designed for managed identity.
- Application permissions are intentionally reviewed separately from delegated permissions.

Run only if the lab login is already prepared:

```powershell
python python\check_graph_connection.py --tenant-id YOUR_TENANT_ID
```

Point out:

```json
"writes_performed": false
```

## 6. Explain safety controls — 2 minutes

Highlight:

- Dry-run default
- Explicit apply switch
- No user deletion
- Managed-group allowlist
- Termination limit
- Placeholder rejection
- Secret-safe logging
- Source-of-authority check for hybrid identities

## 7. Close with limitations — 1 minute

Explain that production use would require:

- Tenant-specific permission review
- HRIS integration and feed validation
- Approval workflow
- Non-production integration tests
- Monitoring and Log Analytics
- Conditional Access, PIM, access reviews, and governance controls

## Interview questions to prepare for

- Why use group-based licensing?
- Why prefer managed identity over a client secret?
- What is the difference between delegated and application permissions?
- How would you protect break-glass accounts?
- What happens if the HR feed is stale?
- How do you avoid modifying unmanaged groups?
- How would you verify that a termination succeeded?
- What is the source of authority for a synchronized user?
