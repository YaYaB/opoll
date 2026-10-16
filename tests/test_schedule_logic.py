import datetime
import unittest
from zoneinfo import ZoneInfo

from poll_logic import parse_poll_text
from schedule_logic import (
    ScheduleError,
    get_subcommand,
    next_weekday,
    occurrences,
    parse_schedule_text,
    render_question,
)

PARIS = ZoneInfo("Europe/Paris")

REMOTE_POLL = (
    'schedule friday 12:00 every 2 weeks multiple "On which days do you remote the week beginning on '
    'Monday {next_monday} (Mandatory days in the office: Monday, Tuesday, Thursday)?" '
    '"Monday Morning" "Monday Afternoon" "Tuesday Morning"'
)


class GetSubcommandTest(unittest.TestCase):
    def test_subcommands(self):
        self.assertEqual(get_subcommand("schedule friday 12:00 x"), "schedule")
        self.assertEqual(get_subcommand("  Scheduled"), "scheduled")
        self.assertEqual(get_subcommand("unschedule all"), "unschedule")

    def test_regular_polls_are_not_subcommands(self):
        self.assertIsNone(get_subcommand('multiple "Q?" "A" "B"'))
        self.assertIsNone(get_subcommand("Schedules for next week? • A • B"))
        self.assertIsNone(get_subcommand(""))


class ParseScheduleTextTest(unittest.TestCase):
    def test_full_spec(self):
        spec = parse_schedule_text(REMOTE_POLL)
        self.assertEqual(spec.weekday, 4)
        self.assertEqual(spec.time, datetime.time(12, 0))
        self.assertEqual(spec.every_weeks, 2)
        self.assertIsNone(spec.start)
        self.assertIsNone(spec.times)
        question, options, multiple = parse_poll_text(spec.poll_text)
        self.assertTrue(multiple)
        self.assertIn("{next_monday}", question)
        self.assertEqual(options, ["Monday Morning", "Monday Afternoon", "Tuesday Morning"])

    def test_defaults_to_weekly(self):
        spec = parse_schedule_text('schedule Monday at 9:30 "Q?" "A" "B"')
        self.assertEqual((spec.weekday, spec.time, spec.every_weeks), (0, datetime.time(9, 30), 1))

    def test_every_week_starting_times(self):
        spec = parse_schedule_text('schedule friday 08:00 every week starting 2026-11-06 times 3 "Q?" "A"')
        self.assertEqual(spec.every_weeks, 1)
        self.assertEqual(spec.start, datetime.date(2026, 11, 6))
        self.assertEqual(spec.times, 3)

    def test_invalid_inputs(self):
        for text in [
            "schedule",
            'schedule funday 12:00 "Q?" "A"',
            'schedule friday 25:00 "Q?" "A"',
            'schedule friday 12:00 every 0 weeks "Q?" "A"',
            'schedule friday 12:00 times 0 "Q?" "A"',
            'schedule friday 12:00 starting 2026-02-30 "Q?" "A"',
            "schedule friday 12:00",
        ]:
            with self.subTest(text=text), self.assertRaises(ScheduleError):
                parse_schedule_text(text)


class OccurrencesTest(unittest.TestCase):
    def test_weekly_fills_120_days(self):
        now = datetime.datetime(2026, 10, 17, 10, 0, tzinfo=PARIS)  # Saturday
        spec = parse_schedule_text('schedule friday 12:00 "Q?" "A"')
        result = occurrences(spec, now)
        self.assertEqual(result[0], datetime.datetime(2026, 10, 23, 12, 0, tzinfo=PARIS))
        self.assertEqual(len(result), 17)
        self.assertTrue(all(dt - now <= datetime.timedelta(days=120) for dt in result))

    def test_keeps_local_time_across_dst(self):
        now = datetime.datetime(2026, 10, 17, 10, 0, tzinfo=PARIS)
        spec = parse_schedule_text('schedule friday 12:00 times 3 "Q?" "A"')
        result = occurrences(spec, now)
        # Paris leaves summer time on 2026-10-25: same wall clock, different UTC offset.
        self.assertEqual([dt.hour for dt in result], [12, 12, 12])
        self.assertNotEqual(result[0].utcoffset(), result[1].utcoffset())

    def test_today_if_time_not_passed_yet(self):
        now = datetime.datetime(2026, 10, 23, 11, 0, tzinfo=PARIS)  # Friday 11:00
        spec = parse_schedule_text('schedule friday 12:00 times 1 "Q?" "A"')
        self.assertEqual(occurrences(spec, now)[0].date(), datetime.date(2026, 10, 23))

    def test_next_week_if_time_passed(self):
        now = datetime.datetime(2026, 10, 23, 12, 30, tzinfo=PARIS)
        spec = parse_schedule_text('schedule friday 12:00 times 1 "Q?" "A"')
        self.assertEqual(occurrences(spec, now)[0].date(), datetime.date(2026, 10, 30))

    def test_every_two_weeks_keeps_parity_of_past_start(self):
        now = datetime.datetime(2026, 10, 17, 10, 0, tzinfo=PARIS)
        spec = parse_schedule_text('schedule friday 12:00 every 2 weeks starting 2026-10-02 times 2 "Q?" "A"')
        self.assertEqual(
            [dt.date() for dt in occurrences(spec, now)],
            [datetime.date(2026, 10, 30), datetime.date(2026, 11, 13)],
        )

    def test_start_beyond_slack_limit(self):
        now = datetime.datetime(2026, 10, 17, 10, 0, tzinfo=PARIS)
        spec = parse_schedule_text('schedule friday 12:00 starting 2027-06-01 "Q?" "A"')
        self.assertEqual(occurrences(spec, now), [])


class RenderQuestionTest(unittest.TestCase):
    def test_next_monday_from_friday(self):
        self.assertEqual(
            render_question("Week beginning on Monday {next_monday}?", datetime.date(2026, 9, 4)),
            "Week beginning on Monday 2026-09-07?",
        )

    def test_custom_format_and_other_weekday(self):
        self.assertEqual(
            render_question("{next_Friday:%d/%m} and {next_monday:%A %d %B}", datetime.date(2026, 9, 4)),
            "11/09 and Monday 07 September",
        )

    def test_unknown_placeholders_untouched(self):
        self.assertEqual(render_question("{foo} {next_moon}", datetime.date(2026, 9, 4)), "{foo} {next_moon}")

    def test_next_weekday_is_strictly_after(self):
        self.assertEqual(next_weekday(datetime.date(2026, 9, 7), 0), datetime.date(2026, 9, 14))


if __name__ == "__main__":
    unittest.main()
