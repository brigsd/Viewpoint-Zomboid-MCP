#!/usr/bin/env python3
"""Monta data/pz_api.sqlite a partir da instalacao do Project Zomboid (somente leitura).

Uso:
    python 07-PZ-API-Knowledge/build_index.py [--game-dir PATH] [--out PATH]

Passos: recria o banco, aplica schema.sql, roda cada extrator
(`extract(conn, game_dir) -> dict`), preenche symbols_fts, grava `meta` e
imprime um resumo. A pasta do jogo nunca e alterada.
"""
from __future__ import annotations

import argparse
import datetime
import importlib
import os
import re
import sqlite3
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
DEFAULT_OUT = HERE / "data" / "pz_api.sqlite"
FALLBACK_VERSION = "42.21"

# (modulo, obrigatorio). extract_java e escrito em paralelo por outro agente:
# se faltar ou falhar, so avisa.
EXTRACTORS = [
    ("extract_java", False),
    ("extract_lua", True),
    ("extract_scripts", True),
    ("extract_translations", True),
]
TABLES = ["symbols", "usages", "script_blocks", "script_fields", "translations"]


def detect_game_version(game_dir: Path) -> str:
    """Tenta ler a versao do jogo; senao devolve 42.21."""
    candidates = [
        game_dir / "version.txt",
        game_dir / "media" / "version.txt",
    ]
    for c in candidates:
        try:
            m = re.search(r"\b(4\d\.\d+(?:\.\d+)?)\b", c.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m.group(1)
        except OSError:
            pass
    return FALLBACK_VERSION


def detect_steam_buildid(game_dir: Path) -> str | None:
    manifest = game_dir.parent.parent / "appmanifest_108600.acf"
    try:
        m = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text(encoding="utf-8", errors="replace"))
        return m.group(1) if m else None
    except OSError:
        return None


def build(game_dir: Path, out: Path, game_version: str | None = None) -> dict:
    t0 = time.time()
    out.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-journal", "-wal", "-shm"):
        p = Path(str(out) + suffix)
        if p.exists():
            p.unlink()

    conn = sqlite3.connect(out)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    conn.commit()

    results: dict[str, dict] = {}
    warnings: list[str] = []
    for mod_name, required in EXTRACTORS:
        ts = time.time()
        try:
            mod = importlib.import_module(mod_name)
            res = mod.extract(conn, str(game_dir))
            conn.commit()
            results[mod_name] = dict(res or {})
            results[mod_name]["_seconds"] = round(time.time() - ts, 1)
        except ModuleNotFoundError as e:
            conn.rollback()
            if e.name == mod_name:
                warnings.append(f"{mod_name}: modulo ausente, ignorado ({e})")
            else:
                warnings.append(f"{mod_name}: falhou por dependencia ausente: {e}")
        except Exception as e:  # noqa: BLE001 - queremos seguir adiante
            conn.rollback()
            warnings.append(f"{mod_name}: falhou ({type(e).__name__}: {e})")
            if os.environ.get("PZ_DEBUG"):
                traceback.print_exc(file=sys.stderr)
        if mod_name not in results and required:
            warnings.append(f"{mod_name}: era obrigatorio; o indice ficara incompleto")

    # busca textual sobre os simbolos
    conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('optimize')")

    # meta
    version = game_version or detect_game_version(game_dir)
    meta = {
        "game_version": version,
        "built_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    build_id = detect_steam_buildid(game_dir)
    if build_id:
        meta["steam_buildid"] = build_id
    counts: dict[str, int] = {}
    for t in TABLES:
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        meta[f"count_{t}"] = str(counts[t])
    for kind, n in conn.execute("SELECT kind, COUNT(*) FROM symbols GROUP BY kind ORDER BY kind"):
        meta[f"count_symbols_{kind}"] = str(n)
    conn.executemany("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", meta.items())
    conn.commit()
    kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM symbols GROUP BY kind"))
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()

    return {
        "results": results,
        "warnings": warnings,
        "counts": counts,
        "kinds": kinds,
        "version": version,
        "seconds": time.time() - t0,
        "size": out.stat().st_size,
    }


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Monta o indice SQLite da API do Project Zomboid.")
    ap.add_argument("--game-dir", default=os.environ.get("PZ_GAME_DIR", DEFAULT_GAME_DIR),
                    help="pasta de instalacao do jogo (somente leitura)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="banco de saida")
    ap.add_argument("--game-version", default=None, help="forca game_version no meta")
    args = ap.parse_args(argv)

    game_dir = Path(args.game_dir)
    if not (game_dir / "media").is_dir():
        print(f"ERRO: {game_dir} nao parece uma instalacao do Project Zomboid (sem media/).",
              file=sys.stderr)
        return 2
    out = Path(args.out)

    print(f"Jogo : {game_dir}")
    print(f"Saida: {out}")
    r = build(game_dir, out, args.game_version)

    print()
    for mod, res in r["results"].items():
        detail = ", ".join(f"{k}={v}" for k, v in res.items() if not k.startswith("_"))
        print(f"  {mod:<22} {res.get('_seconds', 0):>6}s  {detail}")
    for w in r["warnings"]:
        print(f"  AVISO: {w}")
    print()
    print(f"game_version: {r['version']}")
    for t, n in r["counts"].items():
        print(f"  {t:<14} {n:>9}")
    if r["kinds"]:
        print("  symbols por kind: " + ", ".join(f"{k}={v}" for k, v in sorted(r["kinds"].items())))
    print(f"Tempo: {r['seconds']:.1f}s   Banco: {r['size'] / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
