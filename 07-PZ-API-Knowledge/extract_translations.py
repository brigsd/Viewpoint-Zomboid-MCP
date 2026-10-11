"""Extrator de traducoes: media/lua/shared/Translate/<LANG>/*.json (EN e PTBR).

So EN e PTBR entram no banco para ele ficar pequeno. Arquivos .txt no formato
antigo (`Chave = "valor",`) tambem sao lidos, quando existirem nessas pastas.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

LANGS = ("EN", "PTBR")
_TXT_LINE = re.compile(r'^\s*([^\s=]+)\s*=\s*"(.*)"\s*,?\s*$')
_SKIP_TXT = {"language.txt", "credits.txt"}


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace").lstrip("﻿")


def extract(conn: sqlite3.Connection, game_dir) -> dict:
    game = Path(game_dir)
    root = game / "media" / "lua" / "shared" / "Translate"
    counts: dict[str, int] = {}
    rows: list[tuple] = []

    if root.is_dir():
        for lang_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            lang = lang_dir.name.upper()
            if lang not in LANGS:
                continue
            for path in sorted(lang_dir.iterdir()):
                if not path.is_file():
                    continue
                rel = path.relative_to(game).as_posix()
                suffix = path.suffix.lower()
                if suffix == ".json":
                    try:
                        data = json.loads(_read_text(path))
                    except (json.JSONDecodeError, OSError):
                        continue
                    if not isinstance(data, dict):
                        continue
                    category = path.stem
                    for key, value in data.items():
                        if not isinstance(value, str):
                            value = json.dumps(value, ensure_ascii=False)
                        rows.append((lang, category, str(key), value, rel))
                elif suffix == ".txt" and path.name.lower() not in _SKIP_TXT:
                    # ex.: ContextMenu_EN.txt -> categoria ContextMenu
                    category = re.sub(r"_" + re.escape(lang) + r"$", "", path.stem, flags=re.I)
                    for line in _read_text(path).splitlines():
                        m = _TXT_LINE.match(line)
                        if m:
                            rows.append((lang, category, m.group(1), m.group(2), rel))

    conn.executemany(
        "INSERT INTO translations(lang, category, key, value, file) VALUES (?,?,?,?,?)", rows
    )
    for r in rows:
        counts[r[0]] = counts.get(r[0], 0) + 1
    out = {"translations": len(rows)}
    for lang, n in sorted(counts.items()):
        out[f"translations_{lang}"] = n
    out["translation_categories"] = len({(r[0], r[1]) for r in rows})
    return out
