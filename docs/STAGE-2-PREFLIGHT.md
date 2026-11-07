# Stage 2 — Read-Only User and Group Preflight

## Objective

Verify the private Stage 2 policy and worker feed against Microsoft Graph before any lifecycle write. This preflight is intentionally read-only and is designed for one synthetic, non-admin lab user and one non-role-assignable security group.

## Preconditions

- Stage 1 Graph connectivity succeeded.
- `config/policy.local.json` contains the real tenant and lab group Object ID.
- `data/lab-workers.csv` contains one synthetic lab worker, or `--worker-id` is supplied.
- The selected user is non-admin and not a break-glass account.
- The selected group is a security group and is not role-assignable.
- The private files are ignored by Git.

## Run

From the repository root in an activated virtual environment:

```powershell
python python\stage2_preflight.py `
  --policy config\policy.local.json `
  --input data\lab-workers.csv
```

If the feed contains more than one worker:

```powershell
python python\stage2_preflight.py `
  --policy config\policy.local.json `
  --input data\lab-workers.csv `
  --worker-id STAGE2-001
```

The script uses `DefaultAzureCredential`, so a local Azure CLI session can be used:

```powershell
az login --tenant YOUR_TENANT_ID --allow-no-subscriptions
```

## Read-only requests

The preflight reads:

- `/organization` to verify the expected tenant
- `/users/{userPrincipalName}` to locate the selected user
- `/groups/{groupObjectId}` to verify group type and role-assignability
- `/users/{userId}/memberOf/microsoft.graph.group` to summarize current managed membership

It does not create, update, disable, delete, license, or revoke sessions for any object.

## Expected success indicators

The JSON output should contain:

```json
{
  "tenant_verified": true,
  "user_found": true,
  "writes_performed": false,
  "ready_for_controlled_stage2_write": true
}
```

The output also reports whether the selected user is already a member of each managed group.

## If it fails

- `Tenant mismatch`: confirm Azure CLI and `policy.local.json` use the same tenant.
- `User was not found`: confirm the private worker UPN exactly matches the Entra user.
- `group is not security-enabled`: use a security group rather than a Microsoft 365 group.
- `group is role-assignable`: stop and choose a non-role-assignable lab group.
- Graph HTTP 403: review the delegated Microsoft Graph read permissions and consent; do not immediately grant broad write permissions.
- Authentication failure: run `az account show` and sign in to the intended tenant.

## Evidence

Keep the raw output private. For a portfolio screenshot, redact tenant IDs, UPNs, display names, and Object IDs. Record:

- Test date
- Worker ID or a redacted identifier
- Policy version or hash
- Tenant verified
- User found
- Group safety checks
- Current membership
- `writes_performed=false`

Do not use `--apply` until this preflight succeeds and the first write has an explicit action allowlist and rollback plan.
