# Security Policy

## Scope

This repository is a fictional healthcare-sector IAM lab. It must not contain production credentials, patient data, protected health information, or unredacted tenant exports.

## Supported version

The default branch is the supported portfolio version. This project is not a production service and does not provide an SLA.

## Reporting a security issue

Do not publish credentials, tokens, personal data, or exploit details in a public issue. For a private portfolio repository, contact the repository owner through the private contact method listed on the GitHub profile.

If a secret is accidentally committed:

1. Revoke or rotate it immediately.
2. Remove it from the working tree.
3. Rewrite Git history if necessary.
4. Check repository forks, Actions logs, and artifacts.
5. Document the incident without publishing the secret.

## Safe contribution boundaries

- Use synthetic identities only.
- Use a dedicated lab tenant.
- Never include access tokens, refresh tokens, passwords, client secrets, private keys, or production worker feeds.
- Redact screenshots before committing them.
- Do not test destructive operations against privileged or emergency-access accounts.
