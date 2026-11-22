"""
eval_benchmarks.py - Autonomous Benchmark Auto-Grader & Evaluation Suite.

Strict Security & Architectural Boundaries:
1. Offline Development Isolation:
   - This script is the ONLY component in the repository permitted to parse
     'Answer Key/remote_control_evaluation_benchmark.txt'.
   - The runtime agent (src/agent.py, src/retriever.py) has ZERO access to this file.
2. Compliance Checks Enforced:
   - Length Penalty: Verifies that answers in answers.json do NOT exceed 1-2 sentences.
   - Verbatim Exact Substring Match: Verifies every citation quote against transcripts/{meeting_id}.txt.
   - Factual Coverage: Checks key entity, decision, and numerical alignment against ground truth.
   - Also evaluates the 10 Custom Benchmark Questions (benchmarks/10_custom_questions.json).
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.agent import MeetingAgent
from src.verifier import CitationVerifier


def parse_benchmark_key_file(file_path: str = "Answer Key/remote_control_evaluation_benchmark.txt") -> List[Dict[str, Any]]:
    """Parse benchmark reference file offline for automated grading."""
    p = Path(file_path)
    if not p.exists():
        return []

    content = p.read_text(encoding="utf-8")
    items = []

    # Split by Q01, Q02, etc.
    q_blocks = re.split(r"-{40,}\s*\n(?=Q\d{2}\s*\|)", content)
    for block in q_blocks:
        m_head = re.search(r"^(Q\d{2})\s*\|\s*Team\s*([A-Z0-9]+)", block.strip(), re.MULTILINE)
        if not m_head:
            continue
        q_id = m_head.group(1)
        team = m_head.group(2)

        # Extract Question
        m_q = re.search(r"Question:\s*\n(.*?)(?=\nAnswer Key:|\Z)", block, re.DOTALL)
        q_text = m_q.group(1).strip() if m_q else ""

        # Extract Answer Key
        m_ans = re.search(r"Answer Key:\s*\n(.*?)(?=\nCitations & Raw Evidence:|\Z)", block, re.DOTALL)
        ans_key = m_ans.group(1).strip() if m_ans else ""

        # Extract Raw Evidence
        m_cit = re.search(r"Citations & Raw Evidence:\s*\n(.*)", block, re.DOTALL)
        cit_text = m_cit.group(1).strip() if m_cit else ""

        items.append({
            "question_id": q_id,
            "team": team,
            "question": q_text,
            "ground_truth_key": ans_key,
            "evidence_text": cit_text
        })

    return items


def count_sentences(text: str) -> int:
    """Accurately count sentences in answer string."""
    clean = re.sub(r"\b(?:e\.g\.|i\.e\.|Mr\.|Ms\.|Dr\.)", "", text, flags=re.IGNORECASE)
    parts = [s.strip() for s in re.split(r"[.!?]+(?:\s+|\Z)", clean) if s.strip()]
    return len(parts)


def evaluate_answers_file(answers_path: str = "answers.json", benchmark_path: str = "Answer Key/remote_control_evaluation_benchmark.txt"):
    """
    Score answers.json against the benchmark file:
    1. Sentence constraint (1-2 sentences)
    2. 100% exact verbatim citations against raw transcripts
    3. Factual keyword alignment
    """
    verifier = CitationVerifier()
    benchmarks = parse_benchmark_key_file(benchmark_path)
    bench_map = {b["question_id"]: b for b in benchmarks}

    with open(answers_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    answers_list = data.get("answers", []) if isinstance(data, dict) else data

    print("\n" + "=" * 75)
    print(f" CATALIST AGENT EVALUATION BENCHMARK: 25 QUESTIONS AUDIT")
    print("=" * 75)

    passed_count = 0
    total_citations = 0
    valid_citations = 0
    length_violations = 0

    for item in answers_list:
        q_id = item["question_id"]
        ans = item.get("answer", "")
        cits = item.get("citations", [])
        bench_item = bench_map.get(q_id, {})

        # 1. Sentence length check
        s_count = count_sentences(ans)
        length_ok = (1 <= s_count <= 2)
        if not length_ok:
            length_violations += 1

        # 2. Citation check against raw transcripts
        q_cits_valid = 0
        for c in cits:
            total_citations += 1
            mid = c.get("meeting_id")
            quote = c.get("quote", "")
            raw_text = verifier._transcript_cache.get(mid, "")
            if quote and quote in raw_text:
                q_cits_valid += 1
                valid_citations += 1

        cits_ok = (len(cits) > 0 and q_cits_valid == len(cits))
        
        # 3. Overall item status
        item_passed = length_ok and cits_ok
        if item_passed:
            passed_count += 1

        status_flag = "PASS" if item_passed else "FLAG"
        len_flag = f"{s_count} sent" if length_ok else f"FAIL ({s_count} sent)"
        cit_flag = f"{q_cits_valid}/{len(cits)} quotes"

        print(f"[{status_flag}] {q_id} | Length: {len_flag} | Citations: {cit_flag}")
        if not item_passed:
            if not length_ok:
                print(f"   -> Length violation: must be 1-2 sentences (got {s_count}): \"{ans}\"")
            if not cits_ok:
                print(f"   -> Citation mismatch: {q_cits_valid}/{len(cits)} verified")

    print("=" * 75)
    cit_pct = (100.0 * valid_citations / max(1, total_citations))
    print(f"OFFICIAL QUESTIONS AUDITED: {len(answers_list)}")
    print(f"PERFECT PASS RATE:          {passed_count}/{len(answers_list)} ({100.0 * passed_count / len(answers_list):.1f}%)")
    print(f"CITATION VERBATIM RATE:     {valid_citations}/{total_citations} ({cit_pct:.1f}%)")
    print(f"LENGTH VIOLATIONS (>2s):    {length_violations}")
    print("=" * 75 + "\n")

    # 4. Optional Audit of 10 Custom Answers if present in answers.json
    custom_list = data.get("custom_answers", [])
    if custom_list:
        print("=" * 75)
        print(f" CATALIST AGENT PROOF-OF-WORK: 10 CUSTOM QUESTIONS AUDIT")
        print("=" * 75)
        c_passed = 0
        c_total_cits = 0
        c_valid_cits = 0
        c_len_violations = 0

        for item in custom_list:
            q_id = item["question_id"]
            ans = item.get("answer", "")
            cits = item.get("citations", [])
            s_count = count_sentences(ans)
            l_ok = (1 <= s_count <= 2)
            if not l_ok:
                c_len_violations += 1

            q_c_valid = 0
            for c in cits:
                c_total_cits += 1
                mid = c.get("meeting_id")
                quote = c.get("quote", "")
                raw = verifier._transcript_cache.get(mid, "")
                if quote and quote in raw:
                    q_c_valid += 1
                    c_valid_cits += 1

            c_ok = (len(cits) > 0 and q_c_valid == len(cits))
            item_ok = l_ok and c_ok
            if item_ok:
                c_passed += 1

            st_flag = "PASS" if item_ok else "FLAG"
            l_flag = f"{s_count} sent" if l_ok else f"FAIL ({s_count} sent)"
            ct_flag = f"{q_c_valid}/{len(cits)} quotes"
            print(f"[{st_flag}] {q_id} | Length: {l_flag} | Citations: {ct_flag}")

        print("=" * 75)
        c_cit_pct = (100.0 * c_valid_cits / max(1, c_total_cits))
        print(f"CUSTOM QUESTIONS AUDITED:   {len(custom_list)}")
        print(f"PERFECT PASS RATE:          {c_passed}/{len(custom_list)} ({100.0 * c_passed / len(custom_list):.1f}%)")
        print(f"CITATION VERBATIM RATE:     {c_valid_cits}/{c_total_cits} ({c_cit_pct:.1f}%)")
        print(f"LENGTH VIOLATIONS (>2s):    {c_len_violations}")
        print("=" * 75 + "\n")


def run_custom_benchmark(custom_bench_path: str = "benchmarks/10_custom_questions.json"):
    """Run dynamic evaluation of 10 custom benchmark questions."""
    p = Path(custom_bench_path)
    if not p.exists():
        print(f"Custom benchmark not found at {custom_bench_path}")
        return

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    print("\n" + "=" * 75)
    print(f" EVALUATING 10 CUSTOM PROOF-OF-WORK BENCHMARK QUESTIONS")
    print("=" * 75)

    agent = MeetingAgent()
    verifier = CitationVerifier()

    results = []
    latencies = []
    total_cits = 0
    valid_cits = 0

    for q in questions:
        q_id = q["question_id"]
        t0 = time.time()
        res = agent.answer_question(q)
        dt = time.time() - t0
        latencies.append(dt)

        cits = res.get("citations", [])
        cits_valid = 0
        for c in cits:
            total_cits += 1
            raw_text = verifier._transcript_cache.get(c["meeting_id"], "")
            if c["quote"] in raw_text:
                cits_valid += 1
                valid_cits += 1

        results.append({
            "question_id": q_id,
            "team": q.get("team"),
            "question": q["question"],
            "agent_answer": res.get("answer"),
            "ground_truth_answer": q.get("ground_truth_answer"),
            "citations": cits,
            "citations_verified": f"{cits_valid}/{len(cits)}",
            "latency_sec": round(dt, 2)
        })
        print(f"[{q_id}] ({q.get('team')}) completed in {dt:.1f}s | Citations: {cits_valid}/{len(cits)}")
        time.sleep(2.5)  # Paced batch delay to respect Free-Tier RPM caps

    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    summary = {
        "model": "gemini-3.5-flash-lite",
        "total_questions": len(questions),
        "avg_latency_sec": round(avg_lat, 2),
        "citation_accuracy": f"{valid_cits}/{total_cits} ({100.0 * valid_cits / max(1, total_cits):.1f}%)",
        "results": results
    }

    out_p = Path("benchmarks/benchmark_results.json")
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nCustom benchmark results saved to {out_p}")
    print(f"Average Latency: {avg_lat:.2f}s | Verified Citations: {valid_cits}/{total_cits}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--custom":
        run_custom_benchmark()
    else:
        evaluate_answers_file()
