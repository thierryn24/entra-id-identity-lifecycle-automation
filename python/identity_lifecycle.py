#!/usr/bin/env python3
"""Entra ID identity lifecycle automation.

This module intentionally defaults to dry-run behavior. It uses Microsoft Graph
v1.0 through urllib and Azure Identity's DefaultAzureCredential so the same
code can run locally, in CI, or with an Azure Automation managed identity.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import re
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
TERMINATED_STATUSES = {"terminated", "offboarded", "disabled"}
VALID_STATUSES = {"active", "leave", "terminated", "prehire", "offboarded", "disabled"}
PLACEHOLDER_PREFIXES = ("REPLACE_WITH", "REPLACE-")


class LifecycleError(RuntimeError):
    """An expected lifecycle or Graph API failure."""


class GraphHttpError(LifecycleError):
    """Graph API error with an HTTP status for retry and reporting logic."""

    def __init__(self, status: int, message: str, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.request_id = request_id


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise LifecycleError(f"Invalid ISO date: {value!r}") from exc


def is_placeholder(value: str) -> bool:
    return not value or value.startswith(PLACEHOLDER_PREFIXES) or value in {"...", "TBD"}


def normalized_status(worker: dict[str, str], today: dt.date | None = None) -> str:
    status = (worker.get("employment_status") or "").strip().lower()
    if status not in VALID_STATUSES:
        raise LifecycleError(
            f"Worker {worker.get('worker_id', '<unknown>')} has unsupported employment_status {status!r}"
        )
    termination_date = parse_date(worker.get("termination_date"))
    if termination_date and termination_date <= (today or dt.date.today()):
        return "terminated"
    return status


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_workers(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "worker_id", "first_name", "last_name", "upn", "display_name",
        "department", "job_title", "employment_status", "start_date",
        "termination_date", "cost_center", "location",
    }
    if not rows:
        raise LifecycleError("Worker feed is empty")
    missing = required - set(rows[0].keys())
    if missing:
        raise LifecycleError(f"Worker feed is missing columns: {sorted(missing)}")
    return [{key: (value or "").strip() for key, value in row.items()} for row in rows]


def validate_policy(policy: dict[str, Any]) -> None:
    for key in ("tenant_id", "verified_domain", "source_of_authority"):
        if is_placeholder(str(policy.get(key, ""))):
            raise LifecycleError(f"Policy value {key!r} must be replaced before apply mode")
    if policy.get("source_of_authority") not in {"cloud", "on_premises_ad", "hybrid"}:
        raise LifecycleError("source_of_authority must be cloud, on_premises_ad, or hybrid")
    execution = policy.get("execution", {})
    if not execution.get("allow_placeholder_ids", False):
        configured_ids: list[str] = [str(value) for value in policy.get("managed_group_ids", [])]
        for mapping in policy.get("role_mappings", []):
            configured_ids.extend(str(value) for value in mapping.get("group_ids", []))
            configured_ids.extend(str(value) for value in mapping.get("license_group_ids", []))
            configured_ids.extend(str(value) for value in mapping.get("direct_license_sku_ids", []))
        unresolved = sorted(value for value in configured_ids if is_placeholder(value))
        if unresolved:
            raise LifecycleError(f"Policy contains unresolved group or SKU IDs: {unresolved}")
    if int(execution.get("max_actions_per_run", 0)) <= 0:
        raise LifecycleError("execution.max_actions_per_run must be positive")
    if int(execution.get("max_terminations_per_run", 0)) <= 0:
        raise LifecycleError("execution.max_terminations_per_run must be positive")


def matching_mappings(worker: dict[str, str], policy: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for mapping in policy.get("role_mappings", []):
        department_match = not mapping.get("department") or mapping["department"].casefold() == worker.get("department", "").casefold()
        title_match = not mapping.get("job_title") or mapping["job_title"].casefold() == worker.get("job_title", "").casefold()
        if department_match and title_match:
            matches.append(mapping)
    return matches


def desired_groups(worker: dict[str, str], policy: dict[str, Any]) -> set[str]:
    result = {str(group_id) for group_id in policy.get("managed_group_ids", [])}
    for mapping in matching_mappings(worker, policy):
        result.update(str(group_id) for group_id in mapping.get("group_ids", []))
        result.update(str(group_id) for group_id in mapping.get("license_group_ids", []))
    return {group_id for group_id in result if not is_placeholder(group_id)}


def direct_license_skus(worker: dict[str, str], policy: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for mapping in matching_mappings(worker, policy):
        result.update(str(sku_id) for sku_id in mapping.get("direct_license_sku_ids", []))
    return {sku_id for sku_id in result if not is_placeholder(sku_id)}


def build_plan(
    workers: Iterable[dict[str, str]],
    policy: dict[str, Any],
    today: dt.date | None = None,
) -> list[dict[str, Any]]:
    """Build a deterministic action plan without calling Microsoft Graph."""
    today = today or dt.date.today()
    actions: list[dict[str, Any]] = []
    termination_count = 0
    for worker in workers:
        worker_id = worker.get("worker_id", "")
        upn = worker.get("upn", "")
        if not worker_id or not upn:
            raise LifecycleError("Every worker must have worker_id and upn")
        status = normalized_status(worker, today=today)
        if status in TERMINATED_STATUSES or (parse_date(worker.get("termination_date")) or dt.date.max) <= today:
            termination_count += 1
            actions.extend([
                {"action": "disable_user", "worker_id": worker_id, "upn": upn},
                {"action": "revoke_sign_in_sessions", "worker_id": worker_id, "upn": upn},
                {"action": "remove_managed_group_memberships", "worker_id": worker_id, "upn": upn},
                {"action": "remove_direct_licenses", "worker_id": worker_id, "upn": upn},
            ])
            continue
        if status in {"active", "prehire", "leave"}:
            actions.extend([
                {"action": "ensure_user", "worker_id": worker_id, "upn": upn, "status": status},
                {
                    "action": "reconcile_managed_groups",
                    "worker_id": worker_id,
                    "upn": upn,
                    "desired_group_ids": sorted(desired_groups(worker, policy)),
                },
            ])
            sku_ids = sorted(direct_license_skus(worker, policy))
            if sku_ids:
                actions.append({
                    "action": "assign_direct_licenses",
                    "worker_id": worker_id,
                    "upn": upn,
                    "sku_ids": sku_ids,
                })
    maximum = int(policy.get("execution", {}).get("max_actions_per_run", 100))
    max_terminations = int(policy.get("execution", {}).get("max_terminations_per_run", 25))
    if termination_count > max_terminations:
        raise LifecycleError(
            f"Termination safety limit exceeded: {termination_count} > {max_terminations}"
        )
    if len(actions) > maximum:
        raise LifecycleError(f"Action safety limit exceeded: {len(actions)} > {maximum}")
    return actions


class AuditLogger:
    """Append-only JSON Lines logger with secret-safe fields."""

    def __init__(self, directory: str | Path, run_id: str | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or str(uuid.uuid4())
        self.path = self.directory / f"identity-lifecycle-{dt.datetime.now(dt.timezone.utc):%Y%m%d}.jsonl"

    def emit(self, event: str, **fields: Any) -> None:
        record = {"timestamp": utc_now(), "run_id": self.run_id, "event": event, **fields}
        safe = {key: value for key, value in record.items() if key.lower() not in {"password", "secret", "access_token", "client_secret"}}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, sort_keys=True, default=str) + "\n")


class GraphClient:
    """Small Microsoft Graph v1.0 client with retry-after and transient retry handling."""

    def __init__(self, credential: Any, tenant_id: str, max_retries: int = 5, base_delay: float = 2.0):
        self.credential = credential
        self.tenant_id = tenant_id
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._token: Any = None

    @classmethod
    def from_default_credential(cls, tenant_id: str, max_retries: int = 5, base_delay: float = 2.0) -> "GraphClient":
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise LifecycleError("Install python/requirements.txt before apply mode") from exc
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        return cls(credential, tenant_id, max_retries, base_delay)

    def _access_token(self) -> str:
        token = self.credential.get_token("https://graph.microsoft.com/.default")
        return token.token

    @staticmethod
    def _error_message(body: bytes) -> str:
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
            return str(parsed.get("error", {}).get("message", parsed))[:500]
        except (ValueError, UnicodeDecodeError):
            return body.decode("utf-8", errors="replace")[:500]

    def request(
        self,
        method: str,
        path_or_url: str,
        body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201, 202, 204),
    ) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("http") else f"{GRAPH_ROOT}{path_or_url}"
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=encoded,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Project1-EntraIdentityLifecycle/1.0",
                },
                method=method.upper(),
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    status = response.status
                    payload = response.read()
                    if status not in expected:
                        raise GraphHttpError(status, self._error_message(payload), response.headers.get("request-id"))
                    if not payload:
                        return {}
                    return json.loads(payload.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                request_id = exc.headers.get("request-id") if exc.headers else None
                message = self._error_message(exc.read())
                retryable = exc.code == 429 or exc.code >= 500
                if not retryable or attempt >= self.max_retries:
                    raise GraphHttpError(exc.code, message, request_id) from exc
                retry_after = 0
                if exc.headers:
                    try:
                        retry_after = int(exc.headers.get("Retry-After", "0"))
                    except ValueError:
                        retry_after = 0
                time.sleep(max(retry_after, self.base_delay * (2 ** attempt) + random.random()))
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise LifecycleError(f"Graph network failure: {exc}") from exc
                time.sleep(self.base_delay * (2 ** attempt) + random.random())
        raise LifecycleError("Graph request exhausted retries")

    def list_all(self, path: str) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        next_url: str | None = path
        while next_url:
            page = self.request("GET", next_url)
            values.extend(page.get("value", []))
            next_url = page.get("@odata.nextLink")
        return values

    def get_user(self, upn: str) -> dict[str, Any] | None:
        path = f"/users/{urllib.parse.quote(upn, safe='@._-')}?$select=id,userPrincipalName,accountEnabled,assignedLicenses"
        try:
            return self.request("GET", path)
        except GraphHttpError as exc:
            if exc.status == 404:
                return None
            raise

    def ensure_user(self, worker: dict[str, str], policy: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_user(worker["upn"])
        if existing:
            self.request("PATCH", f"/users/{existing['id']}", {
                "accountEnabled": True,
                "displayName": worker["display_name"],
                "givenName": worker["first_name"],
                "surname": worker["last_name"],
                "department": worker["department"],
                "jobTitle": worker["job_title"],
                "employeeId": worker["worker_id"],
                "usageLocation": policy.get("default_usage_location", "US"),
            })
            return existing
        if policy.get("source_of_authority") in {"on_premises_ad", "hybrid"}:
            raise LifecycleError(
                f"Refusing cloud creation for {worker['upn']}: source_of_authority is {policy['source_of_authority']}"
            )
        password = os.environ.get("IDENTITY_LIFECYCLE_INITIAL_PASSWORD")
        if not password:
            raise LifecycleError(
                "IDENTITY_LIFECYCLE_INITIAL_PASSWORD must be supplied for first-time cloud user creation; "
                "do not put it in source files."
            )
        mail_nickname = re.sub(r"[^A-Za-z0-9._-]", "", worker["upn"].split("@", 1)[0])[:64]
        payload = {
            "accountEnabled": True,
            "displayName": worker["display_name"],
            "givenName": worker["first_name"],
            "surname": worker["last_name"],
            "department": worker["department"],
            "jobTitle": worker["job_title"],
            "employeeId": worker["worker_id"],
            "usageLocation": policy.get("default_usage_location", "US"),
            "mailNickname": mail_nickname or worker["worker_id"],
            "userPrincipalName": worker["upn"],
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": password,
            },
        }
        return self.request("POST", "/users", payload, expected=(201,))

    def user_id(self, upn: str) -> str:
        user = self.get_user(upn)
        if not user:
            raise LifecycleError(f"User not found: {upn}")
        return str(user["id"])

    def managed_group_memberships(self, user_id: str, managed_group_ids: set[str]) -> set[str]:
        memberships = self.list_all(f"/users/{user_id}/memberOf/microsoft.graph.group?$select=id")
        return {str(item["id"]) for item in memberships if str(item.get("id")) in managed_group_ids}

    def add_group_member(self, group_id: str, user_id: str) -> None:
        self.request("POST", f"/groups/{group_id}/members/$ref", {
            "@odata.id": f"{GRAPH_ROOT}/directoryObjects/{user_id}"
        }, expected=(204,))

    def remove_group_member(self, group_id: str, user_id: str) -> None:
        self.request("DELETE", f"/groups/{group_id}/members/{user_id}/$ref", expected=(204,))

    def assign_licenses(self, user_id: str, sku_ids: list[str]) -> None:
        self.request("POST", f"/users/{user_id}/assignLicense", {
            "addLicenses": [{"skuId": sku_id, "disabledPlans": []} for sku_id in sku_ids],
            "removeLicenses": [],
        })

    def remove_direct_licenses(self, user_id: str) -> list[str]:
        states = self.list_all(f"/users/{user_id}/licenseAssignmentStates?$select=skuId,assignedByGroup")
        direct_skus = sorted({str(item["skuId"]) for item in states if not item.get("assignedByGroup") and item.get("skuId")})
        if direct_skus:
            self.request("POST", f"/users/{user_id}/assignLicense", {
                "addLicenses": [], "removeLicenses": direct_skus,
            })
        return direct_skus


def generate_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        value = "".join(random.SystemRandom().choice(alphabet) for _ in range(length))
        if (any(c.isupper() for c in value) and any(c.islower() for c in value)
                and any(c.isdigit() for c in value) and any(c in "!@#$%^&*()-_=+" for c in value)):
            return value


def apply_action(client: GraphClient, action: dict[str, Any], workers_by_id: dict[str, dict[str, str]], policy: dict[str, Any], audit: AuditLogger) -> None:
    worker = workers_by_id[action["worker_id"]]
    upn = action["upn"]
    kind = action["action"]
    user_id = client.user_id(upn) if kind != "ensure_user" else None
    if kind == "ensure_user":
        user = client.ensure_user(worker, policy)
        audit.emit("user_ensured", action=kind, worker_id=action["worker_id"], upn=upn, object_id=user.get("id"))
    elif kind == "reconcile_managed_groups":
        desired = set(action["desired_group_ids"])
        managed = desired | {str(g) for g in policy.get("managed_group_ids", []) if not is_placeholder(str(g))}
        current = client.managed_group_memberships(user_id, managed)
        for group_id in sorted(desired - current):
            client.add_group_member(group_id, user_id)
            audit.emit("group_member_added", action=kind, worker_id=action["worker_id"], upn=upn, group_id=group_id, object_id=user_id)
        for group_id in sorted(current - desired):
            client.remove_group_member(group_id, user_id)
            audit.emit("group_member_removed", action=kind, worker_id=action["worker_id"], upn=upn, group_id=group_id, object_id=user_id)
    elif kind == "assign_direct_licenses":
        client.assign_licenses(user_id, action["sku_ids"])
        audit.emit("direct_licenses_assigned", action=kind, worker_id=action["worker_id"], upn=upn, sku_ids=action["sku_ids"], object_id=user_id)
    elif kind == "disable_user":
        client.request("PATCH", f"/users/{user_id}", {"accountEnabled": False})
        audit.emit("user_disabled", action=kind, worker_id=action["worker_id"], upn=upn, object_id=user_id)
    elif kind == "revoke_sign_in_sessions":
        client.request("POST", f"/users/{user_id}/revokeSignInSessions", expected=(200, 204))
        audit.emit("sessions_revoked", action=kind, worker_id=action["worker_id"], upn=upn, object_id=user_id)
    elif kind == "remove_managed_group_memberships":
        managed = {str(g) for g in policy.get("managed_group_ids", []) if not is_placeholder(str(g))}
        for mapping in policy.get("role_mappings", []):
            managed.update(str(g) for g in mapping.get("group_ids", []) if not is_placeholder(str(g)))
            managed.update(str(g) for g in mapping.get("license_group_ids", []) if not is_placeholder(str(g)))
        current = client.managed_group_memberships(user_id, managed)
        for group_id in sorted(current):
            client.remove_group_member(group_id, user_id)
            audit.emit("termination_group_removed", action=kind, worker_id=action["worker_id"], upn=upn, group_id=group_id, object_id=user_id)
    elif kind == "remove_direct_licenses":
        removed = client.remove_direct_licenses(user_id)
        audit.emit("direct_licenses_removed", action=kind, worker_id=action["worker_id"], upn=upn, sku_ids=removed, object_id=user_id)
    else:
        raise LifecycleError(f"Unsupported action: {kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Worker CSV path")
    parser.add_argument("--config", required=True, help="Policy JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Plan and log actions without calling Graph")
    parser.add_argument("--apply", action="store_true", help="Apply actions to the tenant")
    parser.add_argument("--today", help="Override today for deterministic testing, YYYY-MM-DD")
    args = parser.parse_args(argv)
    if args.dry_run and args.apply:
        parser.error("Choose only one of --dry-run or --apply")
    apply_mode = bool(args.apply)
    policy = load_json(args.config)
    if apply_mode:
        validate_policy(policy)
    workers = load_workers(args.input)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    actions = build_plan(workers, policy, today=today)
    log_dir = policy.get("execution", {}).get("audit_log_directory", "logs")
    audit = AuditLogger(log_dir)
    audit.emit("run_started", mode="apply" if apply_mode else "dry_run", input=args.input, action_count=len(actions))
    for action in actions:
        audit.emit("action_planned", **action)
    if apply_mode:
        client = GraphClient.from_default_credential(
            str(policy["tenant_id"]),
            int(policy.get("execution", {}).get("retry_attempts", 5)),
            float(policy.get("execution", {}).get("retry_base_seconds", 2)),
        )
        workers_by_id = {worker["worker_id"]: worker for worker in workers}
        for action in actions:
            try:
                apply_action(client, action, workers_by_id, policy, audit)
            except Exception as exc:  # noqa: BLE001 - log and fail closed for the run
                audit.emit("action_failed", action=action.get("action"), worker_id=action.get("worker_id"), upn=action.get("upn"), error=str(exc)[:500])
                raise
    audit.emit("run_completed", mode="apply" if apply_mode else "dry_run", action_count=len(actions))
    for action in actions:
        print(json.dumps(action, sort_keys=True))
    print(f"Audit log: {audit.path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LifecycleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
