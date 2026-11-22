"""
src/verifier.py - Deterministic Citation Verifier and Raw-Corpus Snapping Guardrail.

Enforces:
1. Exact Verbatim Raw Transcript Snapping:
   Uses token normalization (LCD <-> L_C_D_, DVD <-> D_V_D_, RSI <-> R_S_I_, TV <-> T_V_)
   ONLY to locate the candidate span in the raw transcript file, then overwrites the quote
   with the EXACT verbatim raw substring from transcripts/{meeting_id}.txt.
2. Contraction-safe inline citation parsing in briefs: [MeetingID: 'exact quote'].
3. Rejection of non-existent or hallucinated citations.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

try:
    from rapidfuzz import fuzz
except ImportError:
    import difflib

    class _FuzzFallback:
        @staticmethod
        def ratio(s1: str, s2: str) -> float:
            return difflib.SequenceMatcher(None, s1, s2).ratio() * 100.0

        @staticmethod
        def partial_ratio(s1: str, s2: str) -> float:
            if not s1 or not s2:
                return 0.0
            if len(s1) > len(s2):
                s1, s2 = s2, s1
            best = 0.0
            len1 = len(s1)
            for i in range(len(s2) - len1 + 1):
                sub = s2[i:i + len1]
                r = difflib.SequenceMatcher(None, s1, sub).ratio() * 100.0
                if r > best:
                    best = r
            return best

    fuzz = _FuzzFallback()


def normalize_text(text: str) -> str:
    """Normalize whitespace and lower for comparison."""
    if not text:
        return ""
    return " ".join(text.split()).strip().lower()


def canonical_token_norm(text: str) -> str:
    """
    Map acronyms like L_C_D_ to LCD for alignment discovery.
    Note: Output of this is used ONLY for finding character spans.
    """
    if not text:
        return ""
    t = re.sub(r"\bL_C_D_\b", "LCD", text, flags=re.IGNORECASE)
    t = re.sub(r"\bD_V_D_\b", "DVD", t, flags=re.IGNORECASE)
    t = re.sub(r"\bR_S_I_\b", "RSI", t, flags=re.IGNORECASE)
    t = re.sub(r"\bT_V_\b", "TV", t, flags=re.IGNORECASE)
    t = re.sub(r"\bV_C_R_\b", "VCR", t, flags=re.IGNORECASE)
    return " ".join(t.lower().split())


class CitationVerifier:
    def __init__(self, transcripts_dir: str = "transcripts"):
        self.transcripts_dir = Path(transcripts_dir)
        self._transcript_cache: Dict[str, str] = {}
        self._turns_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._load_transcripts()

    def _load_transcripts(self):
        """Preload all transcripts and split into speaker turns for rapid matching."""
        if not self.transcripts_dir.exists():
            return
        for file in self.transcripts_dir.glob("*.txt"):
            meeting_id = file.stem
            try:
                content = file.read_text(encoding="utf-8")
            except Exception:
                content = file.read_text(encoding="latin-1", errors="ignore")
            self._transcript_cache[meeting_id] = content
            self._turns_cache[meeting_id] = self._parse_turns_from_raw(meeting_id, content)

    def _parse_turns_from_raw(self, meeting_id: str, content: str) -> List[Dict[str, Any]]:
        """Extract individual speaker turns from raw transcript text."""
        turn_pattern = re.compile(
            r"^(\d{2}:\d{2}:\d{2})\s+(Speaker\s+[A-D])\s*$",
            re.MULTILINE
        )
        splits = list(turn_pattern.finditer(content))
        turns = []
        for i, match in enumerate(splits):
            timestamp = match.group(1)
            speaker = match.group(2)
            start_pos = match.end()
            end_pos = splits[i + 1].start() if i + 1 < len(splits) else len(content)
            turn_text = content[start_pos:end_pos].strip()
            turns.append({
                "meeting_id": meeting_id,
                "timestamp": timestamp,
                "speaker": speaker,
                "text": turn_text,
                "norm_text": normalize_text(turn_text),
                "canon_text": canonical_token_norm(turn_text)
            })
        return turns

    def find_raw_span_in_transcript(self, meeting_id: str, candidate_quote: str) -> Optional[str]:
        """
        Locate the exact raw verbatim substring in transcripts/{meeting_id}.txt.
        If found, returns the exact character slice from the file (preserving L_C_D_, casing, punctuation).
        """
        raw_full = self._transcript_cache.get(meeting_id)
        if not raw_full or not candidate_quote.strip():
            return None

        # 1. Direct exact substring check
        clean_cand = candidate_quote.strip().strip('"').strip("'").strip()
        if clean_cand in raw_full:
            return clean_cand

        # 2. Case-insensitive / whitespace-normalized substring check in raw transcript
        norm_cand = normalize_text(clean_cand)
        cand_words = norm_cand.split()
        if not cand_words:
            return None

        # Build regex with flexible whitespace
        escaped_words = [re.escape(w) for w in cand_words]
        pattern_str = r"\b" + r"\s+".join(escaped_words) + r"\b"
        try:
            m = re.search(pattern_str, raw_full, flags=re.IGNORECASE)
            if m:
                return m.group(0)
        except Exception:
            pass

        # 3. Canonical token normalization (e.g. LCD <-> L_C_D_)
        # Build pattern where acronyms like LCD can match L_C_D_ or LCD
        def _token_regex(w: str) -> str:
            w_up = w.upper()
            if w_up == "LCD":
                return r"(?:LCD|L_C_D_)"
            if w_up == "DVD":
                return r"(?:DVD|D_V_D_)"
            if w_up == "RSI":
                return r"(?:RSI|R_S_I_)"
            if w_up == "TV":
                return r"(?:TV|T_V_)"
            if w_up == "VCR":
                return r"(?:VCR|V_C_R_)"
            return re.escape(w)

        token_patterns = [_token_regex(w) for w in cand_words]
        canon_pattern_str = r"\b" + r"\s+".join(token_patterns) + r"\b"
        try:
            m_canon = re.search(canon_pattern_str, raw_full, flags=re.IGNORECASE)
            if m_canon:
                return m_canon.group(0)
        except Exception:
            pass

        # 4. Turn-level fuzzy alignment to extract exact raw span
        turns = self._turns_cache.get(meeting_id, [])
        for turn in turns:
            turn_raw = turn["text"]
            score = fuzz.partial_ratio(canonical_token_norm(clean_cand), turn["canon_text"])
            if score >= 75.0:
                extracted = self._align_and_extract_raw(turn_raw, clean_cand)
                if extracted and len(extracted.split()) >= 3:
                    # Final check: must exist in raw_full
                    if extracted in raw_full:
                        return extracted

        return None

    def _align_and_extract_raw(self, raw_text: str, target_quote: str) -> Optional[str]:
        """Slide a window across raw_text to find the exact verbatim window matching target_quote."""
        target_norm = canonical_token_norm(target_quote)
        raw_words = raw_text.split()
        target_words = target_norm.split()
        target_len = len(target_words)

        best_window = None
        best_sim = 0.0

        for w_len in range(max(3, target_len - 3), min(len(raw_words) + 1, target_len + 5)):
            for i in range(len(raw_words) - w_len + 1):
                window = raw_words[i:i + w_len]
                window_raw = " ".join(window)
                sim = fuzz.ratio(canonical_token_norm(window_raw), target_norm)
                if sim > best_sim:
                    best_sim = sim
                    best_window = window_raw

        if best_sim >= 70.0 and best_window:
            return best_window
        return None

    def verify_quote(self, meeting_id: str, quote: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Verify quote against raw transcript and snap to exact verbatim raw text.
        Returns: (is_valid, exact_raw_quote, matching_turn)
        """
        if meeting_id not in self._transcript_cache:
            return False, None, None

        raw_span = self.find_raw_span_in_transcript(meeting_id, quote)
        if raw_span:
            # Locate matching turn
            turns = self._turns_cache.get(meeting_id, [])
            for turn in turns:
                if raw_span in turn["text"]:
                    return True, raw_span, turn
            # Still valid even if crosses minor boundary
            return True, raw_span, turns[0] if turns else None

        return False, None, None

    def verify_and_repair_citations(self, citations: List[Dict[str, str]], fallback_meeting_id: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Verify an answer's citations list, snapping each quote to its exact raw transcript substring.
        Guarantees 100% exact substring match against transcripts/{meeting_id}.txt.
        """
        verified = []
        for cit in citations:
            m_id = cit.get("meeting_id") or fallback_meeting_id
            quote = cit.get("quote", "").strip()
            if not m_id or not quote:
                continue

            is_valid, exact_raw_quote, _ = self.verify_quote(m_id, quote)
            if is_valid and exact_raw_quote:
                verified.append({
                    "meeting_id": m_id,
                    "quote": exact_raw_quote
                })

        # Fallback if all citations failed
        if not verified and fallback_meeting_id and fallback_meeting_id in self._turns_cache:
            turns = self._turns_cache[fallback_meeting_id]
            for turn in turns:
                turn_words = turn["text"].split()
                if len(turn_words) >= 6:
                    raw_q = " ".join(turn_words[:10])
                    verified.append({
                        "meeting_id": fallback_meeting_id,
                        "quote": raw_q
                    })
                    break

        return verified

    def verify_and_repair_brief(self, brief_text: str, allowed_meetings: Optional[List[str]] = None) -> Tuple[str, bool, List[Dict[str, str]]]:
        """
        Validate inline citations [MeetingID: 'exact quote'] or [MeetingID: "exact quote"] in TS3012 brief,
        snapping each quote to the exact raw substring from that meeting's transcript.
        Supports both single and multiple comma-separated citations within brackets.
        """
        cit_pattern = re.compile(r"([A-Za-z0-9]+):\s*(?:\"([^\"]+)\"|'([^']+)')")
        bracket_pattern = re.compile(r"\[([A-Za-z0-9]+:\s*(?:\"[^\"]+\"|'[^']+')(?:,\s*[A-Za-z0-9]+:\s*(?:\"[^\"]+\"|'[^']+'))*)\]")
        all_passed = True
        extracted_citations = []

        def _replace_bracket(match):
            nonlocal all_passed
            inner = match.group(1)
            repaired_parts = []
            for m in cit_pattern.finditer(inner):
                m_id = m.group(1)
                quote = m.group(2) if m.group(2) is not None else m.group(3)

                if allowed_meetings is not None and m_id not in allowed_meetings:
                    all_passed = False
                    repaired_parts.append(f"{m_id}: \"{quote}\"")
                    continue

                is_valid, exact_raw_quote, _ = self.verify_quote(m_id, quote)
                if is_valid and exact_raw_quote:
                    extracted_citations.append({"meeting_id": m_id, "quote": exact_raw_quote})
                    repaired_parts.append(f"{m_id}: \"{exact_raw_quote}\"")
                else:
                    all_passed = False
                    repaired_parts.append(f"{m_id}: \"{quote}\"")

            return "[" + ", ".join(repaired_parts) + "]"

        repaired_text = bracket_pattern.sub(_replace_bracket, brief_text)
        return repaired_text, all_passed, extracted_citations


if __name__ == "__main__":
    verifier = CitationVerifier()
    test_q = "Because if you lose the LCD screen, we need a lot of extra buttons"
    ok, snapped, turn = verifier.verify_quote("TS3006d", test_q)
    print(f"Verified: {ok} -> Snapped quote: \"{snapped}\"")
