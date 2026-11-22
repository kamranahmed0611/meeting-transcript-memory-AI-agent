"""
demo.py - Interactive Live Demo & Walkthrough CLI.

Demonstrates:
1. Real agent behavior: Step-by-step trace (Retrieve, Temporal Gap Detection, Neighbor Expansion, Synthesis)
2. Interactive mode: Test custom or unseen questions live on camera
3. Citation validation: Instant visual proof of verbatim transcript matching
"""

import sys
import argparse
import subprocess
from pathlib import Path

# Auto-delegate to local .venv if run with system Python without venv activated
def _maybe_reexec_in_venv():
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        return
    venv_py = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if venv_py.exists() and sys.executable.lower() != str(venv_py).lower():
        result = subprocess.run([str(venv_py)] + sys.argv, check=False)
        sys.exit(result.returncode)

_maybe_reexec_in_venv()

from src.agent import MeetingAgent
from src.retriever import HybridRetriever
from src.verifier import CitationVerifier


SAMPLE_QUESTIONS = [
    {
        "question_id": "DEMO-1",
        "team": "TS3006",
        "question": "Team TS3006 planned both an LCD screen and speech recognition. When costs forced a cut, which did they drop and which did they keep?"
    },
    {
        "question_id": "DEMO-2",
        "team": "ES2003",
        "question": "Team ES2003 leaned towards one material for the case and then switched to another. What was the first material and what did they switch to?"
    },
    {
        "question_id": "DEMO-3",
        "team": "TS3011",
        "question": "Team TS3011 chose a combined energy source for their remote. What was the combination, and what happened to it when costs were added up?"
    }
]


def run_live_demo(question_text: str, team_id: str = None):
    print("\n" + "=" * 65)
    print(f"CATALIST MEETING AGENT: LIVE EXECUTION TRACE")
    print("=" * 65)
    print(f"Query: \"{question_text}\"")

    retriever = HybridRetriever()
    verifier = CitationVerifier()
    agent = MeetingAgent()

    # Step 1: Query Analysis & Metadata Pre-Filtering
    extracted_team = team_id or retriever.extract_team_id(question_text)
    print(f"\n[Agent Step 1: Pre-Filtering & Hybrid Retrieval]")
    print(f"  -> Extracted Team ID: {extracted_team or 'GLOBAL (No Team Pre-Filter)'}")
    
    search_res = retriever.search(question_text, explicit_team=extracted_team, top_k=10)
    turns = search_res["turns"]
    by_meeting = search_res["by_meeting"]

    print(f"  -> Retrieved {len(turns)} candidate turns across meetings: {list(by_meeting.keys())}")
    for i, t in enumerate(turns[:3], 1):
        role_tag = f" [{t['role']}]" if t['role'] else ""
        print(f"     Hit #{i}: ({t['meeting_id']} | {t['speaker']}{role_tag} @ {t['timestamp']})")
        print(f"             \"{t['text'][:85]}...\"")

    # Step 2: Temporal Evolution Check & Neighbor Expansion
    print(f"\n[Agent Step 2: Temporal Sequence Inspection]")
    if len(by_meeting) < 2 and turns:
        print(f"  -> Notice: Only {len(by_meeting)} meeting in top hits. Temporal evolution incomplete.")
        print(f"  -> Triggering Context Expansion on top turn {turns[0]['turn_id']}...")
        neighbors = retriever.get_neighbor_turns(turns[0]['turn_id'], window=2)
        print(f"  -> Expanded {len(neighbors)} adjacent turns into reasoning context.")
    else:
        print(f"  -> Multi-meeting evidence confirmed across: {', '.join(by_meeting.keys())}.")

    # Step 3: Synthesis & Citation Guardrail
    print(f"\n[Agent Step 3: Reasoning & Citation Guardrail]")
    res = agent.answer_question({"question_id": "LIVE", "team": extracted_team, "question": question_text})

    print("\n" + "-" * 65)
    print("FINAL SYNTHESIS:")
    print(f"  {res['answer']}")
    print("\nVERIFIED CITATIONS (Word-for-Word Transcript Match):")
    for cit in res["citations"]:
        is_valid, exact_quote, turn = verifier.verify_quote(cit["meeting_id"], cit["quote"])
        status = "VERIFIED VERBATIM" if is_valid else "FAILED"
        print(f"  [{cit['meeting_id']}] [{status}]")
        print(f"    Quote: \"{cit['quote']}\"")
        if turn:
            spk = turn.get("speaker", "Unknown")
            ts = turn.get("timestamp", "")
            print(f"    Source: {spk} @ {ts}")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Live Demo Runner")
    parser.add_argument("--live", action="store_true", help="Run interactive prompt for live questions")
    parser.add_argument("--sample", type=int, default=1, help="Run sample question (1, 2, or 3)")
    args = parser.parse_args()

    if args.live:
        print("Catalist Meeting Agent - Interactive Live Mode")
        print("Type 'exit' to quit.\n")
        while True:
            try:
                user_q = input("Enter question (e.g. 'Team TS3006 dropped speech or LCD?'): ").strip()
                if not user_q or user_q.lower() in {"exit", "quit"}:
                    break
                run_live_demo(user_q)
            except KeyboardInterrupt:
                break
    else:
        idx = max(1, min(len(SAMPLE_QUESTIONS), args.sample)) - 1
        item = SAMPLE_QUESTIONS[idx]
        run_live_demo(item["question"], team_id=item["team"])


if __name__ == "__main__":
    main()
