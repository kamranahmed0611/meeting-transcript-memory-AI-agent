"""
run.py - Master Execution CLI for Catalist Meeting Intelligence Engine.

Usage:
    python run.py                   # Run full evaluation across 25 questions + TS3012 brief
    python run.py --fresh           # Overwrite checkpoints and regenerate answers
    python run.py --team TS3006     # Test a specific team
"""

import os
import sys
import json
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

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc=""):
        total = len(iterable) if hasattr(iterable, "__len__") else None
        for idx, item in enumerate(iterable, 1):
            if total:
                print(f"[{desc}] {idx}/{total}...", end="\r", flush=True)
            yield item
        print()

from src.ingest import ingest_transcripts
from src.embeddings import EmbeddingEngine
from src.agent import MeetingAgent
from src.brief import BriefGenerator
from src.verifier import CitationVerifier


def atomic_save_json(data: dict, filepath: Path):
    """Atomically write JSON to avoid corrupted files on interruption."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, filepath)


def main():
    parser = argparse.ArgumentParser(description="Catalist Meeting Agent Batch Runner")
    parser.add_argument("--questions", default="questions.json", help="Path to questions.json")
    parser.add_argument("--output", default="answers.json", help="Path to final output answers.json")
    parser.add_argument("--db", default="data/meeting_store.db", help="Path to SQLite database")
    parser.add_argument("--transcripts", default="transcripts", help="Path to transcripts directory")
    parser.add_argument("--fresh", action="store_true", help="Ignore checkpoints and re-run all questions")
    parser.add_argument("--team", default=None, help="Filter to a specific team ID (e.g. TS3006)")
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip dense embedding generation")
    args = parser.parse_args()

    db_path = Path(args.db)
    output_path = Path(args.output)
    checkpoint_path = Path("data/checkpoints.json")

    # Step 1: Ingest transcripts into SQLite if DB missing
    if not db_path.exists():
        print("[Run] Initializing database and ingesting transcripts...")
        ingest_transcripts(transcripts_dir=args.transcripts, db_path=str(db_path))

    # Step 2: Ensure embeddings are generated
    if not args.skip_embeddings:
        try:
            embed_engine = EmbeddingEngine(db_path=str(db_path))
            embed_engine.generate_and_store_embeddings()
        except Exception as e:
            print(f"[Run] Embedding notice: {e}. Falling back to lexical hybrid search.")

    # Step 3: Load questions
    with open(args.questions, "r", encoding="utf-8") as f:
        q_data = json.load(f)
    questions = q_data.get("questions", [])

    if args.team:
        questions = [q for q in questions if q.get("team") == args.team]
        print(f"[Run] Filtered to {len(questions)} questions for team {args.team}")

    # Load checkpoints
    checkpoint = {"answers": {}, "brief": None}
    if checkpoint_path.exists() and not args.fresh:
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            print(f"[Run] Resumed from checkpoint: {len(checkpoint['answers'])} answers already completed.")
        except Exception:
            pass

    # Step 4: Initialize Agent & Verifier
    agent = MeetingAgent(db_path=str(db_path))
    verifier = CitationVerifier(transcripts_dir=args.transcripts)

    # Step 5: Process questions
    print(f"\n[Run] Answering {len(questions)} benchmark questions...")
    for q in tqdm(questions, desc="Processing questions"):
        q_id = q["question_id"]
        if q_id in checkpoint["answers"] and not args.fresh:
            continue

        result = agent.answer_question(q)
        checkpoint["answers"][q_id] = result
        atomic_save_json(checkpoint, checkpoint_path)

    # Step 6: Generate TS3012 pre-meeting brief
    if not checkpoint.get("brief") or args.fresh:
        print("\n[Run] Generating Pre-Meeting Brief for Team TS3012 (Meetings a, b, c only)...")
        brief_gen = BriefGenerator(db_path=str(db_path), verifier=verifier)
        ts3012_brief = brief_gen.generate_brief(client=agent.client)
        checkpoint["brief"] = ts3012_brief
        atomic_save_json(checkpoint, checkpoint_path)
    else:
        print("[Run] Loaded TS3012 brief from checkpoint.")

    # Step 7: Assemble final answers.json (including 10 custom proof-of-work answers if available)
    custom_answers = []
    custom_res_path = Path("benchmarks/benchmark_results.json")
    if custom_res_path.exists():
        try:
            with open(custom_res_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            for res in cdata.get("results", []):
                custom_answers.append({
                    "question_id": res["question_id"],
                    "question": res.get("question", ""),
                    "answer": res.get("agent_answer", res.get("answer", "")),
                    "citations": res.get("citations", [])
                })
        except Exception:
            pass

    final_output = {
        "answers": [checkpoint["answers"][q["question_id"]] for q in questions if q["question_id"] in checkpoint["answers"]],
        "custom_answers": custom_answers,
        "brief": checkpoint["brief"]
    }
    atomic_save_json(final_output, output_path)
    print(f"\n[Run] Final answers saved to {output_path} (25 official answers + {len(custom_answers)} custom answers)")

    # Step 8: Run Final 100% Verification Audit
    print("\n" + "=" * 50)
    print("FINAL CITATION & VERIFICATION AUDIT")
    print("=" * 50)
    total_citations = 0
    valid_citations = 0

    for ans in final_output["answers"]:
        q_id = ans["question_id"]
        for cit in ans.get("citations", []):
            total_citations += 1
            is_valid, exact_quote, _ = verifier.verify_quote(cit["meeting_id"], cit["quote"])
            if is_valid:
                valid_citations += 1
            else:
                print(f"[Audit Warning] {q_id} citation failed: [{cit['meeting_id']}] '{cit['quote']}'")

    print(f"Answer Citations: {valid_citations}/{total_citations} verified verbatim ({100.0 * valid_citations / max(1, total_citations):.1f}%)")

    # Audit Brief Citations
    _, brief_valid, brief_citations = verifier.verify_and_repair_brief(
        final_output["brief"],
        allowed_meetings=["TS3012a", "TS3012b", "TS3012c"]
    )
    print(f"TS3012 Brief Citations: {len(brief_citations)} inline citations verified verbatim against raw transcripts.")
    print("=" * 50)


if __name__ == "__main__":
    main()
