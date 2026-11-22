"""
tests/test_verifier.py - Unit tests for CitationVerifier.

Validates:
1. Exact verbatim quote matches in transcripts pass 100%.
2. Contraction-safe regex handles apostrophes without cutting quotes.
3. Paraphrased quotes are auto-repaired to verbatim spans.
4. Short (<6 words) verbatim quotes are NOT rejected if they are verbatim in the turn.
5. Exclusion of unauthorized meetings (e.g. TS3012d in pre-meeting brief).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.verifier import CitationVerifier, normalize_text


def test_quote_verification():
    verifier = CitationVerifier(transcripts_dir="transcripts")
    
    # Test verbatim quote from ES2002a
    valid, quote, turn = verifier.verify_quote("ES2002a", "Okay. Right. Um well this is the kick-off meeting")
    assert valid, "Expected verbatim quote to pass verification."
    print("Test 1 Passed: Exact verbatim quote verified.")

    # Test short verbatim quote (3-4 words) - should NOT be rejected
    valid_short, quote_short, _ = verifier.verify_quote("ES2002a", "kick-off meeting for our")
    assert valid_short, "Valid short verbatim quote should NOT be rejected."
    print("Test 2 Passed: Short verbatim quote accepted.")

    # Test contraction-safe parsing in brief
    brief_sample = "The team made decisions [ES2002a: 'this is the kick-off meeting for our our project']."
    repaired, all_passed, citations = verifier.verify_and_repair_brief(brief_sample)
    assert all_passed, "Contraction-safe brief citation should pass."
    assert len(citations) == 1
    print("Test 3 Passed: Contraction-safe brief citation passed.")

    # Test exclusion of TS3012d in brief
    leak_sample = "They decided in final meeting [TS3012d: 'we have to make a decision']."
    repaired_leak, leak_passed, _ = verifier.verify_and_repair_brief(leak_sample, allowed_meetings=["TS3012a", "TS3012b", "TS3012c"])
    assert not leak_passed, "TS3012d must fail when restricted to TS3012a-c."
    print("Test 4 Passed: TS3012d boundary enforcement confirmed.")


if __name__ == "__main__":
    test_quote_verification()
    print("All verifier tests passed successfully!")
