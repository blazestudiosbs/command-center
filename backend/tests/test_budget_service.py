import os
import tempfile
import unittest
from unittest.mock import patch

from services import budget_service
from storage import initialize_storage


class BudgetServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"VERA_DATABASE_PATH": os.path.join(self.temp_dir.name, "vera-test.db")},
            clear=False,
        )
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_small_request_is_allowed_and_recorded_without_spend(self):
        result = budget_service.simulate(prompt="Hello Vera", max_output_tokens=400)

        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["mode"], "simulation")
        self.assertIsNone(result["actual_cost_usd"])
        self.assertGreater(result["estimated_cost_usd"], 0)
        self.assertEqual(len(budget_service.list_ledger()), 1)
        self.assertEqual(budget_service.get_status()["spent"]["daily_usd"], 0)

    def test_request_over_per_request_limit_is_blocked(self):
        with patch.dict(os.environ, {"VERA_BUDGET_PER_REQUEST_USD": "0.000001"}):
            result = budget_service.simulate(prompt="Hello Vera", max_output_tokens=400)

        self.assertEqual(result["decision"], "block")
        self.assertIn("per-request", result["reason"])

    def test_explicit_input_token_estimate_is_used(self):
        result = budget_service.simulate(
            prompt="ignored for token estimation",
            input_tokens=1234,
            max_output_tokens=50,
            domain="development",
        )

        self.assertEqual(result["input_tokens"], 1234)
        self.assertEqual(result["domain"], "development")

    def test_invalid_environment_values_fall_back_to_safe_defaults(self):
        with patch.dict(
            os.environ,
            {
                "VERA_BUDGET_DAILY_USD": "not-a-number",
                "VERA_BUDGET_MONTHLY_USD": "-1",
            },
        ):
            config = budget_service.get_config()

        self.assertEqual(config["limits"]["daily_usd"], 0.50)
        self.assertEqual(config["limits"]["monthly_usd"], 5.00)

    def test_live_request_reserves_then_settles_reported_usage(self):
        reservation = budget_service.reserve_live(
            prompt="Hello Vera",
            max_output_tokens=400,
            domain="general",
            model="gpt-4.1-mini",
        )
        reserved_status = budget_service.get_status()
        self.assertGreater(reserved_status["spent"]["daily_usd"], 0)

        settled = budget_service.settle_live(
            reservation["id"], input_tokens=6, output_tokens=20
        )
        self.assertLess(settled["actual_cost_usd"], reservation["reserved_cost_usd"])

    def test_live_reservation_fails_closed_at_limit(self):
        with patch.dict(os.environ, {"VERA_BUDGET_PER_REQUEST_USD": "0"}):
            with self.assertRaises(budget_service.BudgetDeniedError):
                budget_service.reserve_live(
                    prompt="Hello Vera",
                    max_output_tokens=400,
                    domain="general",
                    model="gpt-4.1-mini",
                )


if __name__ == "__main__":
    unittest.main()
