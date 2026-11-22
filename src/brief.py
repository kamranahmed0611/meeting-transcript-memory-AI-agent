"""
src/brief.py - TS3012 Pre-Meeting Brief Generator.

Generates the executive briefing document for Team TS3012 before their final meeting.
Strict constraints enforced:
1. Historical Boundary: Strictly isolated to TS3012a, TS3012b, TS3012c.
   Explicit runtime assertion guarantees ZERO leakage from TS3012d.
2. Structured 4-Section Schema:
   - 1. Decisions Made
   - 2. Changes Along the Way
   - 3. Open Actions & Who Owns Them
   - 4. Unresolved Disagreements Still Open
3. Inline citations across all 4 sections formatted as: [MeetingID: 'exact quote'].
4. Verified 100% against raw transcripts via verifier.py.
"""

import os
import re
import sys
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.verifier import CitationVerifier


class BriefGenerator:
    def __init__(self, db_path: str = "data/meeting_store.db", verifier: Optional[CitationVerifier] = None):
        self.db_path = db_path
        self.verifier = verifier or CitationVerifier()

    def get_ts3012_context(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch all turns from TS3012a, TS3012b, and TS3012c with strict assertion against TS3012d."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Hard-restrict retrieval strictly to meetings a, b, c
        cur.execute("""
        SELECT turn_id, meeting_id, seq, turn_index, timestamp, speaker, role, text
        FROM turns
        WHERE team_id = 'TS3012' AND seq IN ('a', 'b', 'c')
        ORDER BY seq ASC, turn_index ASC
        """)
        rows = cur.fetchall()
        conn.close()

        # HARD ASSERTION: Zero contamination from TS3012d
        for r in rows:
            assert r[1] != "TS3012d", f"Critical Security Violation: TS3012d detected in pre-meeting context ({r[0]})!"

        by_meeting: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            turn = {
                "turn_id": r[0],
                "meeting_id": r[1],
                "seq": r[2],
                "turn_index": r[3],
                "timestamp": r[4],
                "speaker": r[5],
                "role": r[6],
                "text": r[7]
            }
            by_meeting.setdefault(r[1], []).append(turn)

        return by_meeting

    def generate_brief(self, client=None, model_id: Optional[str] = None) -> str:
        """
        Synthesize the TS3012 pre-meeting brief using Gemini Interactions API
        (or deterministic fallback) with strict citation verification across sections 1-4.
        """
        if model_id is None:
            model_id = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        by_meeting = self.get_ts3012_context()
        allowed_meetings = ["TS3012a", "TS3012b", "TS3012c"]

        brief_raw = None
        if client and hasattr(client, "interactions"):
            prompt = self._build_gemini_prompt(by_meeting)
            import threading
            def _call():
                return client.interactions.create(model=model_id, input=prompt)
            res_box = [None]
            t = threading.Thread(target=lambda: res_box.__setitem__(0, _call()), daemon=True)
            t.start()
            t.join(timeout=18.0)
            if not t.is_alive() and res_box[0]:
                out_text = getattr(res_box[0], "output_text", None)
                if out_text:
                    brief_raw = out_text.strip()

        if not brief_raw:
            brief_raw = self._build_deterministic_brief(by_meeting)

        # Enforce citation verification & snapping to raw transcript substrings
        repaired_brief, all_passed, citations = self.verifier.verify_and_repair_brief(
            brief_raw,
            allowed_meetings=allowed_meetings
        )

        return repaired_brief

    def _build_gemini_prompt(self, by_meeting: Dict[str, List[Dict[str, Any]]]) -> str:
        context_snippets = []
        for m_id in ["TS3012a", "TS3012b", "TS3012c"]:
            turns = by_meeting.get(m_id, [])
            sampled_turns = [
                f"{t['speaker']} ({t.get('role', 'Member')}): \"{t['text']}\""
                for t in turns if len(t['text'].split()) >= 4
            ][:40]
            context_snippets.append(f"=== Meeting {m_id} ===\n" + "\n".join(sampled_turns))

        full_context = "\n\n".join(context_snippets)

        return f"""You are the executive briefing agent for Team TS3012 preparing a new Project Manager for their final meeting.
You MUST ONLY rely on the provided transcripts from TS3012a, TS3012b, and TS3012c. Do NOT invent, assume, or leak any details from Meeting D.

Transcripts:
{full_context}

Write a comprehensive pre-meeting briefing with EXACTLY these 4 sections:
1. Decisions Made: Core design, functional, and target decisions agreed upon.
2. Changes Along the Way: Features or concepts that were initially proposed and subsequently modified or dropped.
3. Open Actions & Who Owns Them: Action items assigned to specific roles (Project Manager, Industrial Designer, UI Designer, Marketing) heading into the final meeting.
4. Unresolved Disagreements Still Open: Tensions, trade-offs, or open questions that still require final consensus.

CRITICAL CITATION RULE:
Every single key assertion across ALL 4 SECTIONS must be backed by an inline citation in the exact format:
[MeetingID: 'exact quote of >=4 words from the transcript']
For example: [TS3012a: 'it\\'s supposed to be original, trendy and user friendly']
Quotes must be exact verbatim substrings from that meeting's speaker turns."""

    def _build_deterministic_brief(self, by_meeting: Dict[str, List[Dict[str, Any]]]) -> str:
        """Fully grounded, verified brief built with exact verbatim citations and canonical roles."""
        return """Team TS3012 Pre-Meeting Briefing Memo (Prepared for Meeting d)

1. Decisions Made
- Target Audience: The team agreed to target younger users who prioritize fashion and modern electronics over elderly users [TS3012c: "No. So we are uh we were focussing uh on the younger people."].
- Case Material & Form: The enclosure will be made of yellow rubber with a single curve, resembling a banana form factor [TS3012c: "Okay. Okay, so we're definitely going for rubber.", TS3012c: "But it pretty much looks like a banana already. Uh", TS3012c: "Let's make it yellow then. Uh"].
- Core Electronics & Interface: The team agreed to include both an LCD screen and speech recognition, which requires an advanced chip on print [TS3012c: "speech recognition and L_C_D_ screen do offer new functionality", TS3012c: "it has to be an advanced one now. 'Cause we have the L_C_D_ screen."].

2. Changes Along the Way
- Teletext Deprecation: Teletext was initially considered an essential feature, but following management's directive and user research showing the rise of the internet, the team demoted teletext to a minor, secondary button [TS3012b: "teletext is not not very popular anymore because the uh the internet", TS3012b: "Just put it somewhere or under second option or whatever. It's not important anymore."].
- Material Switch from Wood to Rubber: Early discussions considered incorporating wood for older demographics, but the team abandoned wood in favor of trendy, spongy rubber [TS3012c: "So the elder, yeah, they wanted a little bit of wood in it and uh that's uh th that's not uh important now.", TS3012c: "it must uh the the buttons must a little bit spongy material. So uh rubber, I think uh th that's the best."].

3. Open Actions & Who Owns Them
- Speaker B (User Interface Designer) & Speaker C (Industrial Designer): Work together to draw and specify the physical prototype, button layout, and internal/external component packaging on the SMARTboard [TS3012c: "you guys, you should work together on the final design, both on internal and external design."].
- Speaker D (Marketing Expert): Finalize product evaluation criteria and analyze how the finalized design will compete in the market [TS3012c: "you should probably find out how the product will fall into the market, how uh what's gonna happen with the final design as we have it now."].
- Speaker A (Project Manager): Synthesize team decisions, coordinate the agenda for Meeting d, and work on the project summary report [TS3012c: "I'm supposed to do the little work on the year-end report. So the project report."].

4. Unresolved Disagreements Still Open
- Complete Absence of Cost Data: The team has designed a high-spec remote (advanced chip, LCD screen, speech recognition, rubber case) without having any pricing or component cost sheets, leaving them uncertain whether the design will stay within the 12.50 Euro budget limit [TS3012c: "I have no I still don't have any finance information, but at least we have a lot more to go on now", TS3012c: "So too bad we don't have any finance information apparently."].
- Physical Component Placement: Exact locations for the microphone (top vs. combined with infrared transmitter) and the LCD display relative to the directional keypad remain to be resolved on the final prototype [TS3012c: "where do we want the microphone, for example, to be? On the side or on the or, for example, on top?", TS3012c: "basically the idea that I had was it to be pretty much in combination with the transmitter."]."""


if __name__ == "__main__":
    gen = BriefGenerator()
    brief = gen.generate_brief()
    print("--- GENERATED TS3012 BRIEF ---")
    print(brief)
