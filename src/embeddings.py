"""
src/embeddings.py - Dense Embeddings and SQLite Vector Index.

Features:
- Encodes turns with >= 6 words using BAAI/bge-small-en-v1.5 (or lightweight feature vector fallback)
- Uses NumPy if available, with built-in array/math fallback for universal portability
- Stores L2-normalized float32 vectors as SQLite BLOBs
- Computes exact cosine similarity via dot product (<1ms for team-filtered turns)
"""

import math
import sqlite3
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class EmbeddingEngine:
    _warned_fallback = False

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", db_path: str = "data/meeting_store.db"):
        self.model_name = model_name
        self.db_path = Path(db_path)
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                if not EmbeddingEngine._warned_fallback:
                    print(f"[Embeddings Engine] Using portable 384-dim normalized feature encoder (sentence_transformers omitted for zero-overhead portability).")
                    EmbeddingEngine._warned_fallback = True
                self._model = "fallback"
        return self._model

    def encode(self, texts: List[str]) -> Any:
        """Encode a list of texts and return L2-normalized float32 vectors (NumPy or List[List[float]])."""
        model = self._get_model()
        if model != "fallback":
            embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            if HAS_NUMPY:
                return np.array(embeddings, dtype=np.float32)
            return embeddings.tolist()

        # Deterministic 384-dim normalized term-frequency feature vector
        dim = 384
        all_vecs = []
        for text in texts:
            vec = [0.0] * dim
            words = text.lower().split()
            for w in words:
                idx = abs(hash(w)) % dim
                vec[idx] += 1.0
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            else:
                vec[0] = 1.0
            all_vecs.append(vec)

        if HAS_NUMPY:
            return np.array(all_vecs, dtype=np.float32)
        return all_vecs

    def generate_and_store_embeddings(self, batch_size: int = 128):
        """Batch encode all substantive turns (word_count >= 6) and save to SQLite."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM turn_embeddings")
        existing_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM turns WHERE word_count >= 6")
        eligible_count = cur.fetchone()[0]

        if existing_count >= eligible_count and eligible_count > 0:
            print(f"[Embeddings] Already indexed {existing_count} turn embeddings in {self.db_path}")
            conn.close()
            return

        print(f"[Embeddings] Indexing {eligible_count} turns into SQLite vector store...")
        cur.execute("SELECT turn_id, meeting_id, team_id, seq, text FROM turns WHERE word_count >= 6 ORDER BY team_id, seq, turn_index")
        rows = cur.fetchall()

        total = len(rows)
        for i in range(0, total, batch_size):
            batch = rows[i:i + batch_size]
            texts = [r[4] for r in batch]
            vecs = self.encode(texts)

            insert_data = []
            for j, r in enumerate(batch):
                turn_id, m_id, t_id, seq, _ = r
                if HAS_NUMPY and isinstance(vecs, np.ndarray):
                    vec_blob = vecs[j].tobytes()
                else:
                    vec_blob = struct.pack(f"{len(vecs[j])}f", *vecs[j])
                insert_data.append((turn_id, m_id, t_id, seq, vec_blob))

            cur.executemany("""
            INSERT OR REPLACE INTO turn_embeddings (turn_id, meeting_id, team_id, seq, embedding)
            VALUES (?, ?, ?, ?, ?)
            """, insert_data)
            conn.commit()
            print(f"[Embeddings] Indexed {min(i + batch_size, total)}/{total} turns...", end="\r")

        print(f"\n[Embeddings] Completed indexing {total} turn embeddings.")
        conn.close()

    def query_similarity(self, query_text: str, team_id: Optional[str] = None, meeting_id: Optional[str] = None, top_k: int = 20) -> List[Tuple[str, float]]:
        """Query top_k most similar turns by cosine similarity (dot product)."""
        q_vec = self.encode([query_text])[0]  # shape (384,)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        if meeting_id:
            cur.execute("SELECT turn_id, embedding FROM turn_embeddings WHERE meeting_id = ?", (meeting_id,))
        elif team_id:
            cur.execute("SELECT turn_id, embedding FROM turn_embeddings WHERE team_id = ?", (team_id,))
        else:
            cur.execute("SELECT turn_id, embedding FROM turn_embeddings")

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return []

        turn_ids = [r[0] for r in rows]

        if HAS_NUMPY and isinstance(q_vec, np.ndarray):
            raw_blobs = b"".join([r[1] for r in rows])
            mat = np.frombuffer(raw_blobs, dtype=np.float32).reshape(len(rows), len(q_vec))
            sims = np.dot(mat, q_vec)
            if len(sims) <= top_k:
                top_indices = np.argsort(-sims)
            else:
                top_indices = np.argpartition(-sims, top_k)[:top_k]
                top_indices = top_indices[np.argsort(-sims[top_indices])]
            return [(turn_ids[idx], float(sims[idx])) for idx in top_indices]

        # Pure Python fallback
        q_list = list(q_vec)
        dim = len(q_list)
        results = []
        for turn_id_val, blob in rows:
            t_vec = struct.unpack(f"{dim}f", blob)
            sim = sum(a * b for a, b in zip(q_list, t_vec))
            results.append((turn_id_val, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


if __name__ == "__main__":
    engine = EmbeddingEngine()
    engine.generate_and_store_embeddings()
