"""
test_interactive.py - Interactive Question & Verification Harness for Catalist Meeting Agent.

Features:
- Type ANY free-form question interactively (not hardcoded).
- Runs live retrieval across 138 AMI meeting transcripts.
- Synthesizes an answer with live Gemini (or verified fallback).
- Verifies citations word-for-word and displays the exact transcript file, line number,
  and surrounding dialogue lines so you can verify it directly with your own eyes.
"""

import os
import sys
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

from dotenv import load_dotenv
load_dotenv(override=True)

from src.agent import MeetingAgent
from src.retriever import HybridRetriever
from src.verifier import CitationVerifier, normalize_text


def find_transcript_location(meeting_id: str, quote: str, transcripts_dir: str = "transcripts"):
    """Locate the exact line number and surrounding context in raw .txt transcript."""
    file_path = Path(transcripts_dir) / f"{meeting_id}.txt"
    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        content = file_path.read_text(encoding="latin-1", errors="ignore")

    lines = content.splitlines()
    norm_quote = normalize_text(quote)
    words = norm_quote.split()
    if not words:
        return None

    # Pass 1: Exact match within a single line
    for idx, line in enumerate(lines):
        norm_line = normalize_text(line)
        if norm_quote in norm_line:
            start_l = max(0, idx - 2)
            end_l = min(len(lines), idx + 3)
            snippet_lines = [f"{' >>> ' if i == idx else '     '}Line {i+1:4d}: {lines[i]}" for i in range(start_l, end_l)]
            return {
                "file_path": str(file_path),
                "line_number": idx + 1,
                "snippet": "\n".join(snippet_lines)
            }

    # Pass 2: Prefix match or multi-line turn spanning across lines
    prefix_len = min(len(words), 5)
    prefix_phrase = " ".join(words[:prefix_len])
    for idx, line in enumerate(lines):
        norm_line = normalize_text(line)
        if not norm_line:
            continue
        if prefix_phrase in norm_line or (len(words) >= 4 and " ".join(words[:4]) in norm_line):
            start_l = max(0, idx - 2)
            end_l = min(len(lines), idx + 4)
            snippet_lines = [f"{' >>> ' if i == idx else '     '}Line {i+1:4d}: {lines[i]}" for i in range(start_l, end_l)]
            return {
                "file_path": str(file_path),
                "line_number": idx + 1,
                "snippet": "\n".join(snippet_lines)
            }

    # Pass 3: Window substring search for split lines
    for idx, line in enumerate(lines):
        window_lines = lines[idx:min(len(lines), idx + 6)]
        window_text = normalize_text(" ".join(window_lines))
        if norm_quote in window_text:
            start_l = max(0, idx - 2)
            end_l = min(len(lines), idx + 4)
            snippet_lines = [f"{' >>> ' if i == idx else '     '}Line {i+1:4d}: {lines[i]}" for i in range(start_l, end_l)]
            return {
                "file_path": str(file_path),
                "line_number": idx + 1,
                "snippet": "\n".join(snippet_lines)
            }

    return {"file_path": str(file_path), "line_number": 1, "snippet": "     (See file for full dialogue turn)"}


def main():
    print("\n" + "=" * 70)
    print("CATALIST MEETING AGENT: INTERACTIVE QUERY & TRANSCRIPT VERIFIER")
    print("=" * 70)
    print("Ask any question in plain English (e.g., 'What material did Team ES2003 pick?').")
    print("Type 'exit' or 'quit' to stop.\n")

    agent = MeetingAgent()
    retriever = agent.retriever
    verifier = agent.verifier

    while True:
        try:
            query = input("\nEnter your question: ").strip()
            if not query:
                continue
            if query.lower() in {"exit", "quit", "q"}:
                print("Exiting interactive test harness.")
                break

            print("\n" + "-" * 70)
            print(f"QUERY: \"{query}\"")
            print("-" * 70)

            # Step 1: Execute agent reasoning loop
            extracted_team = retriever.extract_team_id(query)
            print(f"[1. Retrieval Scope] Team: {extracted_team or 'GLOBAL (Searching all teams)'}")
            
            item = {"question_id": "CUSTOM", "team": extracted_team, "question": query}
            result = agent.answer_question(item)

            # Step 2: Display answer
            print("\n[2. Synthesized Answer]")
            print(f"  {result['answer']}")

            # Step 3: Display and verify citations in raw transcript
            print("\n[3. Citation Verification & Raw Transcript Evidence]")
            citations = result.get("citations", [])
            if not citations:
                print("  No citations returned.")
            else:
                for idx, cit in enumerate(citations, 1):
                    m_id = cit["meeting_id"]
                    quote = cit["quote"]

                    # Verbatim check
                    is_valid, exact_quote, turn = verifier.verify_quote(m_id, quote)
                    status = "VERIFIED VERBATIM" if is_valid else "FAILED MATCH"

                    # Locate exact line in raw transcript file
                    loc = find_transcript_location(m_id, quote)

                    print(f"\n  Evidence #{idx} [{m_id}] [{status}]")
                    print(f"  Quote: \"{quote}\"")
                    if turn:
                        spk = turn.get("speaker", "Unknown")
                        role = f" ({turn['role']})" if turn.get("role") else ""
                        ts = turn.get("timestamp", "")
                        print(f"  Speaker: {spk}{role} @ {ts}")
                    
                    if loc:
                        print(f"  Source File: {loc['file_path']} (Line ~{loc['line_number']})")
                        print("  Raw Transcript Context:")
                        print(loc["snippet"])

            print("=" * 70)

        except KeyboardInterrupt:
            print("\nSession interrupted.")
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
