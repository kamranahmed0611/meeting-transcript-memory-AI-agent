"""
src/ingest.py - Deterministic Transcript Parser and SQLite/FTS5 Store.

Extracts:
- Turn-level dialogue, timestamps, speakers, roles
- Team IDs, meeting sequences (a, b, c, d)
Stores everything in local SQLite with an FTS5 full-text search table.
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROLE_PATTERNS = {
    "project manager": ["project manager", "pm"],
    "industrial designer": ["industrial designer", "industrial design", "id"],
    "user interface designer": ["user interface", "ui designer", "interface designer", "ui"],
    "marketing": ["marketing", "market expert", "marketing expert"]
}


def parse_roles_from_kickoff(text: str) -> Dict[str, str]:
    """Inspect kickoff meeting (a) text to extract speaker roles."""
    roles = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for spk in ["Speaker A", "Speaker B", "Speaker C", "Speaker D"]:
            if spk in line:
                window = " ".join(lines[i:i + 6]).lower()
                for role_name, kws in ROLE_PATTERNS.items():
                    if any(kw in window for kw in kws):
                        if spk not in roles:
                            roles[spk] = role_name
    return roles


def parse_transcript_file(file_path: Path) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """Parse a single transcript .txt file into metadata and speaker turns."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        content = file_path.read_text(encoding="latin-1", errors="ignore")

    lines = content.splitlines()
    meta = {
        "meeting_id": file_path.stem,
        "team_id": file_path.stem[:-1],
        "seq": file_path.stem[-1].lower(),
        "speakers": ""
    }

    body_start_line = 0
    for idx, line in enumerate(lines[:15]):
        if line.startswith("Meeting:"):
            meta["meeting_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("Team:"):
            meta["team_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("Meeting number:"):
            match = re.search(r"\(([a-d])\)", line.lower())
            if match:
                meta["seq"] = match.group(1)
        elif line.startswith("Speakers:"):
            meta["speakers"] = line.split(":", 1)[1].strip()
        elif re.match(r"^\d{2}:\d{2}:\d{2}\s+Speaker\s+[A-D]", line):
            body_start_line = idx
            break

    turn_header_re = re.compile(r"^(\d{2}:\d{2}:\d{2})\s+(Speaker\s+[A-D])\s*$")
    turns = []
    current_turn = None
    accumulated_lines = []

    for line in lines[body_start_line:]:
        match = turn_header_re.match(line.strip())
        if match:
            if current_turn is not None:
                turn_text = " ".join(accumulated_lines).strip()
                current_turn["text"] = turn_text
                current_turn["word_count"] = len(turn_text.split())
                turns.append(current_turn)
                accumulated_lines = []

            timestamp = match.group(1)
            speaker = match.group(2)
            turn_index = len(turns) + 1
            turn_id = f"{meta['meeting_id']}_{turn_index:04d}"
            current_turn = {
                "turn_id": turn_id,
                "meeting_id": meta["meeting_id"],
                "team_id": meta["team_id"],
                "seq": meta["seq"],
                "turn_index": turn_index,
                "timestamp": timestamp,
                "speaker": speaker,
                "role": "",
                "text": "",
                "word_count": 0
            }
        else:
            if current_turn is not None and line.strip():
                accumulated_lines.append(line.strip())

    if current_turn is not None:
        turn_text = " ".join(accumulated_lines).strip()
        current_turn["text"] = turn_text
        current_turn["word_count"] = len(turn_text.split())
        turns.append(current_turn)

    return meta, turns


def init_database(db_path: Path):
    """Create SQLite tables and FTS5 index."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS meetings (
        meeting_id TEXT PRIMARY KEY,
        team_id TEXT NOT NULL,
        seq TEXT NOT NULL,
        num_turns INTEGER NOT NULL,
        file_path TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS turns (
        turn_id TEXT PRIMARY KEY,
        meeting_id TEXT NOT NULL,
        team_id TEXT NOT NULL,
        seq TEXT NOT NULL,
        turn_index INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        speaker TEXT NOT NULL,
        role TEXT,
        text TEXT NOT NULL,
        word_count INTEGER NOT NULL
    );
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_turns_team_seq ON turns(team_id, seq);
    """)

    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
        turn_id UNINDEXED,
        meeting_id UNINDEXED,
        team_id UNINDEXED,
        seq UNINDEXED,
        speaker UNINDEXED,
        text
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS turn_embeddings (
        turn_id TEXT PRIMARY KEY,
        meeting_id TEXT NOT NULL,
        team_id TEXT NOT NULL,
        seq TEXT NOT NULL,
        embedding BLOB NOT NULL
    );
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_embeddings_team ON turn_embeddings(team_id);
    """)

    conn.commit()
    conn.close()


def ingest_transcripts(transcripts_dir: str = "transcripts", db_path: str = "data/meeting_store.db"):
    """Ingest all transcript files into SQLite."""
    t_dir = Path(transcripts_dir)
    d_path = Path(db_path)
    init_database(d_path)

    conn = sqlite3.connect(d_path)
    cur = conn.cursor()

    files = sorted(list(t_dir.glob("*.txt")))
    print(f"[Ingest] Found {len(files)} transcript files in {transcripts_dir}")

    total_turns = 0
    team_roles: Dict[str, Dict[str, str]] = {}

    for file_path in files:
        meta, turns = parse_transcript_file(file_path)
        team_id = meta["team_id"]
        
        # Infer speaker roles if kickoff meeting
        if meta["seq"] == "a" and team_id not in team_roles:
            try:
                full_text = file_path.read_text(encoding="utf-8")
            except Exception:
                full_text = file_path.read_text(encoding="latin-1", errors="ignore")
            team_roles[team_id] = parse_roles_from_kickoff(full_text)

        assigned_roles = team_roles.get(team_id, {})

        # Upsert meeting
        cur.execute("""
        INSERT OR REPLACE INTO meetings (meeting_id, team_id, seq, num_turns, file_path)
        VALUES (?, ?, ?, ?, ?)
        """, (meta["meeting_id"], team_id, meta["seq"], len(turns), str(file_path)))

        # Insert turns
        for t in turns:
            spk_role = assigned_roles.get(t["speaker"], "")
            t["role"] = spk_role
            cur.execute("""
            INSERT OR REPLACE INTO turns (turn_id, meeting_id, team_id, seq, turn_index, timestamp, speaker, role, text, word_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (t["turn_id"], t["meeting_id"], t["team_id"], t["seq"], t["turn_index"], t["timestamp"], t["speaker"], t["role"], t["text"], t["word_count"]))

            # Insert into FTS5 (only turns with substantive words)
            if t["word_count"] >= 3:
                cur.execute("""
                INSERT INTO turns_fts (turn_id, meeting_id, team_id, seq, speaker, text)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (t["turn_id"], t["meeting_id"], t["team_id"], t["seq"], t["speaker"], t["text"]))

        total_turns += len(turns)

    conn.commit()
    conn.close()
    print(f"[Ingest] Successfully ingested {len(files)} meetings and {total_turns} turns into {db_path}")


if __name__ == "__main__":
    ingest_transcripts()
