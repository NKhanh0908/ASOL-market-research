from __future__ import annotations

import re
from typing import Any

_KNOWN_SUBGENRES = [
    'Puzzle',
    'Simulation',
    'Arcade',
    'Action',
    'Card',
    'Board',
    'Sports',
    'Strategy',
    'Trivia',
    'Word',
    'Role Playing',
    'Adventure',
    'Racing',
    'Music',
    'Casino',
    'Family',
]

_GOOGLE_PLAY_SUBGENRES = {
    "GAME_PUZZLE": "Puzzle",
    "GAME_SIMULATION": "Simulation",
    "GAME_ARCADE": "Arcade",
    "GAME_ACTION": "Action",
    "GAME_CARD": "Card",
    "GAME_BOARD": "Board",
    "GAME_SPORTS": "Sports",
    "GAME_STRATEGY": "Strategy",
    "GAME_TRIVIA": "Trivia",
    "GAME_WORD": "Word",
    "GAME_ROLE_PLAYING": "Role Playing",
    "GAME_ADVENTURE": "Adventure",
    "GAME_RACING": "Racing",
    "GAME_MUSIC": "Music",
    "GAME_CASUAL": "Casual",
    "GAME_CASINO": "Casino",
    "GAME_FAMILY": "Family",
}


def classify_google_play_subgenre(genres: list[dict[str, Any]]) -> str | None:
    for genre in genres:
        code = genre.get("code")
        if code in _GOOGLE_PLAY_SUBGENRES:
            return _GOOGLE_PLAY_SUBGENRES[code]
        label = str(genre.get("label") or "").strip()
        if label:
            inferred = classify_subgenre([label])
            if inferred != "Casual" or label.casefold() == "casual":
                return inferred
            return label
    return None

_MECHANIC_KEYWORDS: dict[str, list[str]] = {
    'Match-3': [
        'match 3',
        'match-3',
        'tile match',
        'match 3d',
        'triple match',
        'match three',
        'match-three',
        'swap and match',
        'matching tiles',
        'match items',
        'match tiles',
    ],
    'Merge': [
        'merge',
        'merging',
        'merge puzzle',
        'merge items',
        'merge games',
        'merge and',
    ],
    'Sort': [
        'water sort',
        'color sort',
        'goods sort',
        'sort puzzle',
        'sorting',
        'sort items',
        'ball sort',
        'sort the',
        'sort colored',
        'sort color',
        'sort',
    ],
    'Idle': [
        'idle',
        'tycoon',
        'afk',
        'incremental',
        'auto clicker',
        'clicker',
        'idle game',
        'idle tycoon',
        'farm tycoon',
    ],
    'Runner': [
        'endless runner',
        'runner',
        'parkour',
        'subway',
        'rush',
        'dash',
        'dodge trains',
        'run and jump',
    ],
    'Card / Board': [
        'solitaire',
        'mahjong',
        'sudoku',
        'chess',
        'tripeaks',
        'klondike',
        'spider solitaire',
        'card game',
        'board game',
        'domino',
        'checkers',
        'cards',
        'card',
    ],
    'Word / Trivia': [
        'crossword',
        'word search',
        'word puzzle',
        'trivia',
        'quiz',
        'spelling',
        'anagram',
        'wordscapes',
        'connect letters',
        'guess the',
        'word',
    ],
    'Drawing': [
        'color by number',
        'coloring',
        'paint by number',
        'paint',
        'drawing',
        'sketch',
        'draw puzzle',
        'painting puzzles',
        'painting',
    ],
}


def classify_subgenre(genres: list[Any]) -> str:
    if not genres:
        return 'Casual'
    for g in genres:
        if isinstance(g, dict):
            name = g.get('label') or g.get('term') or g.get('name') or ''
        elif isinstance(g, str):
            name = g
        else:
            name = str(g)

        if not name or name in ('Games', 'Casual'):
            continue
        for known in _KNOWN_SUBGENRES:
            if known.lower() == name.lower() or known.lower() in name.lower():
                return known
    return 'Casual'


def classify_mechanic(title: str, description: str) -> dict[str, Any]:
    title_text = (title or '').lower()
    desc_text = (description or '').lower()

    best_mechanic = 'Other'
    best_score = 0
    matched_evidences: list[str] = []

    for mechanic, keywords in _MECHANIC_KEYWORDS.items():
        score = 0
        evidences = []
        for kw in sorted(keywords, key=len, reverse=True):
            pattern = r'\b' + re.escape(kw) + r'\b' if len(kw) <= 5 else re.escape(kw)
            title_hits = len(re.findall(pattern, title_text))
            desc_hits = len(re.findall(pattern, desc_text))
            if title_hits > 0:
                score += title_hits * 3
                evidences.append(f'title: "{kw}"')
            if desc_hits > 0:
                score += desc_hits
                evidences.append(f'desc: "{kw}"')

        if score > best_score:
            best_score = score
            best_mechanic = mechanic
            matched_evidences = evidences

    if best_score > 0:
        confidence = 'high' if best_score >= 3 else 'medium'
        evidence_str = ', '.join(matched_evidences[:3])
        return {
            'mechanic': best_mechanic,
            'confidence': confidence,
            'evidence': evidence_str,
        }

    return {
        'mechanic': 'Other',
        'confidence': 'unknown',
        'evidence': None,
    }


def classify_app(
    genres: list[str], title: str, description: str
) -> dict[str, Any]:
    subgenre = classify_subgenre(genres)
    mech_result = classify_mechanic(title, description)
    return {
        'subgenre': subgenre,
        'mechanic': mech_result['mechanic'],
        'confidence': mech_result['confidence'],
        'evidence': mech_result['evidence'],
    }
