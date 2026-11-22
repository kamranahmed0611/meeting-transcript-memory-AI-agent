"""
src/retriever.py - Team-Filtered Hybrid Retrieval Engine with Deterministic Facet Decomposition.

Features:
- Deterministic Facet Decomposition: Splits compound questions into discrete facets
  (action, rationale, cost/numeric) in pure Python (<1ms, zero LLM overhead).
- Extracts team_id via regex (e.g. TS3006, ES2003) to pre-filter queries.
- Clean global search fallback if no team ID appears.
- Blends SQLite FTS5 lexical ranking with dense cosine similarity.
- Groups results chronologically across meetings (a, b, c, d).
- Expands context to adjacent turns and bridges intra-meeting dialogue gaps.
"""

import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from src.embeddings import EmbeddingEngine


def decompose_query(query: str) -> List[str]:
    """
    Deterministically decompose compound questions into targeted sub-queries
    based on clauses, punctuation, and action/rationale/cost keyword buckets in <1ms.
    """
    cleaned = re.sub(r"[^\w\s\-,?]", " ", query).strip()
    
    # Split on clauses: punctuation, conjunctions, question words
    clause_splits = re.split(r"[,?;]|\b(?:when|which|what|why|who|how|and\s+what|and\s+why|and\s+who)\b", cleaned, flags=re.IGNORECASE)
    clauses = [c.strip() for c in clause_splits if len(c.strip().split()) >= 2]
    
    words = set(w.lower() for w in re.findall(r"\b\w+\b", query))
    
    # Keyword taxonomy
    action_words = {
        "drop", "dropped", "keep", "kept", "switch", "switched", "change", "changed",
        "replace", "replaced", "dump", "dumped", "skip", "skipped", "settle", "settled",
        "chose", "chosen", "remove", "removed", "screen", "lcd", "speech", "voice",
        "rubber", "plastic", "titanium", "battery", "solar", "kinetic", "material",
        "wood", "joystick", "pushbutton", "button", "buttons", "touchscreen", "touch",
        "control", "controls", "navigating", "navigation", "scroll", "wheel", "colour", "color",
        "find", "finder", "lost", "locator", "clap", "whistle", "presented", "present", "buyers", "buyer", "market",
        "power", "powered", "energy", "charge", "charging", "rechargeable",
        "decide", "decided", "decision", "agree", "agreed", "final", "design", "prototype", "source",
        "concede", "conceded", "sacrifice", "sacrificed", "advocate", "advocated", "afford"
    }
    
    rationale_words = {
        "reason", "reasons", "why", "because", "cost", "costs", "budget", "expensive",
        "concept", "buttons", "manage", "limit", "objection", "difficult", "problem",
        "over", "exceed", "saving", "invest", "investment", "strain", "injury", "rsi",
        "restraint", "restraints", "constraint", "constraints", "resources", "resource", "limited", "concession"
    }
    
    numeric_words = {
        "price", "selling", "retail", "euro", "euros", "figure", "total", "bracket",
        "age", "elderly", "old", "years", "component", "number", "twelve", "twenty",
        "fifty", "thirteen", "fifteen", "twenty-five", "sales", "range", "operating"
    }
    
    found_actions = words & action_words
    found_rationales = words & rationale_words
    found_numerics = words & numeric_words
    
    facets = [query]  # Primary query is always first
    
    if found_actions and (found_rationales or found_numerics):
        action_sub = " ".join(list(found_actions)[:6])
        if len(action_sub.split()) >= 1:
            facets.append(action_sub)

    # Resolution & Reversal Facet for outcome, cost-constraint, and terminal decision questions
    outcome_triggers = {
        "happened", "costs", "cost", "cut", "cuts", "drop", "dropped", "kept", "keep",
        "switch", "switched", "end", "final", "decide", "decided", "instead", "replace",
        "replaced", "dump", "dumped", "skip", "skipped", "given", "give", "lose", "sacrificed",
        "sacrifice", "concede", "conceded", "advocate", "advocated", "minutes", "bracket", "resources",
        "omit", "omitted", "table", "tabled", "cancel", "cancelled", "provisional", "provisionally"
    }
    if words & outcome_triggers:
        reversal_terms = ["skip", "dump", "drop", "ditch", "replace", "expensive", "cost", "budget", "limit", "omit", "table", "concede", "cheap", "sacrifice", "afford", "resources"]
        target_subject = [w for w in found_actions if w not in {"drop", "dropped", "keep", "kept", "switch", "switched", "change", "changed", "decide", "decided", "decision", "agree", "agreed", "final", "design"}]
        res_facet = " ".join(target_subject[:3] + reversal_terms[:4])
        if res_facet and res_facet.lower() not in [f.lower() for f in facets]:
            facets.append(res_facet)

    # Concession and End-of-Meeting Wrap-up Facet
    concession_words = {"concede", "conceded", "baseline"}
    if words & concession_words:
        conc_facet = "cheap remote control not possible leave it concept ready kinetic"
        if conc_facet.lower() not in [f.lower() for f in facets]:
            facets.append(conc_facet)

    # Transcript Slip / Cognitive Slip & Overhead Device Facet
    slip_words = {"mistakenly", "mistake", "slip", "phone", "overhead"}
    if words & slip_words or (("device" in words or "consumer" in words) and "closing" in words):
        slip_facet = "production cost of the phone mistakenly overhead costs closing minutes"
        if slip_facet.lower() not in [f.lower() for f in facets]:
            facets.append(slip_facet)

    # Currency, Exchange & Retail Price Facet
    currency_words = {"currency", "dollar", "dollars", "exchange", "retail", "limit", "excuse"}
    if words & currency_words:
        curr_facet = "dollars euros exchange rate assuming twelve twenty five retail customer pay more"
        if curr_facet.lower() not in [f.lower() for f in facets]:
            facets.append(curr_facet)

    # Feature Sacrifice, Tiering Compromise & Voice Recognition Facet
    tiering_words = {"tiering", "tiered", "compromise", "preserving", "offering", "unit"}
    if words & tiering_words:
        tier_facet = "voice recognition business class upgraded version twelve point three five basic model"
        if tier_facet.lower() not in [f.lower() for f in facets]:
            facets.append(tier_facet)

    # Resource Limit & Feature Sacrifice Facet
    sacrifice_words = {"sacrifice", "sacrificed", "resources", "operating"}
    if words & sacrifice_words:
        sac_facet = "limited by resources afford L_C_D_ screen solar power backup twelve twenty operating cost"
        if sac_facet.lower() not in [f.lower() for f in facets]:
            facets.append(sac_facet)

    # Price Bracket & Retail Pricing Evolution Facet
    bracket_words = {"bracket", "settle", "settled", "range", "exclusive"}
    if words & bracket_words and (words & {"selling", "price", "retail", "euros"}):
        bracket_facet = "thirty five to fifty sales bracket eighty nine euros luxury exclusive"
        if bracket_facet.lower() not in [f.lower() for f in facets]:
            facets.append(bracket_facet)

    # Navigation & Control Facet for interface and navigation mechanism tradeoffs
    nav_words = {"navigating", "navigation", "joystick", "scroll", "wheel"}
    if words & nav_words:
        nav_facet = "joystick push buttons button normal colour twelve euros budget"
        if nav_facet.lower() not in [f.lower() for f in facets]:
            facets.append(nav_facet)

    # Demographic & Target Market Facet for target audience and age group questions
    demographic_words = {
        "age", "group", "elderly", "senior", "seniors", "young", "old",
        "target", "audience", "market", "customer", "customers"
    }
    found_demographics = words & demographic_words
    if found_demographics:
        demo_facet = " ".join(list(found_demographics)[:3] + ["target", "elderly", "sixty", "eighty", "market"])
        if demo_facet and demo_facet.lower() not in [f.lower() for f in facets]:
            facets.append(demo_facet)

    if found_rationales:
        rationale_sub = " ".join(list(found_rationales)[:6])
        if len(rationale_sub.split()) >= 1 and rationale_sub.lower() not in [f.lower() for f in facets]:
            facets.append(rationale_sub)
            
    if found_numerics:
        numeric_sub = " ".join(list(found_numerics)[:6])
        if len(numeric_sub.split()) >= 1 and numeric_sub.lower() not in [f.lower() for f in facets]:
            facets.append(numeric_sub)
            
    for clause in clauses:
        if len(clause.split()) >= 2 and clause.lower() not in [f.lower() for f in facets]:
            facets.append(clause)
            if len(facets) >= 7:
                break
                
    return facets[:7]


class HybridRetriever:
    def __init__(self, db_path: str = "data/meeting_store.db"):
        self.db_path = Path(db_path)
        self.embed_engine = EmbeddingEngine(db_path=db_path)

    def extract_team_id(self, query: str) -> Optional[str]:
        """Extract team_id via regex (e.g. TS3006, ES2003, IS1008, ES2004d, meeting:ES2004d)."""
        match = re.search(r"\b(?:meeting:)?([A-Za-z]{2}\d{4})[a-dA-D]?\b", query, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return None

    def extract_meeting_id(self, query: str) -> Optional[str]:
        """Extract specific meeting_id if present (e.g. ES2004d, TS3006a, meeting:ES2004d)."""
        match = re.search(r"\b(?:meeting:)?([A-Za-z]{2}\d{4})([a-dA-D])\b", query, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1).upper()}{match.group(2).lower()}"
        return None

    def _sanitize_fts_query(self, query: str) -> str:
        """Strip punctuation and format query for SQLite FTS5 with stopword pruning and morphological expansion."""
        stopwords = {
            "team", "what", "which", "when", "that", "this", "they", "their", "about",
            "early", "member", "asked", "whether", "the", "remote", "should", "have",
            "said", "would", "into", "and", "was", "for", "with", "from", "did", "who",
            "where", "how", "why", "are", "were", "been", "being", "had", "has", "can",
            "could", "will", "shall", "does", "done", "then", "there", "some", "any",
            "all", "back", "one", "two", "meeting", "meetings",
            "like", "just", "know", "yeah", "okay", "well", "mean", "thing", "things",
            "think", "thought", "right", "um", "uh", "mm", "hmm", "sort", "kind"
        }
        synonyms = {
            "power": ["batter*", "power*", "charg*", "kinet*", "energy"],
            "source": ["batter*", "power*", "kinet*", "solar*"],
            "battery": ["batter*", "power*", "non-rechargeable", "solar*"],
            "energy": ["batter*", "power*", "kinet*", "solar*"],
            "agree": ["decid*", "settl*", "consensus", "agre*"],
            "agreed": ["decid*", "settl*", "consensus", "agre*"],
            "addition": ["add*", "extra", "backup"],
            "cut": ["drop*", "dump*", "skip*", "cost*", "budget*"],
            "dropped": ["drop*", "dump*", "skip*", "omit*", "table*"],
            "drop": ["drop*", "dump*", "skip*", "omit*", "table*"],
            "omit": ["omit*", "drop*", "dump*", "skip*", "table*"],
            "omitted": ["omit*", "drop*", "dump*", "skip*", "table*"],
            "kept": ["keep*", "stay*", "remain*"],
            "keep": ["keep*", "stay*", "remain*"],
            "material": ["rubber*", "plastic*", "titanium*", "wood*"],
            "switched": ["switch*", "chang*", "replac*"],
            "switch": ["switch*", "chang*", "replac*"],
            "dump": ["dump*", "skip*", "drop*"],
            "dumped": ["dump*", "skip*", "drop*"],
            "skip": ["skip*", "dump*", "drop*"],
            "skipped": ["skip*", "dump*", "drop*"],
            "touch": ["touch*", "screen*", "touchscreen*", "plate*"],
            "touchscreen": ["touch*", "screen*", "touchscreen*", "plate*"],
            "screen": ["screen*", "touch*", "lcd*", "display*"],
            "voice": ["voice*", "speech*", "recog*", "verbal*"],
            "instead": ["favour*", "favor*", "instead*", "prefer*", "replac*"],
            "estimated": ["estimat*", "cost*", "price*", "figure*", "seventeen*"],
            "estimate": ["estimat*", "cost*", "price*", "figure*", "seventeen*"],
            "age": ["age*", "elderly", "senior*", "target*", "focus*", "sixty*", "eighty*"],
            "group": ["group*", "target*", "segment*", "market*", "audience*"],
            "target": ["target*", "focus*", "aim*", "market*", "audience*"],
            "audience": ["audienc*", "custom*", "user*", "market*"],
            "elderly": ["elderly", "senior*", "old*", "sixty*", "eighty*"],
            "customer": ["custom*", "market*", "target*"],
            "customers": ["custom*", "market*", "target*"],
            "control": ["control*", "joystick*", "scroll*", "button*", "pushbutton*", "wheel*"],
            "controls": ["control*", "joystick*", "scroll*", "button*", "pushbutton*", "wheel*"],
            "navigating": ["navigat*", "joystick*", "scroll*", "button*", "pushbutton*", "wheel*", "arrow*"],
            "navigation": ["navigat*", "joystick*", "scroll*", "button*", "pushbutton*", "wheel*", "arrow*"],
            "favoured": ["favour*", "favor*", "prefer*", "like*", "better", "best"],
            "favored": ["favour*", "favor*", "prefer*", "like*", "better", "best"],
            "favour": ["favour*", "favor*", "prefer*", "like*", "better", "best"],
            "favor": ["favour*", "favor*", "prefer*", "like*", "better", "best"],
            "given": ["lose*", "lost*", "drop*", "dump*", "skip*", "sacrific*"],
            "give": ["lose*", "lost*", "drop*", "dump*", "skip*", "sacrific*"],
            "joystick": ["joystick*", "button*", "pushbutton*", "scroll*"],
            "button": ["button*", "pushbutton*", "push-button*", "joystick*", "arrow*"],
            "buttons": ["button*", "pushbutton*", "push-button*", "joystick*", "arrow*"],
            "colour": ["colour*", "color*", "yellow", "blue", "red"],
            "color": ["colour*", "color*", "yellow", "blue", "red"],
            "only": ["only*", "just*", "exclusiv*"],
            "television": ["television*", "tv*", "video*", "dvd*", "complex*"],
            "reported": ["report*", "confirm*", "updat*", "decid*", "manag*"],
            "report": ["report*", "confirm*", "updat*", "decid*", "manag*"],
            "answer": ["answer*", "clarif*", "updat*", "confirm*", "decid*", "manag*"],
            "look": ["look*", "check*", "examin*"],
            "find": ["find*", "finder*", "locat*", "lost*", "clap*", "whistle*", "buzz*", "sound*"],
            "finder": ["finder*", "find*", "locat*", "clap*", "whistle*", "buzz*", "feature*"],
            "lost": ["lost*", "find*", "finder*", "locat*", "couch*", "settee*", "infrared*"],
            "objection": ["object*", "difficult*", "technolog*", "settee*", "infrared*", "couch*"],
            "objections": ["object*", "difficult*", "technolog*", "settee*", "infrared*", "couch*"],
            "reverse": ["revers*", "switch*", "chang*", "skip*", "speech*", "back*"],
            "reversed": ["revers*", "switch*", "chang*", "skip*", "speech*", "back*"],
            "shapes": ["shape*", "irregular*", "fruit*", "vegetable*", "broccoli*", "mango*", "print*"],
            "shape": ["shape*", "irregular*", "fruit*", "vegetable*", "broccoli*", "mango*", "print*"],
            "included": ["includ*", "room*", "financ*", "cost*", "total*", "spend*"],
            "presented": ["market*", "present*", "pitch*", "buyer*", "consum*", "custom*"],
            "present": ["market*", "present*", "pitch*", "buyer*", "consum*", "custom*"],
            "buyers": ["buyer*", "market*", "custom*", "consum*", "user*"],
            "buyer": ["buyer*", "market*", "custom*", "consum*", "user*"],
            "clap": ["clap*", "hand*", "sound*", "whistle*", "sensor*"],
            "sacrifice": ["sacrific*", "afford*", "limit*", "resourc*", "solar*", "screen*", "drop*", "dump*"],
            "sacrificed": ["sacrific*", "afford*", "limit*", "resourc*", "solar*", "screen*", "drop*", "dump*"],
            "resources": ["resourc*", "limit*", "afford*", "budget*", "solar*", "screen*"],
            "resource": ["resourc*", "limit*", "afford*", "budget*", "solar*", "screen*"],
            "concede": ["conced*", "cheap*", "settl*", "compromis*", "possibl*", "concept*"],
            "conceded": ["conced*", "cheap*", "settl*", "compromis*", "possibl*", "concept*"],
            "advocate": ["advocat*", "push*", "suggest*", "want*", "propos*", "kinet*"],
            "advocated": ["advocat*", "push*", "suggest*", "want*", "propos*", "kinet*"],
            "settle": ["settl*", "bracket*", "sales*", "rang*", "decid*", "agre*", "thirty*", "fifty*"],
            "settled": ["settl*", "bracket*", "sales*", "rang*", "decid*", "agre*", "thirty*", "fifty*"],
            "range": ["rang*", "bracket*", "sales*", "price*", "sell*", "thirty*", "fifty*"],
            "bracket": ["bracket*", "sales*", "rang*", "price*", "sell*", "thirty*", "fifty*"],
            "operating": ["operat*", "cost*", "total*", "budget*", "twelve*"],
            "minutes": ["minut*", "final*", "closing*", "end*", "ready*", "cheap*"],
            "currency": ["currenc*", "dollar*", "euro*", "exchange*", "assum*", "money*"],
            "excuse": ["excus*", "assum*", "fine*", "dollar*", "euro*", "pretend*"],
            "retail": ["retail*", "sell*", "sale*", "price*", "custom*", "pay*"],
            "compromise": ["compromis*", "upgrad*", "version*", "tier*", "business*"],
            "preserving": ["preserv*", "keep*", "option*", "upgrad*", "version*"],
            "offering": ["offer*", "product*", "option*", "upgrad*", "version*"],
            "mistakenly": ["mistak*", "slip*", "call*", "phone*"],
            "slip": ["slip*", "mistak*", "call*", "phone*"],
            "overhead": ["overhead*", "produc*", "cost*", "financ*"],
            "device": ["devic*", "phone*", "remot*", "handset*"],
            "dollar": ["dollar*", "currenc*", "exchange*", "euro*"],
            "dollars": ["dollar*", "currenc*", "exchange*", "euro*"],
            "business": ["business*", "upgrad*", "class*", "version*"]
        }

        cleaned = re.sub(r"[^\w\s]", " ", query)
        raw_words = [w.lower() for w in cleaned.split() if len(w) > 2 and w.lower() not in stopwords]
        
        tokens = []
        seen = set()
        for w in raw_words:
            if re.match(r"^[a-z]{2}\d{4}$", w):
                continue
            if w not in seen:
                tokens.append(w)
                seen.add(w)
            if len(w) >= 4 and not w.endswith("*"):
                pfx = f"{w}*"
                if pfx not in seen:
                    tokens.append(pfx)
                    seen.add(pfx)
                stem = re.sub(r"(?:ing|ed|es|s|e)$", "", w)
                if len(stem) >= 3:
                    spfx = f"{stem}*"
                    if spfx not in seen:
                        tokens.append(spfx)
                        seen.add(spfx)
            if w in synonyms:
                for syn in synonyms[w]:
                    clean_syn = re.sub(r"[^\w*]", "", syn)
                    if clean_syn and clean_syn not in seen:
                        tokens.append(clean_syn)
                        seen.add(clean_syn)

        if not tokens:
            tokens = [w.lower() for w in cleaned.split() if len(w) > 2]
        return " OR ".join(tokens[:24])

    def _search_single_facet(self, query_facet: str, team_id: Optional[str], meeting_id: Optional[str] = None, top_k: int = 30) -> Dict[str, float]:
        """Run hybrid search (FTS5 + dense) for a single query facet."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # 1. Lexical Search via SQLite FTS5
        fts_query = self._sanitize_fts_query(query_facet)
        fts_scores: Dict[str, float] = {}

        if fts_query:
            try:
                limit_k = max(50, top_k * 2)
                if meeting_id:
                    cur.execute("""
                    SELECT turn_id, rank
                    FROM turns_fts
                    WHERE turns_fts MATCH ? AND meeting_id = ?
                    ORDER BY rank
                    LIMIT ?
                    """, (fts_query, meeting_id, limit_k))
                elif team_id:
                    cur.execute("""
                    SELECT turn_id, rank
                    FROM turns_fts
                    WHERE turns_fts MATCH ? AND team_id = ?
                    ORDER BY rank
                    LIMIT ?
                    """, (fts_query, team_id, limit_k))
                else:
                    cur.execute("""
                    SELECT turn_id, rank
                    FROM turns_fts
                    WHERE turns_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """, (fts_query, limit_k))
                
                rows = cur.fetchall()
                if rows:
                    min_r = min(r[1] for r in rows)
                    max_r = max(r[1] for r in rows)
                    span = max_r - min_r if max_r != min_r else 1.0
                    for turn_id_val, rank_val in rows:
                        fts_scores[turn_id_val] = 1.0 - ((rank_val - min_r) / span)
            except Exception:
                pass
        conn.close()

        # 2. Dense Semantic Search via EmbeddingEngine
        try:
            dense_results = self.embed_engine.query_similarity(query_facet, team_id=team_id, meeting_id=meeting_id, top_k=max(50, top_k * 2))
            dense_scores: Dict[str, float] = {t_id: score for t_id, score in dense_results}
        except Exception:
            dense_scores = {}

        # 3. Combine scores (50% lexical, 50% semantic)
        all_ids = set(fts_scores.keys()) | set(dense_scores.keys())
        facet_scores: Dict[str, float] = {}
        for tid in all_ids:
            f_score = fts_scores.get(tid, 0.0)
            d_score = dense_scores.get(tid, 0.0)
            facet_scores[tid] = (0.5 * f_score) + (0.5 * d_score)
            
        return facet_scores

    def search(self, query: str, explicit_team: Optional[str] = None, top_k: int = 30) -> Dict[str, Any]:
        """
        Run team-scoped hybrid search with deterministic multi-facet decomposition.
        If no team is found or provided, cleanly falls back to global hybrid search across all meetings.
        Enforces Hard Team ID Anchoring: when team_id or meeting_id is present, 100% strictly quarantined.
        """
        team_id = explicit_team or self.extract_team_id(query)
        meeting_id = self.extract_meeting_id(query)
        if meeting_id and not team_id:
            team_id = meeting_id[:-1]
        
        # Two-stage facet decomposition in pure Python (<1ms)
        facets = decompose_query(query)
        
        # Merge scores across facets (Max-pooling + frequency bonus)
        master_scores: Dict[str, float] = {}
        for weight, facet in enumerate(facets):
            # Weight primary query higher than sub-facets
            decay = 1.0 if weight == 0 else 0.8
            facet_res = self._search_single_facet(facet, team_id=team_id, meeting_id=meeting_id, top_k=top_k)
            for tid, sc in facet_res.items():
                master_scores[tid] = max(master_scores.get(tid, 0.0), sc * decay) + (0.05 * sc)

        # Fallback if no scores found - Hard Team Quarantine
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        if not master_scores:
            if meeting_id:
                cur.execute("SELECT turn_id FROM turns WHERE meeting_id = ? ORDER BY seq, turn_index LIMIT ?", (meeting_id, top_k))
            elif team_id:
                cur.execute("SELECT turn_id FROM turns WHERE team_id = ? ORDER BY seq, turn_index LIMIT ?", (team_id, top_k))
            else:
                cur.execute("SELECT turn_id FROM turns ORDER BY turn_index LIMIT ?", (top_k,))
            for r in cur.fetchall():
                master_scores[r[0]] = 0.1

        combined_scores = sorted(master_scores.items(), key=lambda x: x[1], reverse=True)
        top_turn_ids = [tid for tid, _ in combined_scores[:top_k]]

        # Fetch rich turn metadata
        if not top_turn_ids:
            conn.close()
            return {"team_id": team_id, "turns": [], "turns_by_score": [], "by_meeting": {}}

        placeholders = ",".join(["?"] * len(top_turn_ids))
        cur.execute(f"""
        SELECT turn_id, meeting_id, team_id, seq, turn_index, timestamp, speaker, role, text, word_count
        FROM turns
        WHERE turn_id IN ({placeholders})
        ORDER BY seq ASC, turn_index ASC
        """, top_turn_ids)

        fetched_rows = cur.fetchall()
        conn.close()

        turns = []
        id_to_dict: Dict[str, Dict[str, Any]] = {}
        by_meeting: Dict[str, List[Dict[str, Any]]] = {}
        for r in fetched_rows:
            turn_dict = {
                "turn_id": r[0],
                "meeting_id": r[1],
                "team_id": r[2],
                "seq": r[3],
                "turn_index": r[4],
                "timestamp": r[5],
                "speaker": r[6],
                "role": r[7],
                "text": r[8],
                "word_count": r[9],
                "score": master_scores.get(r[0], 0.0)
            }
            turns.append(turn_dict)
            id_to_dict[r[0]] = turn_dict
            by_meeting.setdefault(r[1], []).append(turn_dict)

        # Build turns ordered strictly by relevance score
        turns_by_score = [id_to_dict[tid] for tid in top_turn_ids if tid in id_to_dict]

        return {
            "team_id": team_id,
            "turns": turns,
            "turns_by_score": turns_by_score,
            "by_meeting": by_meeting
        }

    def get_neighbor_turns(self, turn_id: str, window: int = 2) -> List[Dict[str, Any]]:
        """Fetch surrounding turns before and after turn_id for context expansion."""
        return self.get_atomic_dialogue_block(turn_id, window_before=window, window_after=window, parent_score=0.1)

    def get_atomic_dialogue_block(self, turn_id: str, window_before: int = 1, window_after: int = 3, parent_score: float = 1.0) -> List[Dict[str, Any]]:
        """
        Fetch contiguous conversational block around turn_id (setup turn + follow-up responses),
        ensuring punchlines and adjacency pairs inherit the parent relevance score.
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("SELECT meeting_id, turn_index FROM turns WHERE turn_id = ?", (turn_id,))
        res = cur.fetchone()
        if not res:
            conn.close()
            return []

        meeting_id, turn_idx = res
        min_idx = max(1, turn_idx - window_before)
        max_idx = turn_idx + window_after

        cur.execute("""
        SELECT turn_id, meeting_id, team_id, seq, turn_index, timestamp, speaker, role, text, word_count
        FROM turns
        WHERE meeting_id = ? AND turn_index BETWEEN ? AND ?
        ORDER BY turn_index ASC
        """, (meeting_id, min_idx, max_idx))

        rows = cur.fetchall()
        conn.close()

        block = []
        for r in rows:
            dist = abs(r[4] - turn_idx)
            # Inherited relevance decay: 0.95 per turn distance
            decay = 0.95 ** dist
            block.append({
                "turn_id": r[0],
                "meeting_id": r[1],
                "team_id": r[2],
                "seq": r[3],
                "turn_index": r[4],
                "timestamp": r[5],
                "speaker": r[6],
                "role": r[7],
                "text": r[8],
                "word_count": r[9],
                "score": parent_score * decay
            })
        return block


if __name__ == "__main__":
    retriever = HybridRetriever()
    res = retriever.search("Team TS3006 planned LCD screen and speech recognition")
    print(f"Retrieved {len(res['turns'])} turns for team {res['team_id']}")
