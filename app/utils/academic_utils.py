"""Academic utilities for CampusX — branch code derivation and institutional ID formatting.
Supports auto-generating branch-tagged IDs (STU-<BRANCH>-YYYY-XXX / FAC-<BRANCH>-YYYY-XXX).
"""
import re
from typing import Optional

BRANCH_CODE_MAP = {
    'artificial intelligence & machine learning': 'AIML',
    'artificial intelligence and machine learning': 'AIML',
    'ai & ml': 'AIML',
    'machine learning': 'AIML',
    'artificial intelligence': 'AI',
    'data science': 'DS',
    'computer science': 'CSE',
    'cyber security': 'CYS',
    'information security': 'CYS',
    'cyber': 'CYS',
    'information technology': 'IT',
    'civil': 'CE',
    'mechanical': 'ME',
    'electrical': 'EE',
    'electronics': 'ECE',
    'aerospace': 'AERO',
    'automobile': 'AUTO',
    'chemical': 'CHEM',
    'instrumentation': 'INST',
    'biotechnology': 'BIOTECH',
    'pharmaceutic': 'PHARM',
    'pharmacy': 'PHARM',
    'forensic': 'FS',
    'agriculture': 'AGRI',
    'architecture': 'ARCH',
}

BRANCH_DISPLAY_MAP = {
    'AIML': 'AI & ML',
    'AI': 'AI & ML',
    'DS': 'Data Science',
    'CSE': 'CSE',
    'CYS': 'Cyber Security',
    'IT': 'IT',
    'CE': 'Civil',
    'EE': 'Electrical',
    'ME': 'Mechanical',
}

APPROVED_DEPARTMENT_KEYWORDS = [
    "artificial intelligence",
    "data science",
    "computer science",
    "cyber",
    "information security",
    "information technology",
    "civil",
    "electrical",
    "mechanical"
]


def get_branch_code(department_name: Optional[str]) -> str:
    """Return a standard uppercase branch code (e.g. CSE, AIML, IT) from department name."""
    if not department_name:
        return 'GEN'
    name_lower = department_name.strip().lower()
    for key, code in BRANCH_CODE_MAP.items():
        if key in name_lower:
            return code
    # Clean words fallback
    words = [
        w for w in re.sub(r'[^a-zA-Z\s]', ' ', department_name).split()
        if w.lower() not in ('department', 'of', 'school', 'faculty', 'and', 'the', 'studies')
    ]
    if words:
        return ''.join(w[0] for w in words).upper()[:5]
    return 'GEN'


def get_branch_display_code(branch_code: Optional[str]) -> str:
    """Return human-readable display branch code (e.g. AI & ML for AIML, Data Science for DS)."""
    if not branch_code:
        return 'GEN'
    code_upper = branch_code.strip().upper()
    return BRANCH_DISPLAY_MAP.get(code_upper, branch_code)


def generate_institutional_id(role: str, branch_code: str, sequence_num: int = 1, year: int = 2026) -> str:
    """Generate institutional ID containing branch code.
    Format: STU-CSE-2026-001 or FAC-CSE-2026-001 or ADM-CSE-2026-001.
    """
    role_upper = (role or "STUDENT").strip().upper()
    prefix = "STU" if role_upper == "STUDENT" else "FAC" if role_upper == "FACULTY" else "ADM"
    clean_branch = re.sub(r'[^A-Z0-9]', '', (branch_code or "CSE").strip().upper()) or "GEN"
    return f"{prefix}-{clean_branch}-{year}-{sequence_num:03d}"
