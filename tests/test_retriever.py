"""
tests/test_retriever.py - Unit tests for HybridRetriever.

Validates:
1. Regex extraction of team_id across question styles.
2. Pre-filtering by team_id vs fallback to global search.
3. Neighbor turn expansion for multi-turn conversational context.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retriever import HybridRetriever


def test_retriever():
    retriever = HybridRetriever(db_path="data/meeting_store.db")

    # 1. Test team_id regex extraction
    assert retriever.extract_team_id("Team TS3006 planned an LCD screen") == "TS3006"
    assert retriever.extract_team_id("What did ES2003 lean towards first?") == "ES2003"
    assert retriever.extract_team_id("In Team IS1008, a team member...") == "IS1008"
    assert retriever.extract_team_id("General question without team code") is None
    print("Test 1 Passed: Team ID regex extraction verified.")

    # 2. Test team-scoped retrieval
    res = retriever.search("Team TS3006 planned LCD screen and speech recognition", top_k=10)
    assert res["team_id"] == "TS3006"
    assert len(res["turns"]) > 0
    # Confirm all retrieved turns belong to TS3006
    for t in res["turns"]:
        assert t["team_id"] == "TS3006"
    print("Test 2 Passed: Team-scoped hybrid search confirmed.")

    # 3. Test global search fallback (no team ID)
    res_global = retriever.search("remote control battery lithium solar", top_k=5)
    assert res_global["team_id"] is None
    assert len(res_global["turns"]) > 0
    print("Test 3 Passed: Global hybrid search fallback confirmed.")

    # 4. Test neighbor turn expansion
    first_turn_id = res["turns"][0]["turn_id"]
    neighbors = retriever.get_neighbor_turns(first_turn_id, window=2)
    assert len(neighbors) >= 1
    print("Test 4 Passed: Neighbor turn expansion confirmed.")


if __name__ == "__main__":
    test_retriever()
    print("All retriever tests passed successfully!")
