import datetime
import os
import unittest
from unittest import mock

from slack_sdk.errors import SlackApiError

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-secret")
# The Bolt App verifies its token with auth.test at import time; keep tests offline.
with mock.patch("slack_sdk.web.client.WebClient.auth_test", return_value={"ok": True}):
    import app  # noqa: E402

from poll_logic import parse_votes_from_blocks  # noqa: E402

COMMAND = (
    'schedule friday 12:00 every 2 weeks times 2 multiple "Remote the week of Monday {next_monday}?" '
    '"Monday Morning" "Monday Afternoon"'
)


class FakeClient:
    def __init__(self, fail_after=None):
        self.scheduled = []
        self.deleted = []
        self.fail_after = fail_after

    def chat_scheduleMessage(self, **kwargs):
        if self.fail_after is not None and len(self.scheduled) >= self.fail_after:
            raise SlackApiError("boom", {"ok": False, "error": "time_in_past"})
        self.scheduled.append(kwargs)

    def chat_scheduledMessages_list(self, **kwargs):
        return {"scheduled_messages": [{"id": "Q2", "post_at": 2}, {"id": "Q1", "post_at": 1}]}

    def chat_deleteScheduledMessage(self, **kwargs):
        self.deleted.append(kwargs["scheduled_message_id"])


@mock.patch.dict(os.environ, {"OPOLL_TIMEZONE": "Europe/Paris"})
class HandleScheduleTest(unittest.TestCase):
    def test_schedules_rendered_votable_polls(self):
        client, respond = FakeClient(), mock.Mock()
        app.handle_schedule(client, "C1", COMMAND, respond)

        self.assertEqual(len(client.scheduled), 2)
        first = client.scheduled[0]
        self.assertEqual(first["channel"], "C1")
        post_at = datetime.datetime.fromtimestamp(first["post_at"], app.schedule_timezone())
        self.assertEqual((post_at.weekday(), post_at.hour), (4, 12))
        monday = post_at.date() + datetime.timedelta(days=3)

        question, options, votes, multiple = parse_votes_from_blocks(first["blocks"])
        self.assertEqual(question, f"Remote the week of Monday {monday:%Y-%m-%d}?")
        self.assertEqual(options, ["Monday Morning", "Monday Afternoon"])
        self.assertTrue(multiple)
        second = datetime.datetime.fromtimestamp(client.scheduled[1]["post_at"], app.schedule_timezone())
        self.assertEqual((second.date() - post_at.date()).days, 14)
        self.assertEqual(second.hour, 12)
        self.assertIn("Scheduled 2 poll(s)", respond.call_args.kwargs["text"])

    def test_reports_partial_failure(self):
        client, respond = FakeClient(fail_after=1), mock.Mock()
        app.handle_schedule(client, "C1", COMMAND, respond)
        self.assertIn("Scheduled 1 of 2 polls", respond.call_args.kwargs["text"])

    def test_usage_on_bad_input(self):
        client, respond = FakeClient(), mock.Mock()
        app.handle_schedule(client, "C1", "schedule someday", respond)
        self.assertEqual(client.scheduled, [])
        self.assertIn("Usage", respond.call_args.kwargs["text"])


class HandleUnscheduleTest(unittest.TestCase):
    def test_all(self):
        client, respond = FakeClient(), mock.Mock()
        app.handle_unschedule(client, "C1", "unschedule all", respond)
        self.assertEqual(client.deleted, ["Q1", "Q2"])

    def test_one(self):
        client, respond = FakeClient(), mock.Mock()
        app.handle_unschedule(client, "C1", "unschedule Q123", respond)
        self.assertEqual(client.deleted, ["Q123"])

    def test_missing_target(self):
        client, respond = FakeClient(), mock.Mock()
        app.handle_unschedule(client, "C1", "unschedule", respond)
        self.assertEqual(client.deleted, [])
        self.assertIn("Usage", respond.call_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
