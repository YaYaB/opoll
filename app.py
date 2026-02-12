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
import re
import logging

from dotenv import load_dotenv

load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


def parse_poll_text(text: str) -> tuple[str, list[str], bool]:
    """Parse /opoll command text into question, list of options, and multiple_choice flag.
    Supports:
      - Double-quoted: "Question?" "Option1" "Option2" (space-separated, any number of spaces)
      - Bullet points • or - at start of line
      - Single line: Question? • A • B • C
    Leading "multiple" or "--multiple" (case-insensitive) enables multiple choice.
    """
    if not text or not text.strip():
        return "Poll question?", ["Option 1", "Option 2"], False

    raw = text.strip()
    multiple = False
    if re.match(r"^(?:multiple|--multiple)\b", raw, re.IGNORECASE):
        multiple = True
        raw = re.sub(r"^(?:multiple|--multiple)\s*", "", raw, count=1, flags=re.IGNORECASE).strip()

    # Double-quoted format: "What's for lunch?" "Pizza" "Sushi" "Salad"
    quoted = re.findall(r'"([^"]*)"', raw)
    if len(quoted) >= 2:
        question = quoted[0].strip() or "Poll question?"
        options = [s.strip() for s in quoted[1:] if s.strip()]
        if options:
            return question, options, multiple
        return question, ["Yes", "No"], multiple
    if len(quoted) == 1:
        return quoted[0].strip() or "Poll question?", ["Yes", "No"], multiple

    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    bullet_pattern = re.compile(r"^[\•\-]\s*")

    # Single line with " • " separators: "Question? • Option1 • Option2"
    if len(lines) == 1 and " • " in lines[0]:
        parts = [p.strip() for p in lines[0].split(" • ") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1:], multiple
        if len(parts) == 1:
            return parts[0], ["Yes", "No"], multiple

    question_parts = []
    options = []

    for line in lines:
        if bullet_pattern.match(line):
            option = bullet_pattern.sub("", line).strip()
            if option:
                options.append(option)
        else:
            if not options:
                question_parts.append(line)
            else:
                pass

    question = " ".join(question_parts).strip() if question_parts else "Poll question?"
    if not options:
        options = ["Yes", "No"]

    return question, options, multiple


def build_poll_blocks(
    question: str,
    options: list[str],
    votes: dict[int, list[str]] | None = None,
    multiple_choice: bool = False,
) -> list[dict]:
    """Build Block Kit blocks for the poll message.
    votes: optional dict option_index -> list of user_ids (for display as <@UID>)
    multiple_choice: if True, users can vote for several options; we store mode in a context block.
    """
    votes = votes or {}
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": question[:150], "emoji": True},
        },
    ]
    for i, option in enumerate(options):
        voter_ids = votes.get(i, [])
        if voter_ids:
            voters_mrkdwn = " ".join(f"<@{uid}>" for uid in voter_ids)
            line = f"• {option} — {voters_mrkdwn}"
        else:
            line = f"• {option}"
        blocks.append(
            {
                "type": "section",
                "block_id": f"option_{i}",
                "text": {"type": "mrkdwn", "text": line},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Vote", "emoji": True},
                    "action_id": "vote",
                    "value": str(i),
                },
            }
        )
    mode_block_id = "meta_multiple" if multiple_choice else "meta_single"
    mode_label = "Multiple choice" if multiple_choice else "Single choice"
    blocks.append(
        {
            "type": "context",
            "block_id": mode_block_id,
            "elements": [{"type": "mrkdwn", "text": mode_label}],
        }
    )
    return blocks


def parse_votes_from_blocks(blocks: list[dict]) -> tuple[str, list[str], dict[int, list[str]], bool]:
    """Extract question, option labels, current votes, and multiple_choice from message blocks."""
    question = "Poll"
    options = []
    votes = {}
    multiple_choice = False

    for block in blocks:
        if block.get("type") == "header":
            question = block.get("text", {}).get("text", "Poll")
        elif block.get("type") == "section" and block.get("block_id", "").startswith("option_"):
            idx_str = block.get("block_id", "").replace("option_", "")
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            text = block.get("text", {}).get("text", "")
            if " — " in text:
                option_part, voters_part = text.split(" — ", 1)
                option_name = option_part.strip().lstrip("•").strip()
                user_ids = re.findall(r"<@(U[A-Z0-9]+)>", voters_part)
                votes[idx] = user_ids
            else:
                option_name = text.strip().lstrip("•").strip()
                votes[idx] = []
            options.append((idx, option_name))
        elif block.get("type") == "context" and block.get("block_id") == "meta_multiple":
            multiple_choice = True

    options_sorted = [opt[1] for opt in sorted(options, key=lambda x: x[0])]
    return question, options_sorted, votes, multiple_choice


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
