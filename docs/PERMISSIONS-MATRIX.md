# Microsoft Graph Permissions Matrix

## Purpose

This document records the permission starting points for Project 1. It is a design aid, not an automatic admin-consent instruction. Microsoft Graph permissions, supported directory roles, and tenant policy must be reviewed before any apply-mode test.

## Authentication paths

| Execution path | Credential | Permission model | Recommended use |
| --- | --- | --- | --- |
| Local read-only check | Azure CLI through `DefaultAzureCredential` | Delegated user permissions | Stage 1 developer validation |
| Local operator test | Device-code or Azure CLI developer login | Delegated permissions plus appropriate directory role | Controlled lab only |
| CI or service runtime | Workload identity federation or certificate-backed app | Application permissions | Reviewed automation path |
| Azure Automation | System- or user-assigned managed identity | Application permissions | Unattended execution |

## Starting permission matrix

| Operation | Graph call | Starting permission | Notes |
| --- | --- | --- | --- |
| Read organization for connectivity check | `GET /organization` | Delegated `User.Read`; application `Organization.Read.All` | The checker selects only ID, display name, and verified domains. |
| Read users | `GET /users` or `GET /users/{id}` | `User.Read.All` | Reduce scope if the tenant supports a narrower reviewed design. |
| Create or update cloud users | `POST /users`, `PATCH /users/{id}` | `User.ReadWrite.All` | Do not use for users mastered by on-premises AD. |
| Disable a user | `PATCH /users/{id}` with `accountEnabled=false` | `User.EnableDisableAccount.All` plus required read access | Confirm the exact permission supported by the target API version and tenant. |
| Read groups and memberships | `GET /groups`, membership endpoints | `Group.Read.All` or `GroupMember.Read.All` | Use the least privilege needed for planning. |
| Add or remove managed memberships | Group member `$ref` endpoints | `GroupMember.ReadWrite.All` | Restrict automation to an allowlist of managed groups. |
| Assign or remove direct licenses | `POST /users/{id}/assignLicense` | `LicenseAssignment.ReadWrite.All` | Group-based licensing is the default design. |
| Revoke sign-in sessions | `POST /users/{id}/revokeSignInSessions` | `User.RevokeSessions.All` | Validate behavior in a lab user first. |
| Read tenant directory audit logs | `GET /auditLogs/directoryAudits` | `AuditLog.Read.All` | Use a separate audit-export identity where possible. |

## Consent and role review

Before apply mode:

1. Register or select a dedicated identity.
2. Grant only the permissions required by the tested operations.
3. Record whether each permission is delegated or application-only.
4. Obtain administrator consent through the organization’s process.
5. Assign only the required Microsoft Entra directory role for delegated execution.
6. Record the identity object ID and permission review date.
7. Remove unused permissions after testing.

## Security boundaries

- Do not grant `Directory.ReadWrite.All` by default.
- Do not manage privileged role-assignable groups through this starter project.
- Do not test against global administrators or emergency-access accounts.
- Prefer managed identity or workload identity over client secrets.
- Keep application permissions on a dedicated identity that is excluded from human sign-in.
- Review Microsoft Graph audit logs after every write test.

## Evidence to capture

For a portfolio lab, record:

- The permission names and whether they are delegated or application permissions
- The reason each permission is required
- The identity used for the test, without exposing secrets
- The Graph endpoint tested
- The dry-run output before the write test
- The resulting Entra audit event
- The rollback or cleanup result
