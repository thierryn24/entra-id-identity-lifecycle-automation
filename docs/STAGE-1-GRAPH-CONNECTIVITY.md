# Stage 1 — Microsoft Graph Connectivity

## Status

| Field | Value |
| --- | --- |
| Project | Project 1 — Entra ID Identity Lifecycle Automation |
| Stage | Stage 1: local Microsoft Graph connectivity |
| Status | Completed in a personal Entra ID lab |
| Execution environment | VS Code integrated PowerShell terminal |
| Authentication | Azure CLI developer login through Azure Identity `DefaultAzureCredential` |
| Graph operation | Read-only `GET /organization` |
| Tenant writes performed | No |
| Subscription required | No; tenant-level Azure CLI login was used |

## Objective

The objective of Stage 1 was to prove that the local Python project could authenticate to the intended Microsoft Entra tenant and make a controlled, read-only Microsoft Graph request.

This stage intentionally did not provision users, modify groups, assign licenses, disable accounts, or revoke sessions. It established the authentication foundation before any lifecycle write operation was considered.

## Environment

The project was opened in Visual Studio Code from the Project 1 repository root. A Python virtual environment was created and activated locally.

The following commands were used to verify the environment:

```powershell
Get-Location
Get-ChildItem
python --version
python -m unittest discover -s tests -v
```

The local test suite completed successfully:

```text
Ran 7 tests
OK
```

## Authentication flow

The local test used Azure CLI authentication:

```powershell
az login --tenant <TENANT_ID> --allow-no-subscriptions
```

The `--allow-no-subscriptions` option was used because the lab tenant did not have an Azure subscription. The login still provided tenant-level authentication for the read-only Graph test.

Project 1 uses Azure Identity’s `DefaultAzureCredential`. In this local setup, the credential chain used the developer’s Azure CLI login to acquire a Microsoft Graph token.

The connectivity script requested a token for:

```text
https://graph.microsoft.com/.default
```

It then sent the token as a bearer token to Microsoft Graph.

## Read-only Graph request

The connectivity checker called:

```http
GET https://graph.microsoft.com/v1.0/organization?$select=id,displayName,verifiedDomains
```

The request returned the organization object for the expected tenant. The script compared the returned organization ID to the tenant ID supplied on the command line.

The check was run with:

```powershell
python python\check_graph_connection.py --tenant-id <TENANT_ID>
```

A redacted example of the successful result is:

```text
Microsoft Graph connection succeeded.
{
  "tenant_id_argument": "<REDACTED_TENANT_ID>",
  "organization_id": "<REDACTED_TENANT_ID>",
  "display_name": "<REDACTED_LAB_NAME>",
  "verified_domain_count": 1,
  "writes_performed": false
}
```

## Evidence collected

| Evidence | Purpose | Recommended screenshot |
| --- | --- | --- |
| Repository and terminal location | Shows the project was executed from the intended VS Code workspace | Yes |
| Unit-test result | Shows the local code passed its offline tests | Yes |
| Azure CLI tenant-level login | Shows authentication was directed to the intended tenant without an Azure subscription | Optional |
| Read-only Graph result | Shows successful token acquisition and Graph connectivity | Yes |
| Entra admin center overview | Shows the lab tenant context | Optional; redact identifying values |

## Recommended screenshots

Keep the final portfolio to **three or four strong screenshots**. More screenshots do not automatically make the project stronger.

### Screenshot 1 — VS Code project and test result

Capture the VS Code terminal showing:

```powershell
python -m unittest discover -s tests -v
```

The terminal should show:

```text
Ran 7 tests
OK
```

The Explorer panel should show the main project folders if possible.

### Screenshot 2 — Azure CLI tenant-level login

Capture the terminal showing the successful tenant-level login or verification command:

```powershell
az account show --query "{tenantId:tenantId,user:user.name}" -o json
```

Redact:

- Personal email address
- Tenant ID, unless you intentionally choose to publish it
- Local Windows username
- Subscription or organization identifiers

This screenshot is optional because the Graph success screenshot is stronger evidence.

### Screenshot 3 — Successful read-only Graph check

Capture the command and result:

```powershell
python python\check_graph_connection.py --tenant-id <TENANT_ID>
```

The screenshot should clearly show:

```text
Microsoft Graph connection succeeded.
"writes_performed": false
```

Redact the actual tenant ID, personal email, and organization display name before publishing.

### Screenshot 4 — Entra lab context

Optionally capture the Microsoft Entra admin center showing the lab tenant overview or a test group. Do not show a list of real users in a public portfolio screenshot.

If a user list is necessary for a private submission, redact:

- User principal names
- Personal names
- Email addresses
- Tenant branding
- Administrator accounts
- Any domain names that identify the organization

## What the screenshots prove

The screenshots should support these claims:

1. The code runs locally in a structured Python project.
2. The local tests pass before tenant access is attempted.
3. Azure CLI can authenticate to the intended Entra tenant without an Azure subscription.
4. The application can acquire a Microsoft Graph token through Azure Identity.
5. The application can perform a read-only Graph request.
6. No tenant write operation was performed during Stage 1.

## What not to claim yet

Stage 1 does not yet prove that the project can:

- Create users
- Modify users
- Add or remove group members
- Assign Microsoft 365 licenses
- Disable users
- Revoke sessions
- Run as an Azure Automation managed identity
- Operate safely in production

Those capabilities require separate permission configuration and controlled non-production integration tests.

## Suggested README section

Add this section to the repository README:

```markdown
## Stage 1 — Read-only Microsoft Graph connectivity

I validated the local authentication path before enabling lifecycle writes.
The project runs in VS Code and uses Azure CLI developer authentication through
Azure Identity's `DefaultAzureCredential`.

The test command was:

```powershell
az login --tenant <TENANT_ID> --allow-no-subscriptions
python python\check_graph_connection.py --tenant-id <TENANT_ID>
```

The checker performed a read-only request to Microsoft Graph:

```http
GET /organization?$select=id,displayName,verifiedDomains
```

The result confirmed the expected tenant and reported:

```json
{
  "writes_performed": false
}
```

No users, groups, licenses, or sessions were modified during this stage.
```

## Suggested portfolio project bullet

Use a truthful bullet such as:

> Built and tested a Python-based Microsoft Entra ID lifecycle automation project in VS Code; implemented Azure CLI authentication through Azure Identity and validated read-only Microsoft Graph connectivity before introducing tenant write operations.

## Suggested interview explanation

> I separated authentication validation from lifecycle changes. First, I ran offline unit tests. Then I authenticated to the correct Entra tenant using Azure CLI with no Azure subscription. Finally, I used a dedicated Python connectivity checker to acquire a Microsoft Graph token and call the read-only organization endpoint. The checker also compared the returned organization ID with the expected tenant ID and confirmed that no write operations occurred. This staged approach reduced the risk of testing user or group changes before authentication and tenant targeting were verified.

## Screenshot filename convention

Use descriptive filenames instead of names such as `Screenshot1.png`:

```text
screenshots/stage-1-vscode-tests.png
screenshots/stage-1-azure-cli-tenant-login-redacted.png
screenshots/stage-1-graph-readonly-success-redacted.png
screenshots/stage-1-entra-lab-context-redacted.png
```

## Privacy checklist before publishing

- [ ] Personal email addresses are redacted.
- [ ] Real user names are redacted.
- [ ] User principal names are redacted.
- [ ] Tenant IDs are redacted or intentionally approved for publication.
- [ ] Domain names are redacted if they identify the lab owner.
- [ ] Access tokens and refresh tokens are not visible.
- [ ] Client secrets and certificates are not visible.
- [ ] Browser tabs do not show unrelated personal information.
- [ ] Administrator and break-glass accounts are not shown.
- [ ] The screenshot does not show a successful write operation that was not actually performed.

## Next stage

Stage 2 should use one dedicated non-admin test user and one lab security group. The next milestone is a real-tenant dry-run that calculates user and group actions without applying them.
