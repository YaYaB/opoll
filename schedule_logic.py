"""Pure logic for `/opoll schedule`: parse the schedule spec, compute when each
occurrence is posted, and render date placeholders in the question. No Slack
dependencies here, so it can be unit-tested without a token or network.

The polls themselves are queued with Slack's chat.scheduleMessage, so no
database or background scheduler is needed on our side.
"""
import datetime
import re
from dataclasses import dataclass

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAY_ALT = "|".join(WEEKDAYS)

# Slack refuses chat.scheduleMessage more than 120 days in the future.
MAX_SCHEDULE_DAYS = 120
# Slack rejects post_at values in the past; keep a margin for request latency.
MIN_LEAD_TIME = datetime.timedelta(minutes=1)

SCHEDULE_USAGE = (
    "Usage: `/opoll schedule <weekday> <HH:MM> [every N weeks] [starting YYYY-MM-DD] "
    '[times N] [multiple] "Question?" "Option 1" "Option 2"`\n'
    "Example: `/opoll schedule friday 12:00 every 2 weeks multiple "
    '"Remote days for the week of Monday {next_monday}?" "Monday" "Tuesday"`\n'
    "Placeholders: `{next_monday}` ... `{next_sunday}` are replaced by the next such day after "
    "the posting date (`{next_monday:%d/%m}` for a custom format).\n"
    "Without `times`, every occurrence within the next 120 days is scheduled (Slack's limit).\n"
    "See queued polls with `/opoll scheduled`, cancel with `/opoll unschedule <id|all>`."
)

_SCHEDULE_RE = re.compile(
    rf"^schedule\s+(?P<weekday>{_WEEKDAY_ALT})"
    r"\s+(?:at\s+)?(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"(?:\s+every\s+(?:(?P<every>\d+)\s+)?weeks?)?"
    r"(?:\s+starting\s+(?P<start>\d{4}-\d{2}-\d{2}))?"
    r"(?:\s+times\s+(?P<times>\d+))?"
    r"\s+(?P<poll_text>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)

_PLACEHOLDER_RE = re.compile(rf"\{{next_(?P<weekday>{_WEEKDAY_ALT})(?::(?P<fmt>[^}}]+))?\}}", re.IGNORECASE)


class ScheduleError(ValueError):
    """Invalid `/opoll schedule` input; the message is safe to show to the user."""


@dataclass
class ScheduleSpec:
    weekday: int  # 0 = Monday
    time: datetime.time
    every_weeks: int
    start: datetime.date | None
    times: int | None
    poll_text: str  # remaining text, parsed by poll_logic.parse_poll_text


def get_subcommand(text: str) -> str | None:
    """Return 'schedule', 'scheduled' or 'unschedule' if text starts with one, else None."""
    match = re.match(r"^(schedule|scheduled|unschedule)\b", (text or "").strip(), re.IGNORECASE)
    return match.group(1).lower() if match else None


def parse_schedule_text(text: str) -> ScheduleSpec:
    match = _SCHEDULE_RE.match((text or "").strip())
    if not match:
        raise ScheduleError(SCHEDULE_USAGE)

    hour, minute = int(match["hour"]), int(match["minute"])
    if hour > 23 or minute > 59:
        raise ScheduleError(f"Invalid time {match['hour']}:{match['minute']}.\n{SCHEDULE_USAGE}")

    every_weeks = int(match["every"]) if match["every"] else 1
    if every_weeks < 1:
        raise ScheduleError("`every` must be at least 1 week.")

    times = int(match["times"]) if match["times"] else None
    if times is not None and times < 1:
        raise ScheduleError("`times` must be at least 1.")

    start = None
    if match["start"]:
        try:
            start = datetime.date.fromisoformat(match["start"])
        except ValueError:
            raise ScheduleError(f"Invalid start date {match['start']}.") from None

    return ScheduleSpec(
        weekday=WEEKDAYS.index(match["weekday"].lower()),
        time=datetime.time(hour, minute),
        every_weeks=every_weeks,
        start=start,
        times=times,
        poll_text=match["poll_text"],
    )


def occurrences(spec: ScheduleSpec, now: datetime.datetime) -> list[datetime.datetime]:
    """Posting datetimes (in now's timezone) for spec, within Slack's 120-day window.

    The first occurrence is the first matching weekday on or after `starting`
    (default: today) whose time is still ahead of now; the following ones are
    every `every_weeks` weeks after it, keeping the same local wall-clock time.
    """
    tz = now.tzinfo
    base = spec.start or now.date()
    day = base + datetime.timedelta(days=(spec.weekday - base.weekday()) % 7)
    step = datetime.timedelta(weeks=spec.every_weeks)
    earliest = now + MIN_LEAD_TIME
    latest = now + datetime.timedelta(days=MAX_SCHEDULE_DAYS)

    while datetime.datetime.combine(day, spec.time, tzinfo=tz) < earliest:
        day += step

    result = []
    while spec.times is None or len(result) < spec.times:
        post_at = datetime.datetime.combine(day, spec.time, tzinfo=tz)
        if post_at > latest:
            break
        result.append(post_at)
        day += step
    return result


def next_weekday(after: datetime.date, weekday: int) -> datetime.date:
    """Next date with the given weekday strictly after `after`."""
    return after + datetime.timedelta(days=(weekday - after.weekday() - 1) % 7 + 1)


def render_question(template: str, post_date: datetime.date) -> str:
    """Replace {next_<weekday>} / {next_<weekday>:<strftime>} placeholders."""

    def replace(match: re.Match) -> str:
        day = next_weekday(post_date, WEEKDAYS.index(match["weekday"].lower()))
        return day.strftime(match["fmt"] or "%Y-%m-%d")

    return _PLACEHOLDER_RE.sub(replace, template)
