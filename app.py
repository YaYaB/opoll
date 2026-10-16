"""
Open-source Slack poll app.
Usage:
  Single choice (one vote per user):
    /opoll <question>
    • Option A
    • Option B
    /opoll "Question?" "A" "B" "C"   # quoted, space-separated
  Multiple choice (vote for several options; click again to remove):
    /opoll multiple <question>
    • Option A
    • Option B
    /opoll multiple "Question?" "A" "B" "C"
  Recurring polls (queued in Slack with chat.scheduleMessage, up to 120 days ahead):
    /opoll schedule friday 12:00 every 2 weeks multiple "Week of Monday {next_monday}?" "A" "B"
    /opoll scheduled            # list polls queued in this channel
    /opoll unschedule <id|all>  # cancel one or all of them
"""
import datetime
import os
import logging
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

from slack_sdk.errors import SlackApiError

from poll_logic import build_poll_blocks, parse_poll_text, parse_votes_from_blocks
from schedule_logic import (
    ScheduleError,
    get_subcommand,
    occurrences,
    parse_schedule_text,
    render_question,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


@app.command("/opoll")
def handle_poll_command(ack, body, client, command, respond):
    """Handle /opoll  <question> with bullet list of options."""
    ack()
    text = command.get("text", "")
    channel_id = body.get("channel_id")
    user_id = body.get("user_id")

    subcommand = get_subcommand(text)
    if subcommand == "schedule":
        return handle_schedule(client, channel_id, text, respond)
    if subcommand == "scheduled":
        return handle_list_scheduled(client, channel_id, respond)
    if subcommand == "unschedule":
        return handle_unschedule(client, channel_id, text, respond)

    question, options, multiple_choice = parse_poll_text(text)
    blocks = build_poll_blocks(question, options, multiple_choice=multiple_choice)
    fallback = f"Poll: {question} ({len(options)} options)"

    try:
        client.chat_postMessage(
            channel=channel_id,
            text=fallback,
            blocks=blocks,
        )
    except Exception as e:
        logger.exception("Failed to post poll")
        reply_ephemeral(respond, slack_error_message(e, "Failed to create poll"))


def slack_error_message(e: Exception, prefix: str) -> str:
    err = getattr(e, "response", None)
    err_code = err.get("error") if err and hasattr(err, "get") else None
    if err_code == "channel_not_found":
        return (
            "I can't post in this channel. "
            "Invite me here: type `/invite @YourPollApp` in the channel, "
            "or add the scope `chat:write.public` to the app (for public channels only)."
        )
    return f"{prefix}: {e}"


def reply_ephemeral(respond, text: str) -> None:
    try:
        respond(text=text, response_type="ephemeral")
    except Exception:
        logger.exception("Could not send reply to user")


def schedule_timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("OPOLL_TIMEZONE", "UTC"))


def handle_schedule(client, channel_id, text, respond):
    """/opoll schedule ...: queue every occurrence of a recurring poll in Slack."""
    try:
        spec = parse_schedule_text(text)
    except ScheduleError as e:
        return reply_ephemeral(respond, str(e))

    tz = schedule_timezone()
    post_times = occurrences(spec, datetime.datetime.now(tz))
    if not post_times:
        return reply_ephemeral(
            respond, "Nothing to schedule: the first occurrence is more than 120 days away (Slack's limit)."
        )

    question_template, options, multiple_choice = parse_poll_text(spec.poll_text)
    scheduled = []
    for post_at in post_times:
        question = render_question(question_template, post_at.date())
        try:
            client.chat_scheduleMessage(
                channel=channel_id,
                post_at=int(post_at.timestamp()),
                text=f"Poll: {question} ({len(options)} options)",
                blocks=build_poll_blocks(question, options, multiple_choice=multiple_choice),
            )
        except SlackApiError as e:
            logger.exception("Failed to schedule poll")
            done = f"Scheduled {len(scheduled)} of {len(post_times)} polls. " if scheduled else ""
            return reply_ephemeral(respond, done + slack_error_message(e, "Failed to schedule poll"))
        scheduled.append(post_at)

    dates = "\n".join(f"• {dt:%a %Y-%m-%d %H:%M}" for dt in scheduled)
    reply_ephemeral(
        respond,
        f"Scheduled {len(scheduled)} poll(s) ({tz.key}):\n{dates}\n"
        "Run `/opoll schedule ...` again later to extend beyond 120 days.",
    )


def list_scheduled_messages(client, channel_id) -> list[dict]:
    messages, cursor = [], None
    while True:
        resp = client.chat_scheduledMessages_list(channel=channel_id, cursor=cursor, limit=100)
        messages.extend(resp.get("scheduled_messages", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return sorted(messages, key=lambda m: m.get("post_at", 0))


def handle_list_scheduled(client, channel_id, respond):
    """/opoll scheduled: list polls queued in this channel."""
    try:
        messages = list_scheduled_messages(client, channel_id)
    except SlackApiError as e:
        logger.exception("Failed to list scheduled polls")
        return reply_ephemeral(respond, slack_error_message(e, "Failed to list scheduled polls"))
    if not messages:
        return reply_ephemeral(respond, "No poll scheduled in this channel.")

    tz = schedule_timezone()
    lines = [
        f"• `{m['id']}` {datetime.datetime.fromtimestamp(m['post_at'], tz):%a %Y-%m-%d %H:%M} — {m.get('text', '')}"
        for m in messages
    ]
    reply_ephemeral(respond, f"Scheduled polls ({tz.key}):\n" + "\n".join(lines))


def handle_unschedule(client, channel_id, text, respond):
    """/opoll unschedule <id|all>: cancel queued polls in this channel."""
    target = text.strip().split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
    if not target:
        return reply_ephemeral(respond, "Usage: `/opoll unschedule <id|all>` (ids from `/opoll scheduled`).")

    try:
        ids = [m["id"] for m in list_scheduled_messages(client, channel_id)] if target.lower() == "all" else [target]
        for scheduled_id in ids:
            client.chat_deleteScheduledMessage(channel=channel_id, scheduled_message_id=scheduled_id)
    except SlackApiError as e:
        logger.exception("Failed to cancel scheduled poll")
        return reply_ephemeral(respond, slack_error_message(e, "Failed to cancel scheduled poll"))
    reply_ephemeral(respond, f"Cancelled {len(ids)} scheduled poll(s).")


@app.action("vote")
def handle_vote(ack, body, client):
    """Handle Vote button click: add user to option and update message."""
    ack()

    user_id = body.get("user", {}).get("id")
    channel_id = body.get("channel", {}).get("id")
    message_ts = body.get("message", {}).get("ts")
    message_blocks = body.get("message", {}).get("blocks", [])
    action = (body.get("actions") or [{}])[0]
    option_index = int(action.get("value", 0))

    question, options, votes, multiple_choice = parse_votes_from_blocks(message_blocks)
    if not options:
        return

    if multiple_choice:
        # Toggle: if already voted for this option, remove; otherwise add (and keep other votes)
        if user_id in votes.get(option_index, []):
            votes[option_index].remove(user_id)
        else:
            votes.setdefault(option_index, []).append(user_id)
    else:
        # Single choice: remove from any other option, add to selected
        for idx in votes:
            if user_id in votes[idx]:
                votes[idx].remove(user_id)
        votes.setdefault(option_index, []).append(user_id)

    new_blocks = build_poll_blocks(question, options, votes, multiple_choice=multiple_choice)
    fallback = f"Poll: {question} ({len(options)} options)"

    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=fallback,
            blocks=new_blocks,
        )
    except Exception as e:
        logger.exception("Failed to update poll after vote")


# Flask app for HTTP request handling
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/", methods=["GET"])
def health_check():
    """Basic health check endpoint for Elastic Beanstalk."""
    return "OK", 200


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    """Single endpoint for slash commands and interactivity (button clicks)."""
    try:
        logger.info(f"Received Slack request: {request.method} {request.path}")
        result = handler.handle(request)
        logger.info("Slack request handled successfully")
        return result
    except Exception as e:
        logger.exception(f"Error handling Slack request: {e}")
        # Log request details for debugging
        logger.error(f"Request headers: {dict(request.headers)}")
        logger.error(f"Request data: {request.get_data(as_text=True)[:500]}")
        # Return 200 to prevent Slack from retrying invalid requests
        return {"error": str(e)}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
