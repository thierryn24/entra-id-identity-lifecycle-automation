import unittest

from python.stage2_preflight import group_is_safe, select_worker
from python.identity_lifecycle import LifecycleError


class Stage2PreflightTests(unittest.TestCase):
    def test_select_worker_requires_one_worker_without_filter(self):
        worker = {"worker_id": "STAGE2-001", "upn": "stage2@example.invalid"}
        self.assertEqual(select_worker([worker], None), worker)

    def test_select_worker_rejects_ambiguous_feed(self):
        workers = [
            {"worker_id": "STAGE2-001", "upn": "one@example.invalid"},
            {"worker_id": "STAGE2-002", "upn": "two@example.invalid"},
        ]
        with self.assertRaises(LifecycleError):
            select_worker(workers, None)

    def test_group_safety_rejects_role_assignable_group(self):
        safe, failures = group_is_safe({"securityEnabled": True, "isAssignableToRole": True})
        self.assertFalse(safe)
        self.assertIn("group is role-assignable", failures)

    def test_group_safety_accepts_non_role_assignable_security_group(self):
        safe, failures = group_is_safe({"securityEnabled": True, "isAssignableToRole": False})
        self.assertTrue(safe)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
