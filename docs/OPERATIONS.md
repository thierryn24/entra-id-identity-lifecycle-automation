# Operations Runbook

## Scope

This runbook describes how to operate Project 1 safely in a personal or non-production Entra lab. It is intentionally conservative and does not replace tenant change management.

## Execution stages

```text
Offline tests → Read-only Graph check → Real-feed dry-run → Permission review → One-user pilot → Termination test → Evidence review
```

Do not skip directly from offline tests to broad apply mode.

## Preflight checklist

- [ ] The worker feed came from the expected source.
- [ ] The feed is fresh and contains stable worker IDs.
- [ ] The correct tenant ID is known.
- [ ] The execution identity is the intended identity.
- [ ] The identity is not a personal administrator account for unattended work.
- [ ] The policy contains no unresolved placeholders.
- [ ] Managed group IDs were verified from the target tenant.
- [ ] Privileged and emergency-access accounts are excluded.
- [ ] The termination limit is appropriate for the change window.
- [ ] A rollback or recovery plan exists.

## Stage 1: local validation

```powershell
python -m unittest discover -s tests -v
az login --tenant YOUR_TENANT_ID --allow-no-subscriptions
python python\check_graph_connection.py --tenant-id YOUR_TENANT_ID
```

The Graph checker is read-only. It must report the expected organization and `writes_performed=false`.

## Stage 2: dry-run

```powershell
python python\identity_lifecycle.py `
  --input data\lab-workers.csv `
  --config config\policy.local.json `
  --dry-run
```

Review:

- Number of planned actions
- Active users to ensure or update
- Group memberships to add or remove
- Terminations and session revocations
- License actions
- Unexpected users or UPNs
- Generated JSONL audit output

A dry-run is not approval. It is evidence for the approval decision.

## Stage 3: controlled pilot

Use a single non-admin test user and a single lab group. Before apply mode:

1. Confirm the user is cloud-only or that the selected source-of-authority path is correct.
2. Confirm the user is not privileged.
3. Confirm the group is not role-assignable.
4. Confirm Graph permissions and admin consent.
5. Save the dry-run output.
6. Record the policy version and run ID.
7. Apply only the smallest approved change.

## Monitoring during execution

Watch for:

- Authentication or consent failures
- HTTP 401 or 403 responses
- Throttling responses such as HTTP 429
- A termination count above the expected limit
- A missing user or group
- Partial group reconciliation
- License propagation delay
- Unexpected changes outside the managed-group allowlist

## After execution

1. Review the local JSONL log.
2. Record the run ID and action count.
3. Query Entra directory audit logs for the run window.
4. Compare expected actions with tenant-side mutations.
5. Check the test user and group in the Entra admin center.
6. Record failures and whether they were retried.
7. Remove temporary permissions or test data when the lab is complete.

## Recovery and rollback

The package does not delete users. For an incorrect pilot:

- Re-enable a mistakenly disabled test account.
- Restore intended managed group membership through an approved change.
- Remove an unintended license assignment through the approved licensing path.
- Revoke or rotate credentials if the execution identity was exposed.
- Preserve logs and the run ID for investigation.
- Do not rerun a partial execution until the failure is understood.

## Leaver safety

Termination is high impact. Before testing:

- Use a dedicated lab user.
- Set `max_terminations_per_run` to `1`.
- Confirm that delete-user behavior is disabled.
- Confirm that unmanaged group memberships will not be changed.
- Confirm that mailbox and data preservation requirements are handled separately.

## Incident indicators

Escalate or stop the run if:

- The feed is empty or unexpectedly small.
- A privileged account appears in the input.
- More terminations are planned than expected.
- Tenant IDs do not match.
- The execution identity is not the approved identity.
- The run fails after making partial changes.
- Audit evidence does not match the planned actions.
