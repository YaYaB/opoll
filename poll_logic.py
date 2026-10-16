"""Pure poll-building logic used by app.py (the /opoll handler, including
scheduled polls). No Slack-app/Flask dependencies here, so it can be imported
without a bot token, signing secret, or network access.
"""
import re


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
            "type": "section",
            "block_id": "question",
            "text": {"type": "mrkdwn", "text": f"*{question}*"},
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
        if block.get("type") == "section" and block.get("block_id") == "question":
            question = block.get("text", {}).get("text", "Poll")
            if question.startswith("*") and question.endswith("*"):
                question = question[1:-1]
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
