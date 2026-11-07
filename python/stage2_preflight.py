#!/usr/bin/env python3
"""Read-only Stage 2 preflight for one Entra lab user and managed group.

This script performs no directory writes. It verifies the expected tenant,
locates one worker from the private feed, reads the user, reads each managed
group selected by the policy, and reports current membership.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    from .identity_lifecycle import (
        GraphClient,
        GraphHttpError,
        LifecycleError,
        desired_groups,
        load_json,
        load_workers,
        validate_policy,
    )
except ImportError:  # pragma: no cover - used when executed as python/stage2_preflight.py
    from identity_lifecycle import (
        GraphClient,
        GraphHttpError,
        LifecycleError,
        desired_groups,
        load_json,
        load_workers,
        validate_policy,
    )


def select_worker(workers: list[dict[str, str]], worker_id: str | None) -> dict[str, str]:
    if worker_id:
        matches = [worker for worker in workers if worker.get("worker_id") == worker_id]
        if not matches:
            raise LifecycleError(f"Worker ID not found in feed: {worker_id}")
        if len(matches) > 1:
            raise LifecycleError(f"Worker ID appears more than once in feed: {worker_id}")
        return matches[0]
    if len(workers) != 1:
        raise LifecycleError(
            "Stage 2 preflight expects exactly one worker; supply --worker-id for a larger feed"
        )
    return workers[0]


def group_is_safe(group: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if group.get("securityEnabled") is not True:
        failures.append("group is not security-enabled")
    if group.get("isAssignableToRole") is True:
        failures.append("group is role-assignable")
    return not failures, failures


def graph_group(client: GraphClient, group_id: str) -> dict[str, Any]:
    return client.request(
        "GET",
        f"/groups/{group_id}?$select=id,displayName,securityEnabled,mailEnabled,isAssignableToRole",
    )


def graph_memberships(client: GraphClient, user_id: str) -> list[dict[str, Any]]:
    return client.list_all(
        f"/users/{user_id}/memberOf/microsoft.graph.group"
        "?$select=id,displayName,securityEnabled,isAssignableToRole"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="config/policy.local.json", help="Private policy JSON path")
    parser.add_argument("--input", default="data/lab-workers.csv", help="Private worker CSV path")
    parser.add_argument("--worker-id", help="Worker ID to check when the feed contains more than one worker")
    args = parser.parse_args(argv)

    try:
        policy = load_json(args.policy)
        validate_policy(policy)
        workers = load_workers(args.input)
        worker = select_worker(workers, args.worker_id)
        group_ids = sorted(desired_groups(worker, policy))
        if not group_ids:
            raise LifecycleError("The selected worker resolves to no managed group IDs")

        client = GraphClient.from_default_credential(
            str(policy["tenant_id"]),
            int(policy.get("execution", {}).get("retry_attempts", 5)),
            float(policy.get("execution", {}).get("retry_base_seconds", 2)),
        )

        organization = client.request("GET", "/organization?$select=id,displayName")
        organizations = organization.get("value", [])
        if not organizations:
            raise LifecycleError("Graph returned no organization object")
        organization_id = str(organizations[0].get("id", ""))
        expected_tenant = str(policy["tenant_id"])
        if organization_id.casefold() != expected_tenant.casefold():
            raise LifecycleError(
                f"Tenant mismatch: policy expects {expected_tenant}, Graph returned {organization_id}"
            )

        user = client.get_user(worker["upn"])
        if not user:
            raise LifecycleError(f"User was not found: {worker['upn']}")
        user_id = str(user["id"])
        if user.get("accountEnabled") is False:
            raise LifecycleError(f"Selected active lab user is disabled: {worker['upn']}")

        groups: list[dict[str, Any]] = []
        failures: list[str] = []
        for group_id in group_ids:
            try:
                group = graph_group(client, group_id)
                safe, group_failures = group_is_safe(group)
                groups.append({
                    "id": group.get("id"),
                    "display_name": group.get("displayName"),
                    "security_enabled": group.get("securityEnabled"),
                    "mail_enabled": group.get("mailEnabled"),
                    "role_assignable": group.get("isAssignableToRole", False),
                    "safe_for_stage2": safe,
                    "failures": group_failures,
                })
                failures.extend(f"{group_id}: {item}" for item in group_failures)
            except GraphHttpError as exc:
                failures.append(f"{group_id}: Graph HTTP {exc.status}: {exc}")

        memberships = graph_memberships(client, user_id)
        membership_ids = {str(item.get("id")) for item in memberships}
        membership_summary = [
            {"group_id": group_id, "is_member": group_id in membership_ids}
            for group_id in group_ids
        ]

        ready = not failures
        result = {
            "tenant_verified": True,
            "worker_id": worker["worker_id"],
            "user_found": True,
            "user_account_enabled": user.get("accountEnabled"),
            "managed_groups": groups,
            "membership": membership_summary,
            "writes_performed": False,
            "ready_for_controlled_stage2_write": ready,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if failures:
            print("Preflight failed:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        print("Stage 2 read-only preflight succeeded.")
        return 0
    except GraphHttpError as exc:
        print(f"ERROR: Microsoft Graph HTTP {exc.status}: {exc}", file=sys.stderr)
        return 1
    except (LifecycleError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - concise local diagnostic
        print(f"ERROR: token acquisition or Graph request failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
