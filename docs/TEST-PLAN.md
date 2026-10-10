# Test Plan

## Test objectives

Project 1 should demonstrate that lifecycle decisions are deterministic, safe by default, auditable, and ready for controlled tenant integration testing.

## Test levels

| Level | Tenant writes | Purpose |
| --- | --- | --- |
| Unit tests | No | Validate planning and safety logic locally |
| Sample dry-run | No | Demonstrate joiner, mover, and leaver planning |
| Graph connectivity check | No | Validate token acquisition and tenant targeting |
| Non-production integration | Limited | Verify one-user and one-group behavior |
| Azure Automation pilot | Limited | Verify managed identity and job output |

## Offline acceptance tests

| ID | Scenario | Expected result |
| --- | --- | --- |
| UT-01 | Active worker | Ensure-user and group-reconciliation actions are planned |
| UT-02 | Terminated worker | Disable, revoke sessions, remove managed groups, and license cleanup are planned |
| UT-03 | Termination date today or earlier | Worker is treated as terminated |
| UT-04 | Placeholder policy in apply mode | Execution fails closed before authentication or writes |
| UT-05 | Termination safety limit | Execution fails when the configured limit is exceeded |
| UT-06 | Secret-like audit fields | Passwords, secrets, and tokens are excluded |
| UT-07 | Explicit direct license mapping | Direct-license action is created only when explicitly configured |

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected baseline:

```text
Ran 7 tests
OK
```

## Read-only Graph acceptance test

| Check | Expected result |
| --- | --- |
| Azure CLI tenant login | Correct tenant selected; subscription may be `N/A (tenant level account)` |
| Token acquisition | `DefaultAzureCredential` obtains a Graph token |
| Graph request | `GET /organization` returns HTTP 200 |
| Tenant verification | Returned organization ID matches expected tenant ID |
| Write safety | Output reports `writes_performed=false` |

## Non-production integration test

Use one cloud-only, non-admin test user and one assigned security group.

1. Run a dry-run and save the output.
2. Verify the planned UPN and group object ID.
3. Apply the smallest approved provisioning action.
4. Confirm the user and membership in Entra.
5. Query the Entra audit log.
6. Mark the user terminated in a lab-only feed.
7. Apply the termination workflow.
8. Confirm account disabled, sessions revoked, and managed membership removed.
9. Query the audit log again.
10. Record any replication or licensing delay.

## Negative tests

- Wrong tenant ID
- Missing Graph permission
- Expired or unavailable credential
- Empty worker feed
- Duplicate worker ID
- Duplicate UPN
- Unknown group ID
- Placeholder policy value
- Excessive termination count
- Attempt to manage an on-premises-mastered identity as cloud-only

## Evidence requirements

For each integration test, preserve:

- Test date and environment
- Redacted input description
- Policy version or hash
- Run ID
- Dry-run output
- Resulting action summary
- Entra audit evidence
- Cleanup result
- Lessons learned

Never commit tokens, secrets, production data, or unredacted user information.
