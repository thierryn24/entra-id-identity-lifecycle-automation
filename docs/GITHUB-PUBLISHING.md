# GitHub Publishing Guide

## Before creating the repository

Review the project as if you were a recruiter or IAM hiring manager. The public repository should contain the code, synthetic sample data, architecture decisions, tests, redacted evidence, and clear limitations. It must not contain tenant-specific policy files, lab worker feeds with real UPNs, audit exports, access tokens, client secrets, private keys, or unredacted screenshots.

## Recommended GitHub repository settings

Use a clear repository name such as:

```text
entra-id-identity-lifecycle-automation
```

Use this description:

```text
Portfolio IAM project demonstrating Microsoft Entra ID lifecycle automation with Microsoft Graph, Python, PowerShell, Azure Automation, and dry-run-first safety controls.
```

Set the repository to public only after the privacy checklist is complete. Add topics such as:

```text
microsoft-entra-id
identity-and-access-management
iam
microsoft-graph
powershell
python
azure-automation
sc-300
```

Enable the repository security features that are available to you, especially secret scanning and push protection. Protect the default branch if you plan to maintain the project over time.

## Local pre-publish checks

From the project root:

```powershell
python -m unittest discover -s tests -v
Get-ChildItem python\*.py, tests\*.py | ForEach-Object { python -m py_compile $_.FullName }
python -m json.tool config\policy.json > $null
```

Review the files Git will include:

```powershell
git status --short
git diff --check
git ls-files
```

Search for obvious credential markers before the first commit:

```powershell
git grep -n -I -i -E "BEGIN (RSA|OPENSSH|PRIVATE)|client_secret|access_token|password[=:]" -- . ':!*.md' || $true
```

The search may find safe code that intentionally filters or handles secret fields. Review every result manually.

## Initialize the repository

If this project is not already a Git repository:

```powershell
git init -b main
git add .
git diff --cached --check
git commit -m "feat: establish Entra ID IAM portfolio project"
```

## Create the GitHub repository

Create an empty repository on GitHub with the chosen name. Do not add a second README, `.gitignore`, or license from the GitHub web form if those files already exist locally.

Connect the local repository, replacing the placeholder URL with your own repository URL:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/entra-id-identity-lifecycle-automation.git
git remote -v
git push -u origin main
```

## After the first push

Check the rendered README from a private browser window or a logged-out view. Verify that:

- The Mermaid diagram renders or has a readable fallback.
- All links work.
- Screenshots are visible and redacted.
- The repository description is clear within the first screen.
- The limitations are easy to find.
- The GitHub Actions workflow passes.
- No tenant IDs, UPNs, emails, secrets, or raw audit files are exposed.

## Commit history

Use small, meaningful commits while the project evolves:

```text
feat: add read-only Graph connectivity check
feat: add lifecycle dry-run planner
fix: reject unresolved tenant identifiers in apply mode
docs: add permissions and operations runbooks
test: cover termination safety limits
chore: add GitHub Actions Python tests
```

Avoid committing a large history of accidental screenshots, secrets, or local configuration. If a secret is ever committed, rotate it first; deleting the file in a later commit is not sufficient.

## License decision

Choose a license deliberately before inviting reuse. MIT is common for an educational code portfolio, while a private or internal project may intentionally remain without an open-source license. Do not copy a license without understanding whether you want others to reuse and modify the code.

## Portfolio link

Once the repository is public, add it to:

- Your CV under Projects
- Your LinkedIn Featured section
- Your GitHub profile README
- Your interview demonstration notes

Describe it accurately as a fictional healthcare IAM lab and do not claim HIPAA compliance or production readiness.
