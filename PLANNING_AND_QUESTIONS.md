# Catalist Meeting Agent: Comprehensive Planning, Decisions & Q&A Record

**Project:** Agentic AI Intern Build Test (Paid 3-Month Internship | Catalist Media)  
**System Name:** Catalist Meeting Intelligence Engine (`src/`)  
**Status:** Planning Phase Complete — Ready for Implementation  

---

## 1. Executive Summary & Architecture Blueprint

The goal is to build an agentic meeting intelligence system operating over 138 real AMI meeting transcripts (~676,000 words), capable of scaling seamlessly to 10,000+ meetings. The system must answer 25 multi-meeting questions with exact word-for-word citations ($\ge 6$ words) and draft an actionable pre-meeting brief for Team TS3012 before their final meeting.

### System Architecture
```
                                +-----------------------------+
                                | 138 AMI Transcripts (.txt)  |
                                +-----------------------------+
                                               |
                                               v
                             [Deterministic Parsing (Python)]
                                               |
                +------------------------------+-------------------------------+
                |                                                              |
                v                                                              v
   +--------------------------+                                   +---------------------------+
   | SQLite FTS5 Keyword Index|                                   | Local BAAI/bge-small-v1.5 |
   | (Lexical Search: prices, |                                   | Dense Embeddings (NumPy   |
   | materials, components)   |                                   | exact dot-product)        |
   +--------------------------+                                   +---------------------------+
                |                                                              |
                +------------------------------+-------------------------------+
                                               |
                                               v
                          [Team Metadata Pre-Filter (SQL)]
                          (e.g., Team = TS3006; <1ms latency)
                                               |
                                               v
                        [Bounded 2-Step Agent Reasoning Loop]
                          - Step 1: Hybrid candidate retrieval
                          - Step 2: Neighbor turn expansion /
                            unresolved reference resolution
                          - Google GenAI SDK (gemini-3.5-flash-lite / 3.1-flash-lite)
                                               |
                                               v
                        [Deterministic Citation Guardrail (Code)]
                          - Verbatim substring match check
                          - Contraction-safe regex validator
                          - >= 6 words enforced within speaker turn
                          - Auto-repair from source turn ID
                                               |
                                               v
                          +-----------------------------------+
                          | answers.json & TS3012 Brief       |
                          +-----------------------------------+
```

---

## 2. Directory Structure (`src/` Architecture)

```
CataList Media Agent/
├── src/
│   ├── __init__.py          # Zero-config imports from repo root
│   ├── ingest.py            # Turn-level deterministic parsing + SQLite/FTS5 schema
│   ├── embeddings.py        # BAAI/bge-small-en-v1.5 local embedding & vector storage
│   ├── retriever.py         # Team-filtered hybrid retrieval (FTS5 + dense vectors)
│   ├── agent.py             # 2-step bounded agent loop + Gemini 2.5 Flash reasoner
│   ├── verifier.py          # Deterministic citation validator & substring repair
│   └── brief.py             # TS3012 pre-meeting brief synthesizer (a, b, c only)
├── data/
│   ├── transcripts/         # 138 raw transcript files (AMI corpus)
│   ├── meeting_store.db     # SQLite database (FTS5 + turn metadata + embedding BLOBs)
│   └── checkpoints.json     # Atomic incremental checkpoint cache
├── questions.json           # 25 original evaluation questions
├── run.py                   # Master batch execution CLI (supports --fresh, --team)
├── demo.py                  # Live 3-5 min demo CLI with intermediate trace logging
├── WRITEUP.md               # 1-page report matching all Catalist assessment rubrics
├── README.md                # Setup guide, architecture overview, and 3-line Colab block
├── PLANNING_AND_QUESTIONS.md # This persistent record of all design decisions
├── .env.example             # Template for GEMINI_API_KEY
├── .gitignore               # Ignores .env, meeting_store.db, python cache
└── requirements.txt         # Pinned lightweight dependencies
```

---

## 3. Interactive Planning Loop: Full Q&A History

### Batch 1: Core Framework, Storage & Citation Guardrail

* **Q1: Which LLM provider and model do you want to use for the reasoning, synthesis, and briefing tasks?**  
  * **Decision:** **Gemini API (`gemini-3.5-flash-lite` with `gemini-3.1-flash-lite` failover via `google-genai`)**  
  * *Rationale:* High reasoning speed, low latency, structured JSON output support, and resilience against rate limits.

* **Q2: What core indexing and retrieval engine should we use for storing and querying the transcripts?**  
  * **Decision:** **Hybrid SQLite FTS5 (Lexical) + Local `sentence-transformers` (`BAAI/bge-small-en-v1.5`)**  
  * *Rationale:* Gives the best of both worlds: exact keyword matching on technical terms (e.g. "titanium", "LCD", "€12") + dense semantic matching on intent, without external vector database dependencies.

* **Q3: If the LLM provides an answer but the citation quote is slightly paraphrased or missing a word, how should the citation guardrail handle it?**  
  * **Decision:** **Deterministic Substring Alignment (Code-only)**  
  * *Rationale:* The Python verifier validates whether the quote exists verbatim in the referenced speaker turn ($\ge 6$ words). If slightly paraphrased, Python deterministically aligns and extracts the exact substring from the source turn. Zero hallucinated citations.

* **Q4: What primary delivery and execution format do you prefer for the final codebase and submission?**  
  * **Decision:** **Modular Python package (`src/`) with root CLI entrypoints + Jupyter Notebook companion**  
  * *Rationale:* Clean separation of concerns, easy to inspect in GitHub, immediate live demo capability, and ready for Google Colab.

* **Q5: For Team TS3012's pre-meeting brief, how should the transcript boundaries be enforced?**  
  * **Decision:** **Strict Historical Isolation (`TS3012a`, `TS3012b`, `TS3012c` only)**  
  * *Rationale:* The brief is explicitly for the team to read *before their final meeting*. Reading `TS3012d` would be future data leakage. `TS3012d` is quarantined and used solely to evaluate how well the brief anticipated final outcomes.

---

### Batch 2: Embedding Selection, Turn Granularity, Benchmark & Brief Structure

* **Q6: Which sentence-transformers embedding model do you want to use for the local semantic index?**  
  * **Decision:** **`BAAI/bge-small-en-v1.5` (~130MB)**  
  * *Rationale:* Superior retrieval benchmark scores on conversational text while remaining lightweight and fast on CPU.

* **Q7: How should turns be partitioned for retrieval and citations given spoken filler words?**  
  * **Decision:** **Index turns with $\ge 6$ words individually; retain micro-turns in conversational context**  
  * *Rationale:* Preserves exact single-speaker citation bounds while allowing the LLM to observe agreement/disagreement signals (*"Mm-hmm"*, *"Yeah"*) in the surrounding context.

* **Q8: For the 10 custom benchmark questions (proof of work), what strategy should we use to craft and verify them?**  
  * **Decision:** **Balanced 10 questions across 10 distinct teams covering: materials, price/budget cuts, component drops, and assigned commitments**  
  * *Constraint Enforced:* Every question requires at least two meetings ($a$ through $d$) to answer. Ground-truth quotes manually verified word-for-word against raw `.txt` files.

* **Q9: For the 'Honesty About Failure' requirement (3 questions your agent got wrong and why), how should we identify these failure cases?**  
  * **Decision:** **Real misses from the final submitted agent**  
  * *Constraint Enforced:* Failures must be genuine misses made by the final system on edge-case questions (e.g. pronoun ambiguity, speech disfluencies, implicit sarcasm), with clear root-cause attribution.

* **Q10: How should Team TS3012's pre-meeting brief be structured in the final output?**  
  * **Decision:** **Structured 4-Section Brief matching the prompt's checklist**  
  * *Sections:* 1. Decisions Made; 2. Changes Along the Way; 3. Open Actions & Owners; 4. Unresolved Disagreements.  
  * *Formatting:* Serialized as a single string in `answers.json["brief"]`, with all citations checked word-for-word.

---

### Batch 3: Environment, Scaling Model, Citation Syntax & Demo Assets

* **Q11: How will the Gemini API key be supplied to the agent pipeline?**  
  * **Decision:** **`.env` file with `python-dotenv`, falling back to `os.environ["GEMINI_API_KEY"]`**  
  * *Security:* `.env` in `.gitignore`, with `.env.example` provided for reviewers.

* **Q12: For the 1-page write-up requirement ('Tell us what ingesting 1,000 meetings would cost and how long it takes'), what methodology should we use?**  
  * **Decision:** **Empirical Extrapolation Table (138 Actual $\rightarrow$ 1,000 Projected $\rightarrow$ 10,000 Projected)**  
  * *Model-vs-Code Defense:* Ingestion API cost is **\$0.00** because parsing and `bge-small-en-v1.5` embeddings run entirely on local CPU. Query costs are isolated and measured separately.

* **Q13: How should citations be formatted inside the TS3012 brief string?**  
  * **Decision:** **Inline bracket citations: `[MeetingID: 'exact quote of >=6 words']`**  
  * *Regex Guard:* Contraction-safe regex (`r"\[([A-Za-z0-9]+):\s*['\"](.+?)['\"]\]"`) that never truncates on apostrophes (*"don't"*, *"it's"*).

* **Q14: To demonstrate 'real agent behaviour (retrieve, loop, process in steps)' without falling over at scale, how should the query-reasoning loop operate?**  
  * **Decision:** **Bounded 2-Step Agentic Loop with Metadata Pre-Filtering**  
  * *Step 1:* Filter by `team_id`, run hybrid retrieval across meetings $a-d$.  
  * *Step 2:* If decision sequence is unresolved or pronouns are ambiguous, expand to adjacent turns or refine search. Capped at 2–3 steps for bounded latency.

* **Q15: What asset would best support your 3-5 minute walkthrough recording or live demo interview?**  
  * **Decision:** **`python demo.py --live` CLI with real-time console tracing + ready-to-read walkthrough script**  
  * *Features:* Displays Step 1 hybrid hits, Step 2 neighbor-turn expansion, and final verified quotes in real-time, plus a 3-line Colab snippet in `README.md`.

---

### Batch 4: SDK, Vector Engine, Checkpointing, Layout & Graphify Development Tool

* **Q16: Which Python Gemini SDK library should we use for API calls?**  
  * **Decision:** **Modern `google-genai` SDK (`from google import genai`)**  
  * *Implementation:* Native Pydantic schema validation (`GenerateContentConfig(response_mime_type="application/json", response_schema=...)`) with active model ID `gemini-3.5-flash-lite` (tiered failover to `gemini-3.1-flash-lite`).

* **Q17: How should the dense embeddings from BAAI/bge-small-en-v1.5 be stored and queried alongside SQLite FTS5?**  
  * **Decision:** **SQLite BLOB storage + NumPy L2-normalized dot product**  
  * *Rationale:* 100% portable, zero C/C++ build errors across Windows/Linux/Colab. Pre-filtering by `team_id` leaves only ~100–300 turns per query, computing exact similarity in < 1ms.

* **Q18: During the full 25-question run (and TS3012 brief), should the pipeline save incremental checkpoints?**  
  * **Decision:** **Atomic JSON Checkpointing (`os.replace`) with `--fresh` override**  
  * *Rationale:* Crash-safe and idempotent against rate limits (HTTP 429) or timeouts.

* **Q19: What repository file structure do you prefer?**  
  * **Decision:** **Standard `src/` layout**  
  * *Rationale:* Makes the model-vs-code boundary immediately obvious to human reviewers and prevents root import clutter.

* **Q20: How should the required 1-page write-up deliverable be formatted?**  
  * **Decision:** **Structured `WRITEUP.md` covering all 7 rubric subsections**  
  * *Rubric Sections:* Architecture, Model-vs-Code, Scaling Table, 10 Custom Qs, 3 Failures, Platform Reasoning, What Production Would Need at Real Scale.

* **Special Tool Requirement:**  
  * **`graphify` Tooling:** Used strictly during agent development/planning to map knowledge graphs, relationships, and data dependencies; excluded from production agent runtime code.

---

## 4. Next Step: Implementation Milestones

1. **Milestone 1:** Build `src/ingest.py` (Transcript turn parser + SQLite FTS5 + embedding store).
2. **Milestone 2:** Build `src/embeddings.py` and `src/retriever.py` (Hybrid search with team pre-filter).
3. **Milestone 3:** Build `src/verifier.py` (Deterministic citation validation & contraction-safe substring alignment).
4. **Milestone 4:** Build `src/agent.py` and `src/brief.py` (2-step agent reasoning loop + TS3012 pre-meeting brief).
5. **Milestone 5:** Build `run.py`, `demo.py`, evaluate benchmark, and generate `answers.json` & `WRITEUP.md`.
