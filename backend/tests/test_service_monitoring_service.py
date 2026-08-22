import os
import tempfile
import unittest
from unittest.mock import patch

from services import audit_service, service_monitoring_service
from storage import initialize_storage


class ServiceMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "vera.db")
        self.env = patch.dict(
            os.environ,
            {
                "VERA_DATABASE_PATH": self.db_path,
                "VERA_MONITORED_CONTAINERS": "command-center,plex",
                "VERA_MONITOR_ALERT_COOLDOWN_SECONDS": "300",
            },
        )
        self.env.start()
        initialize_storage()

    def tearDown(self):
        self.env.stop()
        self.temp_dir.cleanup()

    def test_baseline_does_not_alert_or_create_transition(self):
        notifications = []
        transitions = service_monitoring_service.record_snapshot(
            {
                "command-center": {"status": "running", "detail": "Docker status: running."},
                "plex": {"status": "missing", "detail": "Container was not found."},
            },
            now="2026-08-21T12:00:00Z",
            notifier=lambda *args: notifications.append(args) or {"sent": True},
        )

        self.assertEqual(transitions, [])
        self.assertEqual(notifications, [])
        status = service_monitoring_service.get_status()
        self.assertEqual(status["summary"], {"total": 2, "healthy": 1, "unavailable": 1, "pending": 0})
        self.assertFalse(status["automatic_restarts"])

    def test_state_changes_are_journaled_and_not_duplicated(self):
        running = {
            "command-center": {"status": "running", "detail": "Docker status: running."},
            "plex": {"status": "running", "detail": "Docker status: running."},
        }
        service_monitoring_service.record_snapshot(running, now="2026-08-21T12:00:00Z")
        notifications = []
        stopped = dict(running)
        stopped["plex"] = {"status": "stopped", "detail": "Docker status: exited."}

        first = service_monitoring_service.record_snapshot(
            stopped,
            now="2026-08-21T12:01:00Z",
            notifier=lambda *args: notifications.append(args) or {"sent": True},
        )
        second = service_monitoring_service.record_snapshot(
            stopped,
            now="2026-08-21T12:02:00Z",
            notifier=lambda *args: notifications.append(args) or {"sent": True},
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(notifications), 1)
        event = audit_service.list_events()[0]
        self.assertEqual(event["action"], "service_monitor.outage")
        self.assertEqual(event["resource_id"], "plex")
        self.assertEqual(event["outcome"], "failed")

    def test_cooldown_suppresses_flapping_alert_but_keeps_journal(self):
        notifications = []
        notify = lambda *args: notifications.append(args) or {"sent": True}
        running = {name: {"status": "running", "detail": "running"} for name in ("command-center", "plex")}
        stopped = dict(running)
        stopped["plex"] = {"status": "stopped", "detail": "exited"}
        service_monitoring_service.record_snapshot(running, now="2026-08-21T12:00:00Z", notifier=notify)
        service_monitoring_service.record_snapshot(stopped, now="2026-08-21T12:01:00Z", notifier=notify)
        recovery = service_monitoring_service.record_snapshot(running, now="2026-08-21T12:02:00Z", notifier=notify)

        self.assertEqual(len(notifications), 1)
        self.assertEqual(recovery[0]["alert_suppressed"], "cooldown")
        self.assertEqual(audit_service.list_events()[0]["action"], "service_monitor.recovery")

    def test_notification_preferences_are_persisted(self):
        preferences = service_monitoring_service.set_notification_preferences(
            alerts_enabled=False,
            cooldown=900,
            services=[
                {
                    "container_name": "plex",
                    "outage_alerts_enabled": True,
                    "recovery_alerts_enabled": False,
                }
            ],
        )

        self.assertFalse(preferences["alerts_enabled"])
        self.assertEqual(preferences["cooldown_seconds"], 900)
        plex = next(item for item in preferences["services"] if item["container_name"] == "plex")
        self.assertTrue(plex["outage_alerts_enabled"])
        self.assertFalse(plex["recovery_alerts_enabled"])

    def test_disabled_alerts_still_record_transition(self):
        service_monitoring_service.set_notification_preferences(
            alerts_enabled=False,
            cooldown=300,
            services=[],
        )
        running = {name: {"status": "running", "detail": "running"} for name in ("command-center", "plex")}
        stopped = dict(running)
        stopped["plex"] = {"status": "stopped", "detail": "exited"}
        notifications = []
        service_monitoring_service.record_snapshot(running, now="2026-08-21T12:00:00Z")
        transition = service_monitoring_service.record_snapshot(
            stopped,
            now="2026-08-21T12:01:00Z",
            notifier=lambda *args: notifications.append(args) or {"sent": True},
        )

        self.assertEqual(notifications, [])
        self.assertEqual(transition[0]["alert_suppressed"], "alerts_disabled")
        self.assertEqual(audit_service.list_events()[0]["action"], "service_monitor.outage")

    def test_unknown_service_preference_is_rejected(self):
        with self.assertRaises(ValueError):
            service_monitoring_service.set_notification_preferences(
                alerts_enabled=True,
                cooldown=300,
                services=[
                    {
                        "container_name": "not-configured",
                        "outage_alerts_enabled": True,
                        "recovery_alerts_enabled": True,
                    }
                ],
            )

    def test_history_returns_recent_outages_and_recoveries(self):
        service_monitoring_service.set_notification_preferences(
            alerts_enabled=False,
            cooldown=300,
            services=[],
        )
        running = {name: {"status": "running", "detail": "running"} for name in ("command-center", "plex")}
        stopped = dict(running)
        stopped["plex"] = {"status": "stopped", "detail": "exited"}
        service_monitoring_service.record_snapshot(running, now="2026-08-21T12:00:00Z")
        service_monitoring_service.record_snapshot(stopped, now="2026-08-21T12:01:00Z")
        service_monitoring_service.record_snapshot(running, now="2026-08-21T12:02:00Z")

        history = service_monitoring_service.get_history(limit=10)

        self.assertEqual([event["event"] for event in history], ["recovery", "outage"])
        self.assertEqual(history[0]["display_name"], "Plex")
        self.assertEqual(history[0]["from_status"], "stopped")
        self.assertEqual(history[0]["to_status"], "running")
        self.assertFalse(history[0]["alert_sent"])


if __name__ == "__main__":
    unittest.main()
