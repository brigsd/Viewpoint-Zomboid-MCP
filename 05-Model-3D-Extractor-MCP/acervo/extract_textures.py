#!/usr/bin/env python3
"""Extrai os sprites de objetos do mundo (Project Zomboid B42) dos `.pack` para PNG.

Escreve em `acervo/data/` (fora do git):
  data/sprites/<tileset>/<nome_do_sprite>.png
  data/acervo.sqlite  (tabela `sprites`, esquema em `schema.sql`)

Somente leitura na pasta do jogo: os `.pack` são abertos com `rb`.

Formato `.pack` (verificado nos 24 arquivos do B42.21; inteiros little-endian de 32 bits,
strings = int32 comprimento + bytes UTF-8):

  [ "PZPK" int32 versao ]            # so nas versoes >= 1; sem isso e a versao 0
  int32 n_paginas
  repete n_paginas vezes:
      string nome_da_pagina          # ex. "Tiles2x0"
      int32  n_entradas
      int32  alpha                   # 1 = PNG com canal alpha
      repete n_entradas vezes:
          string nome                # nome do sprite, ex. "furniture_bedding_01_0"
          int32 x, y, w, h           # recorte dentro do atlas PNG (origem no canto superior esquerdo)
          int32 ox, oy               # posicao do recorte dentro do quadro original
          int32 fw, fh               # tamanho do quadro original (antes de cortar a transparencia)
      versao >= 1: int32 tamanho_png + bytes do PNG
      versao 0   : bytes do PNG (sem tamanho: termina no chunk IEND) + 0xDEADBEEF (marcador)

Uso:
  python extract_textures.py [--game-dir DIR] [--data-dir DIR] [--workers N] [--only Tiles2x.pack ...]
"""
from __future__ import annotations

import argparse
import io
import mmap
import multiprocessing as mp
import os
import re
import sqlite3
import struct
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
DEFAULT_DATA_DIR = HERE / "data"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
DEADBEEF = 0xDEADBEEF

# Packs com sprites de objetos/tiles do mundo, em ordem de prioridade (o primeiro que tiver o nome
# vence). 2x antes de 1x para guardar a melhor resolucao. valor = escala (1 ou 2).
TILE_PACKS: dict[str, int] = {
    "Tiles2x.pack": 2,
    "Tiles2x.floor.pack": 2,
    "B42ChunkCaching2x.pack": 2,
    "B42ChunkCaching2x.floor.pack": 2,
    "Overlays2x.pack": 2,
    "Overlays2x.floor.pack": 2,
    "Clock2x.pack": 2,
    "JumboTreesBigs2x.pack": 2,
    "JumboTrees2x.pack": 2,
    "blair_temp.pack": 2,
    "Tiles1x.pack": 1,
    "Tiles1x.floor.pack": 1,
    "Overlays1x.pack": 1,
    "JumboTrees1x.pack": 1,
    "ApCom.pack": 1,
}
# Todo o resto em texturepacks/ e UI/icones/efeitos/mecanica/depth e e so contado, nao extraido.

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# --------------------------------------------------------------------------- leitura do .pack

class PackError(Exception):
    pass


def _png_end(buf, p: int) -> int:
    """Posicao logo apos o IEND do PNG que comeca em p."""
    if bytes(buf[p:p + 8]) != PNG_SIG:
        raise PackError(f"PNG esperado no offset {p}")
    q = p + 8
    n = len(buf)
    while q + 12 <= n:
        ln, = struct.unpack_from(">I", buf, q)
        kind = bytes(buf[q + 4:q + 8])
        q += 12 + ln
        if kind == b"IEND":
            return q
    raise PackError("PNG sem IEND")


def scan_pack(path: str | os.PathLike):
    """Le so os cabecalhos. Devolve (versao, [pagina, ...]); pagina =
    dict(name, alpha, png_off, png_len, entries=[(nome, x, y, w, h, ox, oy, fw, fh), ...])."""
    with open(path, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        if size == 0:
            return 0, []
        m = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        pos = 0
        ver = 0
        if m[:4] == b"PZPK":
            ver, = struct.unpack_from("<i", m, 4)
            pos = 8

        def i32():
            nonlocal pos
            v, = struct.unpack_from("<i", m, pos)
            pos += 4
            return v

        def string():
            nonlocal pos
            n = i32()
            if n < 0 or pos + n > size:
                raise PackError(f"string invalida em {pos}")
            v = bytes(m[pos:pos + n]).decode("utf-8", "replace")
            pos += n
            return v

        pages = []
        n_pages = i32()
        if not 0 <= n_pages < 100000:
            raise PackError(f"numero de paginas absurdo: {n_pages}")
        for _ in range(n_pages):
            name = string()
            count = i32()
            alpha = i32()
            entries = []
            for _ in range(count):
                nm = string()
                vals = struct.unpack_from("<8i", m, pos)
                pos += 32
                entries.append((nm, *vals))
            if ver >= 1:
                ln = i32()
                png_off = pos
                if bytes(m[png_off:png_off + 8]) != PNG_SIG:
                    raise PackError(f"PNG esperado no offset {png_off}")
                pos += ln
            else:
                png_off = pos
                pos = _png_end(m, pos)
                ln = pos - png_off
                if pos + 4 <= size and struct.unpack_from("<I", m, pos)[0] == DEADBEEF:
                    pos += 4
            pages.append({"name": name, "alpha": alpha, "png_off": png_off, "png_len": ln,
                          "entries": entries})
        return ver, pages
    finally:
        m.close()


def tileset_of(name: str) -> str:
    """'furniture_bedding_01_0' -> 'furniture_bedding_01'."""
    m = re.match(r"^(.*?)_\d+$", name)
    return m.group(1) if m else name


def safe(s: str) -> str:
    return _INVALID.sub("_", s)


def sprite_relpath(name: str) -> str:
    return f"sprites/{safe(tileset_of(name))}/{safe(name)}.png"


# --------------------------------------------------------------------------- extracao

def _png_size(path: Path):
    try:
        with open(path, "rb") as f:
            h = f.read(24)
        if h[:8] == PNG_SIG and h[12:16] == b"IHDR":
            return struct.unpack(">II", h[16:24])
    except OSError:
        pass
    return None


def _extract_page(task):
    """Worker: decodifica o atlas de uma pagina e grava os recortes escolhidos."""
    from PIL import Image
    pack_path, png_off, png_len, data_dir, items = task
    data_dir = Path(data_dir)
    todo = []
    skipped = 0
    for it in items:                       # it = (rel, x, y, w, h)
        rel, x, y, w, h = it
        if _png_size(data_dir / rel) == (w, h):
            skipped += 1
        else:
            todo.append(it)
    written = 0
    nbytes = 0
    if todo:
        with open(pack_path, "rb") as f:
            f.seek(png_off)
            blob = f.read(png_len)
        atlas = Image.open(io.BytesIO(blob))
        atlas.load()
        if atlas.mode != "RGBA":
            atlas = atlas.convert("RGBA")
        for rel, x, y, w, h in todo:
            dest = data_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            atlas.crop((x, y, x + w, y + h)).save(tmp, format="PNG", compress_level=4)
            os.replace(tmp, dest)
            written += 1
            nbytes += dest.stat().st_size
    return skipped, written, nbytes


def free_bytes(path: Path) -> int:
    import shutil
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free


def _init_db(data_dir: Path) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "acervo.sqlite")
    conn.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    return conn


def plan(game_dir: str | os.PathLike, only: list[str] | None = None):
    """Escolhe, para cada nome de sprite, o pack vencedor. Devolve (winners, pages_info, ignored, stats).

    winners: nome -> (pack, scale, page_index, entry); pages_info: {(pack, page_idx): page}."""
    tp = Path(game_dir) / "media" / "texturepacks"
    if not tp.is_dir():
        raise FileNotFoundError(f"pasta de texturepacks nao encontrada: {tp}")
    present = sorted(p.name for p in tp.iterdir() if p.is_file() and p.suffix == ".pack")
    ordered = [p for p in TILE_PACKS if p in present and (not only or p in only)]
    winners: dict[str, tuple] = {}
    pages_info: dict[tuple, dict] = {}
    stats = {"entries_seen": 0, "duplicates_dropped": 0, "empty_dropped": 0}
    for pack in ordered:
        _, pages = scan_pack(tp / pack)
        for pi, page in enumerate(pages):
            pages_info[(pack, pi)] = page
            for e in page["entries"]:
                stats["entries_seen"] += 1
                name, x, y, w, h = e[0], e[1], e[2], e[3], e[4]
                if w <= 0 or h <= 0:
                    stats["empty_dropped"] += 1
                    continue
                if name in winners:
                    stats["duplicates_dropped"] += 1
                    continue
                winners[name] = (pack, TILE_PACKS[pack], pi, e)
    ignored = {}
    for pack in present:
        if pack not in TILE_PACKS:
            try:
                _, pages = scan_pack(tp / pack)
                ignored[pack] = sum(len(p["entries"]) for p in pages)
            except (PackError, struct.error, OSError):
                ignored[pack] = -1         # nao e um .pack legivel (ex. .backup nao entra aqui)
    return tp, winners, pages_info, ignored, stats


def extract(conn: sqlite3.Connection, game_dir, data_dir, workers: int | None = None,
            only: list[str] | None = None, max_gb: float = 5.0, progress=None) -> dict:
    """Extrai os sprites dos packs de tiles para `data_dir/sprites` e grava a tabela `sprites`.

    Devolve um dict de contagens. Nunca escreve em `game_dir`."""
    t0 = time.time()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    conn.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    tp, winners, pages_info, ignored, stats = plan(game_dir, only)

    max_bytes = int(max_gb * (1 << 30))
    if free_bytes(data_dir) < max_bytes + (1 << 30):
        raise OSError(f"espaco livre insuficiente em {data_dir} para o limite de {max_gb} GB")

    # tarefas: uma por pagina, so com os sprites que venceram naquela pagina
    per_page: dict[tuple, list] = {}
    rows = []
    for name, (pack, scale, pi, e) in winners.items():
        _, x, y, w, h, ox, oy, fw, fh = e
        rel = sprite_relpath(name)
        per_page.setdefault((pack, pi), []).append((rel, x, y, w, h))
        rows.append((name, pack, pages_info[(pack, pi)]["name"], rel, w, h, ox, oy, fw, fh, scale))
    tasks = []
    for (pack, pi), items in per_page.items():
        pg = pages_info[(pack, pi)]
        tasks.append((str(tp / pack), pg["png_off"], pg["png_len"], str(data_dir), items))
    # paginas grandes primeiro
    tasks.sort(key=lambda t: -t[2])

    skipped = written = nbytes = 0
    workers = workers or max(1, min(8, (os.cpu_count() or 2)))
    if workers == 1 or len(tasks) <= 1:
        results = (_extract_page(t) for t in tasks)
        for n, (s, w_, b) in enumerate(results, 1):
            skipped += s; written += w_; nbytes += b
            if nbytes > max_bytes:
                raise OSError(f"limite de {max_gb} GB excedido; extracao interrompida")
            if progress:
                progress(n, len(tasks))
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            futs = [ex.submit(_extract_page, t) for t in tasks]
            for n, fu in enumerate(as_completed(futs), 1):
                s, w_, b = fu.result()
                skipped += s; written += w_; nbytes += b
                if nbytes > max_bytes:
                    for f in futs:
                        f.cancel()
                    raise OSError(f"limite de {max_gb} GB excedido; extracao interrompida")
                if progress:
                    progress(n, len(tasks))

    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO sprites(name, pack, page, png, width, height, offset_x, offset_y, "
            "frame_w, frame_h, scale) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    total_png = sum(f.stat().st_size for f in (data_dir / "sprites").rglob("*.png"))
    by_pack: dict[str, int] = {}
    by_scale: dict[int, int] = {}
    for r in rows:
        by_pack[r[1]] = by_pack.get(r[1], 0) + 1
        by_scale[r[10]] = by_scale.get(r[10], 0) + 1
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('textures_extracted_at', ?)",
                     (time.strftime("%Y-%m-%dT%H:%M:%S"),))
    return {
        "sprites": len(rows),
        "written": written,
        "skipped_existing": skipped,
        "bytes_written": nbytes,
        "png_bytes_total": total_png,
        "by_pack": by_pack,
        "by_scale": by_scale,
        "pages": len(tasks),
        "ignored_packs": ignored,
        "seconds": round(time.time() - t0, 1),
        **stats,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game-dir", default=os.environ.get("PZ_GAME_DIR", DEFAULT_GAME_DIR))
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--only", nargs="*", help="extrai so estes .pack (ex. Tiles1x.floor.pack)")
    ap.add_argument("--max-gb", type=float, default=5.0, help="aborta se os PNGs gravados passarem disto")
    a = ap.parse_args(argv)

    def prog(n, total):
        if n % 20 == 0 or n == total:
            print(f"  paginas {n}/{total}", file=sys.stderr, flush=True)

    conn = _init_db(Path(a.data_dir))
    try:
        res = extract(conn, a.game_dir, a.data_dir, workers=a.workers, only=a.only,
                      max_gb=a.max_gb, progress=prog)
    finally:
        conn.close()
    print(f"sprites no catalogo: {res['sprites']}  (gravados {res['written']}, ja existiam {res['skipped_existing']})")
    print(f"por escala: {res['by_scale']}")
    for k, v in res["by_pack"].items():
        print(f"  {k}: {v}")
    print(f"descartados: duplicados {res['duplicates_dropped']}, vazios {res['empty_dropped']}")
    print(f"PNGs em disco: {res['png_bytes_total'] / 1e6:.1f} MB; tempo {res['seconds']} s")
    print("packs ignorados (UI/icones/efeitos): " + ", ".join(f"{k}={v}" for k, v in res["ignored_packs"].items()))
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
