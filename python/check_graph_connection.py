#!/usr/bin/env python3
"""Read-only Microsoft Graph connectivity and token-scope check.

This script intentionally performs no directory writes. It acquires a token
for Microsoft Graph using Azure Identity's DefaultAzureCredential and reads the
current organization object. It is suitable for local VS Code testing with an
Azure CLI login, workload identity, service principal, or managed identity.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", help="Expected tenant ID; used for display and optional Azure CLI login guidance")
    args = parser.parse_args()

    try:
        from azure.identity import DefaultAzureCredential
    except ImportError:
        print("ERROR: install dependencies first: python -m pip install -r python/requirements.txt", file=sys.stderr)
        return 2

    try:
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        access_token = credential.get_token("https://graph.microsoft.com/.default")
        request = urllib.request.Request(
            f"{GRAPH_ROOT}/organization?$select=id,displayName,verifiedDomains",
            headers={
                "Authorization": f"Bearer {access_token.token}",
                "Accept": "application/json",
                "User-Agent": "Project1-EntraIdentityLifecycle-ConnectivityCheck/1.0",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: Microsoft Graph returned HTTP {exc.code}: {body[:1000]}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - present a concise local diagnostic
        print(f"ERROR: token acquisition or Graph request failed: {exc}", file=sys.stderr)
        return 1

    organizations = payload.get("value", [])
    if not organizations:
        print("ERROR: Graph returned no organization object", file=sys.stderr)
        return 1

    organization = organizations[0]
    organization_id = organization.get("id")
    if args.tenant_id and organization_id and args.tenant_id.casefold() != organization_id.casefold():
        print(
            f"ERROR: expected tenant {args.tenant_id}, but Graph returned organization {organization_id}",
            file=sys.stderr,
        )
        return 1
    print("Microsoft Graph connection succeeded.")
    print(json.dumps({
        "tenant_id_argument": args.tenant_id or None,
        "organization_id": organization_id,
        "display_name": organization.get("displayName"),
        "verified_domain_count": len(organization.get("verifiedDomains", [])),
        "writes_performed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
