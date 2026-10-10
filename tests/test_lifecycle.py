import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from identity_lifecycle import AuditLogger, LifecycleError, build_plan, load_json, load_workers, validate_policy  # noqa: E402


class LifecyclePlanTests(unittest.TestCase):
    def setUp(self):
        self.policy = {
            "tenant_id": "tenant-id",
            "verified_domain": "contoso.example",
            "default_usage_location": "US",
            "source_of_authority": "cloud",
            "managed_group_ids": ["base-group"],
            "role_mappings": [
                {
                    "department": "Engineering",
                    "job_title": "Software Engineer",
                    "group_ids": ["engineering-group"],
                    "license_group_ids": ["m365-e3-group"],
                    "direct_license_sku_ids": [],
                }
            ],
            "termination": {
                "disable_account": True,
                "revoke_sign_in_sessions": True,
                "remove_managed_group_memberships": True,
                "remove_direct_licenses": True,
                "delete_user": False,
            },
            "execution": {"max_actions_per_run": 50, "max_terminations_per_run": 2},
        }

    def worker(self, **overrides):
        row = {
            "worker_id": "E1001",
            "first_name": "Adele",
            "last_name": "Vance",
            "upn": "adele.vance@contoso.example",
            "display_name": "Adele Vance",
            "department": "Engineering",
            "job_title": "Software Engineer",
            "employment_status": "Active",
            "start_date": "2026-09-01",
            "termination_date": "",
            "cost_center": "ENG-100",
            "location": "Seattle",
        }
        row.update(overrides)
        return row

    def test_active_worker_gets_ensure_and_group_reconciliation(self):
        actions = build_plan([self.worker()], self.policy, today=dt.date(2026, 9, 12))
        self.assertEqual([action["action"] for action in actions], ["ensure_user", "reconcile_managed_groups"])
        self.assertEqual(actions[1]["desired_group_ids"], ["base-group", "engineering-group", "m365-e3-group"])

    def test_termination_date_is_a_termination_signal(self):
        actions = build_plan(
            [self.worker(termination_date="2026-09-10", employment_status="Active")],
            self.policy,
            today=dt.date(2026, 9, 12),
        )
        self.assertEqual(
            [action["action"] for action in actions],
            ["disable_user", "revoke_sign_in_sessions", "remove_managed_group_memberships", "remove_direct_licenses"],
        )

    def test_termination_guard_fails_closed(self):
        policy = dict(self.policy)
        policy["execution"] = {"max_actions_per_run": 50, "max_terminations_per_run": 0}
        with self.assertRaises(LifecycleError):
            build_plan([self.worker(employment_status="Terminated")], policy)

    def test_apply_policy_rejects_placeholder_ids(self):
        policy = json.loads(json.dumps(self.policy))
        policy["role_mappings"][0]["group_ids"] = ["REPLACE_WITH_GROUP_ID"]
        with self.assertRaises(LifecycleError):
            validate_policy(policy)

    def test_direct_license_action_is_only_created_for_explicit_sku_mapping(self):
        policy = json.loads(json.dumps(self.policy))
        policy["role_mappings"][0]["direct_license_sku_ids"] = ["sku-123"]
        actions = build_plan([self.worker()], policy)
        self.assertEqual(actions[-1]["action"], "assign_direct_licenses")
        self.assertEqual(actions[-1]["sku_ids"], ["sku-123"])

    def test_audit_logger_excludes_secret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = AuditLogger(directory, run_id="test-run")
            logger.emit("test", password="never-write", result="ok")
            content = logger.path.read_text(encoding="utf-8")
            self.assertNotIn("never-write", content)
            self.assertIn('"result": "ok"', content)

    def test_sample_files_load(self):
        workers = load_workers(ROOT / "data" / "sample-workers.csv")
        policy = load_json(ROOT / "config" / "policy.json")
        self.assertEqual(len(workers), 3)
        self.assertEqual(policy["source_of_authority"], "cloud")


if __name__ == "__main__":
    unittest.main()
