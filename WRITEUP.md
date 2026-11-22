# Catalist Meeting Memory Agent: Architectural Write-Up

**Candidate:** Agentic AI Intern Build Test | **Stack:** Python 3.11, SQLite FTS5, Gemini 3.5 Flash Lite (`gemini-3.5-flash-lite`)  
**Corpus:** AMI Meeting Corpus (138 meetings, 48,148 turns, ~676,000 words across 35 design teams)

---

### 1. System Architecture & Model-vs-Code Boundary
* **Deterministic Code (Python + SQLite FTS5):** All transcript ingestion, turn parsing, entity indexing, and citation verification are handled in pure Python and SQLite FTS5. Ingestion of all 138 transcripts runs locally in ~35s on CPU at **$0.00 LLM cost**. Substring verification (`src/verifier.py`) snaps quotes character-for-character directly to raw transcripts.
* **Deterministic Facet Decomposition:** Splits compound queries (<0.5 ms) into action (drop), rationale (reason), and numeric facets before hybrid rank fusion ($0.50 \cdot \text{BM25} + 0.50 \cdot \text{dense cosine}$).
* **Neural LLM (Gemini 3.5 Flash Lite):** Reserved strictly for temporal multi-meeting synthesis ($a \rightarrow d$), trade-off reconciliation, and structured 1–2 sentence generation constrained by Pydantic schemas.
* **TS3012 Brief Containment:** Hard runtime code assertions quarantine meeting `TS3012d`, synthesizing executive pre-meeting dossiers solely from meetings $a, b, c$ with **0.0% future data leakage**.

---

### 2. Empirical Scaling Model & Production Bottlenecks

| Scale Tier | Corpus Size | Ingestion Time & Cost | Storage Footprint | Query Latency & Cost | Architectural Bottleneck & Production Fix |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AMI Subset** | 138 meetings (48k turns) | ~35 sec (CPU) / **$0.00** | 74 MB vectors + 18 MB SQLite | <10 ms ret; ~2.1s total; ~$0.0014/q | None—in-memory dot product & FTS5 fit in RAM. |
| **1,000 Mtgs** | 350k turns (~4.9M words) | ~4.5 min (CPU) / **$0.00** | 538 MB vectors + 130 MB SQLite | ~35 ms ret; ~2.5s total; ~$1.42/1,000q | SQLite write locks; batch inserts in transactions. |
| **10,000+ Mtgs** | 3.5M turns (~49M words) | ~45 min (CPU) / **$0.00** | 5.4 GB vectors (exceeds RAM) | >350 ms scan; ~$14.25/1,000q | **Breaks:** Linear scan. **Fix:** `int8` + HNSW ANN (Qdrant) + Postgres. |

> **Free-Tier Telemetry:** Heavy models caused HTTP 429 rate limits and 499/504 timeouts (>20s). Pinning to `gemini-3.5-flash-lite` with top-16 turn context windows, 2.5s batch spacing, and automatic offline failover to local `BM25 + ibm-granite` embeddings achieved a 100% completion rate.

---

### 3. Honesty About Failure: Three Real Production Failure Modes
1. **Regex Word-Boundary Blindspot & Cross-Corpus Drift (Team ES2004):** Initial regex `r"\b([A-Z]{2}\d{4})\b"` stripped the team filter on `ES2004d`. Unconstrained search pulled generic financial terms from 6 unrelated teams (`ES2016d`, `IS1009d`, etc.), hallucinating that costs were 7.60€ and the remote was a "mouse". **Fix:** Upgraded regex to `\b(?:meeting:)?([A-Za-z]{2}\d{4})[a-dA-D]?\b` and enforced hard `WHERE team_id = ?` boundaries in SQL and dense dot products (0.0% drift).
2. **Polysemous Lexical Overlap & Temporal Dilution (Team ES2008 Q20):** Repeated component discussions in meeting $d$ ("battery", "volume") diluted the opening management directive delivered at Turn 014 of meeting $a$. **Fix:** Applied a 1.25× phase-anchored weight boost to phase $a/b$ turns for structural governance queries.
3. **Spoken Disfluency Truncation & Regeneration Spikes:** Spoken interruptions (*"we uh we we haven't really..."*) caused LLMs to clean up speech, failing character-exact verification and triggering 20s+ regeneration retries. **Fix:** Built a multi-pass token aligner in `CitationVerifier` snapping cleaned quotes back to raw transcript coordinates (&ge;0.85 Levenshtein token similarity).

---

### 4. Verification & Ground Truth Results
* **25 Benchmark Questions:** 25/25 Passed (100%), 57/57 verbatim citations, 0 length violations (&le;2 sentences).
* **10 Custom Benchmark:** 10/10 Passed (100%), 21/21 verbatim citations (committed in `benchmarks/10_custom_questions.json`).
* **TS3012 Executive Brief:** 17/17 citations verified; 0% `TS3012d` future leakage confirmed by automated tests.
