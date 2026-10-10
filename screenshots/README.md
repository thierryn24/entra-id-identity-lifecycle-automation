# Portfolio Screenshots

Only place **redacted, non-sensitive evidence** in this directory.

## Recommended Stage 1 evidence

| Filename | Demonstrates |
| --- | --- |
| `stage-1-vscode-tests.png` | Seven offline tests passed in the local virtual environment |
| `stage-1-azure-cli-tenant-login-redacted.png` | Tenant-level Azure CLI login without an Azure subscription |
| `stage-1-graph-readonly-success-redacted.png` | Read-only Microsoft Graph connectivity and `writes_performed=false` |

## Redaction requirements

Before committing an image, check for personal email addresses, Windows usernames, tenant IDs, UPNs, domain names, organization identifiers, access tokens, secrets, private keys, browser tabs, and unrelated notifications.

Use opaque rectangles or crop the sensitive region. Do not rely on a light blur for secrets or tokens. Keep the command, result, and technical evidence visible after redaction.

## Naming and captions

Use descriptive names such as `stage-1-graph-readonly-success-redacted.png`, not `Screenshot123.png`. Add a short caption in the README explaining what the image proves and what it intentionally does not prove.

## Do not upload

Never upload raw screenshots, screenshots of real user lists, production audit exports, or images containing credentials. Store raw images outside the repository or under a local `screenshots/raw/` directory, which is ignored by Git.
