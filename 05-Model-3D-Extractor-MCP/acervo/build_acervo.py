"""Monta o acervo de objetos do jogo (acervo/data/acervo.sqlite) em um comando.

    python 05-Model-3D-Extractor-MCP/acervo/build_acervo.py [--only tiles|textures|depth] [--game-dir PASTA] [--data-dir PASTA]

Sem --only: recria o banco do zero a partir de schema.sql e roda os três extratores
(extract_tiles: definições, geometria e atribuições de profundidade; extract_textures: sprites .pack -> PNG;
extract_depth: folhas media/depthmaps -> PNG por sprite).
Com --only: mantém o banco existente e refaz só aquela parte.
Nada é gravado na pasta do jogo. Se extract_textures faltar ou falhar, o acervo sai sem imagens, com aviso.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import extract_tiles  # noqa: E402

DEFAULT_GAME_DIR = extract_tiles.DEFAULT_GAME_DIR
DEFAULT_DATA_DIR = HERE / "data"
TABLES = ["tiles", "tile_props", "sprites", "geometry", "geometry_props", "depth_assignments", "depth_maps"]


def open_db(data_dir: Path, fresh: bool) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "acervo.sqlite"
    if fresh:
        for suffix in ("", "-wal", "-shm", "-journal"):
            p = Path(str(db) + suffix)
            if p.exists():
                p.unlink()
    conn = sqlite3.connect(db)
    conn.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    return conn


def set_meta(conn: sqlite3.Connection, **kv) -> None:
    conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", [(k, str(v)) for k, v in kv.items()])
    conn.commit()


def report(conn: sqlite3.Connection) -> dict:
    """Imprime e devolve contagens por tabela, por categoria e a cobertura."""
    out: dict = {}
    print("\n== Linhas por tabela ==")
    for t in TABLES:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        out[t] = n
        print(f"  {t:18s} {n:8d}")
    total = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    print("\n== Por categoria (tiles / com PNG / com geometria) ==")
    rows = conn.execute("""
        SELECT COALESCE(t.category,'?') c, COUNT(*) n,
               SUM(EXISTS(SELECT 1 FROM sprites s WHERE s.name = t.name)) png,
               SUM(EXISTS(SELECT 1 FROM geometry g WHERE g.name = t.name)) geo
        FROM tiles t GROUP BY c ORDER BY n DESC""").fetchall()
    out["por_categoria"] = {r[0]: r[1] for r in rows}
    for c, n, png, geo in rows:
        print(f"  {c:18s} {n:7d} {png or 0:8d} {geo or 0:8d}")
    png = conn.execute("SELECT COUNT(*) FROM tiles t WHERE EXISTS(SELECT 1 FROM sprites s WHERE s.name=t.name)").fetchone()[0]
    geo = conn.execute("SELECT COUNT(DISTINCT g.name) FROM geometry g JOIN tiles t ON t.name = g.name").fetchone()[0]
    gprops = conn.execute("SELECT COUNT(DISTINCT g.name) FROM geometry_props g JOIN tiles t ON t.name = g.name").fetchone()[0]
    defs = conn.execute("SELECT COUNT(*) FROM tiles WHERE source NOT IN ('tileGeometry.txt','tileDepthTextureAssignments.txt')").fetchone()[0]
    defs_png = conn.execute("""SELECT COUNT(*) FROM tiles t WHERE source NOT IN ('tileGeometry.txt','tileDepthTextureAssignments.txt')
                               AND EXISTS(SELECT 1 FROM sprites s WHERE s.name=t.name)""").fetchone()[0]
    print("\n== Cobertura ==")
    print(f"  tiles no catalogo:                        {total}")
    print(f"  tiles com PNG de sprite:                  {png} ({100 * png / max(total, 1):.1f}%)")
    print(f"  tiles das definicoes .tiles com PNG:      {defs_png}/{defs} ({100 * defs_png / max(defs, 1):.1f}%)")
    print(f"  tiles com geometria (formas):             {geo} ({100 * geo / max(total, 1):.1f}%)")
    print(f"  tiles com propriedades no tileGeometry:   {gprops}")
    out.update(tiles_com_png=png, tiles_defs=defs, tiles_defs_com_png=defs_png, tiles_com_geometria=geo)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=["tiles", "textures", "depth"], help="refaz só essa parte, mantendo o banco")
    ap.add_argument("--game-dir", default=os.environ.get("PZ_GAME_DIR", DEFAULT_GAME_DIR))
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--workers", type=int, default=None, help="processos do extract_textures e do extract_depth")
    a = ap.parse_args(argv)

    if not Path(a.game_dir).is_dir():
        print(f"ERRO: pasta do jogo nao encontrada: {a.game_dir}", file=sys.stderr)
        return 2
    t0 = time.time()
    data_dir = Path(a.data_dir)
    conn = open_db(data_dir, fresh=a.only is None)
    meta: dict = {}

    if a.only in (None, "tiles"):
        t = time.time()
        res = extract_tiles.extract(conn, a.game_dir)
        meta["tiles_seconds"] = round(time.time() - t, 1)
        meta["tiles_counts"] = {k: v for k, v in res.items() if k != "categories"}
        for w in res.get("warnings", []):
            print(f"AVISO: {w}", file=sys.stderr)
        print(f"tiles/geometria/profundidade: {meta['tiles_seconds']} s")

    if a.only in (None, "textures"):
        t = time.time()
        try:
            import extract_textures  # noqa: WPS433
            res = extract_textures.extract(conn, a.game_dir, data_dir, workers=a.workers)
            meta["textures_counts"] = {k: v for k, v in res.items() if isinstance(v, (int, float))}
            print(f"texturas: {round(time.time() - t, 1)} s, sprites={res.get('sprites')}")
        except ImportError as e:
            print(f"AVISO: extract_textures indisponivel ({e}); acervo sem imagens.", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - o acervo sem imagens ainda e util
            print(f"AVISO: extract_textures falhou ({type(e).__name__}: {e}); acervo sem imagens.", file=sys.stderr)
            traceback.print_exc()
        meta["textures_seconds"] = round(time.time() - t, 1)

    if a.only in (None, "depth"):
        t = time.time()
        try:
            import extract_depth  # noqa: WPS433
            res = extract_depth.extract(conn, a.game_dir, data_dir, workers=a.workers)
            meta["depth_counts"] = {k: v for k, v in res.items() if isinstance(v, (int, float))}
            for w in res.get("warnings", []):
                print(f"AVISO: {w}", file=sys.stderr)
            print(f"profundidade: {round(time.time() - t, 1)} s, mapas={res.get('depth_maps')}, "
                  f"quadros vazios={res.get('empty_frames')}")
            if res.get("colour_alignment"):
                print(f"  cor x profundidade: {res['colour_alignment']}")
        except ImportError as e:
            print(f"AVISO: extract_depth indisponivel ({e}); acervo sem mapas de profundidade.", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"AVISO: extract_depth falhou ({type(e).__name__}: {e}); acervo sem mapas de profundidade.", file=sys.stderr)
            traceback.print_exc()
        meta["depth_seconds"] = round(time.time() - t, 1)

    stats = report(conn)
    set_meta(conn,
             built_at=datetime.datetime.now().isoformat(timespec="seconds"),
             game_dir=a.game_dir,
             build_only=a.only or "all",
             build_seconds=round(time.time() - t0, 1),
             schema="schema.sql",
             **{f"last_{k}": v for k, v in meta.items()},
             **{f"count_{k}": v for k, v in stats.items() if isinstance(v, int)})
    conn.close()
    db = data_dir / "acervo.sqlite"
    print(f"\nPronto em {time.time() - t0:.1f} s. {db} ({db.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
