#!/usr/bin/env python3
"""Corta as folhas de profundidade do jogo (media/depthmaps/DEPTH_*.png) em PNGs por sprite.

Escreve em `acervo/data/` (fora do git):
  data/depth/<tileset>/<nome>.png     quadro 128x256, modo LA (L = valor de profundidade, A = 255 onde ha profundidade)
  data/acervo.sqlite                  tabela `depth_maps` (esquema em `schema.sql`)

Somente leitura na pasta do jogo.

Formato das folhas (verificado nas 218 `DEPTH_*.png` do B42.21):
  * 1024 px de largura = 8 colunas de quadros 128x256 (2x); altura = N linhas de 256 px.
    Duas folhas avulsas (`DEPTH_billboard`, `DEPTH_whole_tile`) tem 128x256 = 1 quadro.
  * indice do quadro = linha * colunas + coluna, igual a grade do tileset: `DEPTH_<tileset>.png`, quadro i
    corresponde ao tile `<tileset>_<i>`.
  * modos: P (paleta, 8 bits), LA, L. Em P o indice 0 e transparente (tRNS) e o indice i>=1 tem cinza 256-i
    (paleta de 255 a 1). Em LA o L e o cinza e o A e 0/255. Aqui tudo vira (L = cinza, A = mascara).

Codificacao do valor (medida contra a geometria do tileGeometry; ver align_check.py):
  cinza = 190 - K*(X+Z) - (2/3)*H*Y      [X,Z,Y em 1/10000 de tile; K = 0,0064; H = 0,007838]
  ou seja, e linear na distancia ao longo da direcao da camera (0,612; 0,5; 0,612): MENOR = MAIS PERTO da camera
  (~104 niveis por tile de profundidade). O quadro inteiro e um "volume" liso (rampa por face), nao a textura:
  a silhueta bate com a geometria do tile, nao com os pixels coloridos do sprite.
  Em paleta: indice = 256 - cinza (indice maior = mais perto).

Uso:
  python extract_depth.py [--game-dir DIR] [--data-dir DIR] [--workers N]
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
FRAME_W, FRAME_H = 128, 256
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')      # igual a extract_textures._INVALID

# Constantes de projecao/profundidade (2x). Ver align_check.py para a medicao.
UNIT = 10000.0                      # 1 tile = 10000 unidades do tileGeometry
K_PX = 128 / 2 / UNIT               # px de tela em x por unidade de X (ou Z): diamante de 128 px de largura
H_PX = 0.8660254 * 128 / 2 ** 0.5 / UNIT   # px de tela por unidade de Y (cos 30 graus * lado do tile em px)
DEPTH_C = 190.0                     # cinza no centro do tile, no chao
DEPTH_COEF = (-K_PX, -2.0 / 3.0 * H_PX, -K_PX)   # (X, Y, Z) em niveis de cinza por unidade


def safe(s: str) -> str:
    return _INVALID.sub("_", s)


def depth_relpath(tileset: str, name: str) -> str:
    return f"depth/{safe(tileset)}/{safe(name)}.png"


def gray_from_world(x, y, z):
    """Valor de cinza esperado de um ponto (X, Y, Z) do tileGeometry (aceita arrays numpy)."""
    return DEPTH_C + DEPTH_COEF[0] * x + DEPTH_COEF[1] * y + DEPTH_COEF[2] * z


def decode_sheet(path):
    """Le uma folha e devolve (cinza uint8 HxW, mascara bool HxW). Qualquer modo do jogo (P, LA, L, RGBA)."""
    import numpy as np
    from PIL import Image

    im = Image.open(path)
    im.load()
    mode = im.mode
    if mode == "P":
        a = np.asarray(im)
        pal = np.zeros(256, np.uint8)
        raw = im.getpalette() or []
        trip = np.asarray(raw[:768], np.uint8).reshape(-1, 3)
        pal[: len(trip)] = trip[:, 0]
        trans = im.info.get("transparency")
        if isinstance(trans, int):
            mask = a != trans
        elif isinstance(trans, (bytes, bytearray)):
            tab = np.full(256, 255, np.uint8)
            tab[: len(trans)] = np.frombuffer(bytes(trans), np.uint8)
            mask = tab[a] > 0
        else:
            mask = a != 0
        return pal[a], mask
    if mode == "LA":
        a = np.asarray(im)
        return a[..., 0].copy(), a[..., 1] > 0
    if mode == "L":
        a = np.asarray(im)
        return a.copy(), a > 0
    a = np.asarray(im.convert("RGBA"))
    return a[..., 0].copy(), a[..., 3] > 0


def _cut_sheet(task):
    """Worker: corta uma folha. Devolve (sheet, linhas, quadros_vazios, aviso)."""
    import numpy as np
    from PIL import Image

    path, tileset, data_dir = task
    data_dir = Path(data_dir)
    sheet = os.path.basename(path)
    gray, mask = decode_sheet(path)
    h, w = gray.shape
    cols, rows = w // FRAME_W, h // FRAME_H
    warn = None
    if cols == 0 or rows == 0:
        return sheet, [], 0, f"{sheet}: {w}x{h} menor que um quadro {FRAME_W}x{FRAME_H}"
    if w % FRAME_W or h % FRAME_H:
        warn = f"{sheet}: {w}x{h} nao e multiplo de {FRAME_W}x{FRAME_H}; sobra ignorada"
    out_rows, empty = [], 0
    for r in range(rows):
        for c in range(cols):
            sl = (slice(r * FRAME_H, (r + 1) * FRAME_H), slice(c * FRAME_W, (c + 1) * FRAME_W))
            m = mask[sl]
            nz = int(m.sum())
            if nz == 0:
                empty += 1
                continue
            idx = r * cols + c
            name = f"{tileset}_{idx}"
            rel = depth_relpath(tileset, name)
            dest = data_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            la = np.dstack([np.where(m, gray[sl], 0).astype(np.uint8), (m * 255).astype(np.uint8)])
            tmp = dest.with_suffix(".tmp")
            Image.fromarray(la, "LA").save(tmp, format="PNG", compress_level=4)
            os.replace(tmp, dest)
            out_rows.append((name, rel, sheet, c, r, nz))
    return sheet, out_rows, empty, warn


def list_sheets(game_dir):
    dm = Path(game_dir) / "media" / "depthmaps"
    if not dm.is_dir():
        raise FileNotFoundError(f"pasta de mapas de profundidade nao encontrada: {dm}")
    out = []
    for p in sorted(dm.glob("DEPTH_*.png")):
        out.append((str(p), p.stem[len("DEPTH_"):]))
    return out


def extract(conn: sqlite3.Connection, game_dir, data_dir, workers: int | None = None,
            check_sample: int = 1500, progress=None) -> dict:
    """Corta todas as folhas para `data_dir/depth` e preenche `depth_maps`. Nunca escreve em `game_dir`."""
    t0 = time.time()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    schema = (HERE / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    if "depth_png" not in {r[1] for r in conn.execute("PRAGMA table_info(objects)")}:
        conn.execute("DROP VIEW IF EXISTS objects")     # banco criado com o esquema antigo (visao sem depth_png)
        conn.executescript(schema)
    sheets = list_sheets(game_dir)
    tasks = [(p, ts, str(data_dir)) for p, ts in sheets]
    tasks.sort(key=lambda t: -os.path.getsize(t[0]))

    rows: list[tuple] = []
    warnings: list[str] = []
    empty = 0
    workers = workers or max(1, min(8, (os.cpu_count() or 2)))
    if workers == 1 or len(tasks) <= 1:
        results = (_cut_sheet(t) for t in tasks)
        for n, (sheet, r, e, w) in enumerate(results, 1):
            rows.extend(r); empty += e
            if w:
                warnings.append(w)
            if progress:
                progress(n, len(tasks))
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            futs = [ex.submit(_cut_sheet, t) for t in tasks]
            for n, fu in enumerate(as_completed(futs), 1):
                sheet, r, e, w = fu.result()
                rows.extend(r); empty += e
                if w:
                    warnings.append(w)
                if progress:
                    progress(n, len(tasks))

    with conn:
        conn.execute("DELETE FROM depth_maps")
        conn.executemany(
            "INSERT OR REPLACE INTO depth_maps(name, png, sheet, col, row, nonzero) VALUES (?,?,?,?,?,?)", rows)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('depth_extracted_at', ?)",
                     (time.strftime("%Y-%m-%dT%H:%M:%S"),))

    names = {r[0] for r in rows}
    in_tiles = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    matched = sum(1 for (n,) in conn.execute("SELECT name FROM tiles") if n in names)
    res = {
        "sheets": len(sheets),
        "depth_maps": len(rows),
        "empty_frames": empty,
        "tiles_with_own_depth": matched if in_tiles else 0,
        "depth_without_tile": len(names) - matched if in_tiles else 0,
        "warnings": warnings,
    }
    if check_sample:
        try:
            res["colour_alignment"] = check_colour_alignment(conn, data_dir, limit=check_sample)
        except Exception as e:  # noqa: BLE001 - a conferencia nao pode derrubar a extracao
            warnings.append(f"conferencia cor x profundidade falhou: {type(e).__name__}: {e}")
    res["seconds"] = round(time.time() - t0, 1)
    return res


# --------------------------------------------------------------------------- conferencia cor x profundidade

def colour_in_frame(row, data_dir):
    """Mascara booleana 256x128 dos pixels opacos do sprite colorido, no quadro cheio (normalizado para 2x).

    row = (png, width, height, offset_x, offset_y, scale, frame_w, frame_h). Devolve None se o quadro
    normalizado nao for 128x256."""
    import numpy as np
    from PIL import Image

    png, w, h, ox, oy, scale, fw, fh = row
    scale = scale or 2
    f = 2 // scale if scale in (1, 2) else 1
    if (fw * f, fh * f) != (FRAME_W, FRAME_H):
        return None
    with Image.open(Path(data_dir) / png) as im:
        a = np.asarray(im.convert("RGBA"))[..., 3] > 0
    full = np.zeros((fh, fw), bool)
    hh, ww = a.shape
    full[oy:oy + hh, ox:ox + ww] = a[: fh - oy, : fw - ox]
    if f == 2:
        full = np.kron(full, np.ones((2, 2), bool))
    return full


def depth_mask(png, data_dir):
    import numpy as np
    from PIL import Image

    with Image.open(Path(data_dir) / png) as im:
        return np.asarray(im.convert("LA"))[..., 1] > 0


def check_colour_alignment(conn: sqlite3.Connection, data_dir, limit: int = 1500, seed: int = 7) -> dict:
    """Compara, em uma amostra, a silhueta do sprite colorido (no quadro cheio) com a mascara do mapa de profundidade.

    Metricas: cobertura = |cor ∩ prof| / |cor| (quanto do desenho cai dentro do volume de profundidade),
    iou = |cor ∩ prof| / |cor ∪ prof| e o deslocamento (dx,dy) em px que maximiza o iou
    (0,0 = alinhado quadro a quadro)."""
    import random

    import numpy as np

    data_dir = Path(data_dir)
    q = conn.execute("""
        SELECT d.name, d.png, s.png, s.width, s.height, s.offset_x, s.offset_y, s.scale, s.frame_w, s.frame_h
        FROM depth_maps d JOIN sprites s ON s.name = d.name""").fetchall()
    rng = random.Random(seed)
    rng.shuffle(q)
    ious, covs, shifts = [], [], []
    skipped = 0
    for name, dpng, spng, w, h, ox, oy, sc, fw, fh in q[:limit]:
        try:
            c = colour_in_frame((spng, w, h, ox, oy, sc, fw, fh), data_dir)
            d = depth_mask(dpng, data_dir)
        except (OSError, ValueError):
            skipped += 1
            continue
        if c is None or c.sum() == 0:
            skipped += 1
            continue
        inter = int((c & d).sum())
        ious.append(inter / max(1, int((c | d).sum())))
        covs.append(inter / int(c.sum()))
        best, bd = inter / max(1, int((c | d).sum())), (0, 0)     # so troca (0,0) se ganhar > 0,005
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                s = np.roll(np.roll(c, dy, 0), dx, 1)
                v = (s & d).sum() / max(1, (s | d).sum())
                if v > best + 0.005:
                    best, bd = v, (dx, dy)
        shifts.append(bd)
    n = len(ious)
    if not n:
        return {"n": 0, "pares_disponiveis": len(q), "ignorados": skipped}
    ious_a, covs_a = np.array(ious), np.array(covs)
    zero = sum(1 for s in shifts if s == (0, 0))
    return {
        "n": n,
        "pares_disponiveis": len(q),
        "ignorados": skipped,
        "iou_mediana": round(float(np.median(ious_a)), 3),
        "iou_p10": round(float(np.percentile(ious_a, 10)), 3),
        "cobertura_mediana": round(float(np.median(covs_a)), 3),
        "cobertura_p10": round(float(np.percentile(covs_a, 10)), 3),
        "cobertura_ge_90pct": round(float((covs_a >= 0.9).mean()), 3),
        "melhor_deslocamento_zero": round(zero / n, 3),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game-dir", default=os.environ.get("PZ_GAME_DIR", DEFAULT_GAME_DIR))
    ap.add_argument("--data-dir", default=str(HERE / "data"))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--no-check", action="store_true", help="pula a conferencia cor x profundidade")
    a = ap.parse_args(argv)
    data_dir = Path(a.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "acervo.sqlite")
    res = extract(conn, a.game_dir, data_dir, workers=a.workers, check_sample=0 if a.no_check else 1500,
                  progress=lambda n, t: print(f"  folhas {n}/{t}", file=sys.stderr) if n % 50 == 0 or n == t else None)
    for k, v in res.items():
        print(f"{k}: {v}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
