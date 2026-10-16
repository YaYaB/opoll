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
"""
import os
import logging

from dotenv import load_dotenv

load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

from poll_logic import build_poll_blocks, parse_poll_text, parse_votes_from_blocks

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
        err = getattr(e, "response", None)
        err_code = err.get("error") if err and hasattr(err, "get") else None
        if err_code == "channel_not_found":
            msg = (
                "I can't post in this channel. "
                "Invite me here: type `/invite @YourPollApp` in the channel, "
                "or add the scope `chat:write.public` to the app (for public channels only)."
            )
        else:
            msg = f"Failed to create poll: {e}"
        try:
            respond(text=msg, response_type="ephemeral")
        except Exception:
            logger.exception("Could not send error reply to user")


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
