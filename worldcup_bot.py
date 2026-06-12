"""
2026 FIFA World Cup — Final Score Bot for Webex
================================================
Checks football-data.org for finished World Cup matches and posts the
final score of each game (once, and only once) to a Webex space.

Designed to be run on a schedule (e.g., every 15 minutes via GitHub Actions).

Required environment variables:
  WEBEX_BOT_TOKEN      - Bot access token from developer.webex.com
  WEBEX_ROOM_ID        - The Webex space (room) ID to post into
  FOOTBALL_DATA_TOKEN  - Free API key from football-data.org

State:
  posted_matches.json  - IDs of matches already announced (kept in the repo
                         so re-runs never double-post)
"""

import json
import os
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WEBEX_BOT_TOKEN = os.environ["WEBEX_BOT_TOKEN"]
WEBEX_ROOM_ID = os.environ["WEBEX_ROOM_ID"]
FOOTBALL_DATA_TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]

# "WC" is the FIFA World Cup competition code on football-data.org
MATCHES_URL = "https://api.football-data.org/v4/competitions/WC/matches"
WEBEX_MESSAGES_URL = "https://webexapis.com/v1/messages"

STATE_FILE = Path(__file__).parent / "posted_matches.json"

# Map stage codes to friendly names
STAGE_NAMES = {
    "GROUP_STAGE": "Group Stage",
    "LAST_32": "Round of 32",
    "LAST_16": "Round of 16",
    "QUARTER_FINALS": "Quarter-final",
    "SEMI_FINALS": "Semi-final",
    "THIRD_PLACE": "Third-place play-off",
    "FINAL": "Final",
}


def load_posted_ids() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_posted_ids(ids: set) -> None:
    STATE_FILE.write_text(json.dumps(sorted(ids)))


def fetch_finished_matches() -> list:
    """Return all finished World Cup matches."""
    resp = requests.get(
        MATCHES_URL,
        headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN},
        params={"status": "FINISHED"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("matches", [])


def format_score_message(match: dict) -> str:
    """Build a Markdown message for a finished match."""
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]
    score = match["score"]
    ft = score["fullTime"]
    home_goals, away_goals = ft["home"], ft["away"]

    stage = STAGE_NAMES.get(match.get("stage", ""), match.get("stage", ""))
    group = match.get("group")  # e.g. "GROUP_A" during group stage
    context = group.replace("GROUP_", "Group ") if group else stage

    line = f"**FT: {home} {home_goals} – {away_goals} {away}**"

    # Add extra-time / penalty details for knockout games
    duration = score.get("duration", "REGULAR")
    extras = []
    if duration == "EXTRA_TIME":
        extras.append("after extra time")
    elif duration == "PENALTY_SHOOTOUT":
        pens = score.get("penalties") or {}
        if pens.get("home") is not None:
            extras.append(f"({pens['home']}–{pens['away']} on penalties)")
        else:
            extras.append("(decided on penalties)")

    winner = score.get("winner")
    if winner == "DRAW" and duration == "REGULAR":
        extras.append("— ends in a draw")

    suffix = " " + " ".join(extras) if extras else ""
    return f"⚽ {line}{suffix}  \n_{context} · 2026 FIFA World Cup_"


def post_to_webex(markdown: str) -> None:
    resp = requests.post(
        WEBEX_MESSAGES_URL,
        headers={
            "Authorization": f"Bearer {WEBEX_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"roomId": WEBEX_ROOM_ID, "markdown": markdown},
        timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    posted = load_posted_ids()
    matches = fetch_finished_matches()

    new_matches = [m for m in matches if m["id"] not in posted]
    if not new_matches:
        print("No new finished matches.")
        return 0

    # Post in kickoff order so scores appear chronologically
    new_matches.sort(key=lambda m: m["utcDate"])

    for match in new_matches:
        message = format_score_message(match)
        print(f"Posting result for match {match['id']}: "
              f"{match['homeTeam']['name']} vs {match['awayTeam']['name']}")
        post_to_webex(message)
        posted.add(match["id"])
        # Save after each post so a mid-run failure never causes duplicates
        save_posted_ids(posted)

    print(f"Posted {len(new_matches)} result(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
