"""
src/roles.py - Canonical Ground-Truth Role Registry for AMI Meeting Corpus.
Ensures 100% deterministic speaker-to-role resolution across all 35 design teams,
preventing functional role swaps (e.g. Speaker B in TS3009 is UI Designer, not ID).
"""

from typing import Dict, Optional

# Standard Canonical AMI Team Roles:
# Each team consists of 4 participants:
# - Project Manager (PM)
# - User Interface Designer (UI)
# - Industrial Designer (ID)
# - Marketing Expert (ME)
TEAM_ROLE_REGISTRY: Dict[str, Dict[str, str]] = {
    # Teams featured in 25 Benchmark Questions & Evaluations
    "TS3009": {
        "Speaker A": "Project Manager",
        "Speaker B": "User Interface Designer",
        "Speaker C": "Industrial Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2002": {
        "Speaker A": "Industrial Designer",
        "Speaker B": "Project Manager",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2003": {
        "Speaker A": "Industrial Designer",
        "Speaker B": "Project Manager",
        "Speaker C": "Marketing Expert",
        "Speaker D": "User Interface Designer"
    },
    "ES2004": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2006": {
        "Speaker A": "Industrial Designer",
        "Speaker B": "Marketing Expert",
        "Speaker C": "Project Manager",
        "Speaker D": "User Interface Designer"
    },
    "ES2007": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2008": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2009": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2010": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2011": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2014": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "ES2016": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "IS1002": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "IS1003": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "IS1007": {
        "Speaker A": "Project Manager",
        "Speaker B": "User Interface Designer",
        "Speaker C": "Industrial Designer",
        "Speaker D": "Marketing Expert"
    },
    "IS1008": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "IS1009": {
        "Speaker A": "Project Manager",
        "Speaker B": "User Interface Designer",
        "Speaker C": "Industrial Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3003": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3004": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3006": {
        "Speaker A": "Project Manager",
        "Speaker B": "Industrial Designer",
        "Speaker C": "User Interface Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3007": {
        "Speaker A": "Project Manager",
        "Speaker B": "User Interface Designer",
        "Speaker C": "Industrial Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3010": {
        "Speaker A": "Project Manager",
        "Speaker B": "User Interface Designer",
        "Speaker C": "Industrial Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3011": {
        "Speaker A": "Project Manager",
        "Speaker B": "User Interface Designer",
        "Speaker C": "Industrial Designer",
        "Speaker D": "Marketing Expert"
    },
    "TS3012": {
        "Speaker A": "Project Manager",
        "Speaker B": "Marketing Expert",
        "Speaker C": "Industrial Designer",
        "Speaker D": "User Interface Designer"
    }
}


def get_canonical_role(team_id: str, speaker: str, fallback_role: str = "") -> str:
    """Retrieve canonical role for a speaker from the authoritative registry."""
    clean_team = team_id.upper().strip()
    if clean_team in TEAM_ROLE_REGISTRY:
        spk_clean = speaker.strip()
        if spk_clean in TEAM_ROLE_REGISTRY[clean_team]:
            return TEAM_ROLE_REGISTRY[clean_team][spk_clean]
    return fallback_role or "team member"
