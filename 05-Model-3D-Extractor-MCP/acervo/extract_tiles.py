"""Extrai definições de tiles, geometria 3D (B42) e profundidade para o catálogo SQLite do acervo.

Fontes (somente leitura) na pasta `media/` do jogo:
  *.tiles / *.tiles.txt          propriedades por sprite (o .txt é a versão legível; o .tiles é binário 'tdef')
  tileGeometry.txt               formas 3D por sprite (VERSION = 2)
  tileDepthTextureAssignments.txt  sprite -> textura de profundidade

Formatos verificados no Build 42.21:
  .tiles.txt : tileset { file, size = colunas,linhas, id, // nome_do_sprite, tile { xy = x,y  chave = valor ... } }
               só lista tiles com ao menos uma propriedade.
  .tiles     : 'tdef', int32 versão, int32 nº de tilesets; por tileset: nome\\n, arquivo png\\n, int32 colunas,
               int32 linhas, int32 id, int32 nº de tiles (= colunas*linhas); por tile: int32 nº de props,
               e para cada uma chave\\n valor\\n. Mesmo conteúdo do .txt (conferido), mas inclui as células vazias.
  índice     : idx = y * colunas + x, nome = f"{tileset}_{idx}". No tileGeometry, `xy = AxB` usa a mesma regra.

Uso:  python extract_tiles.py [pasta_do_jogo] [--db acervo.sqlite]
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sqlite3
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from categorize import categorize  # noqa: E402

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"

# Ordem de carga: a base primeiro; as demais só acrescentam ou sobrescrevem chaves (o jogo faz o mesmo).
DEF_FIRST = "newtiledefinitions"
GEOMETRY_COLS = 8  # largura fixa da grade xy do tileGeometry.txt


def media_dir(game_dir: str) -> str:
    """Aceita a pasta de instalação (com media/) ou a própria pasta media."""
    sub = os.path.join(game_dir, "media")
    return sub if os.path.isdir(sub) else game_dir


# ----------------------------------------------------------------------------------------------------------
# Definições (.tiles / .tiles.txt)
# ----------------------------------------------------------------------------------------------------------

def parse_tiles_txt(path: str):
    """Gera (tileset, colunas, linhas, idx, [(chave, valor)]) para cada tile do .tiles.txt."""
    cur = None
    tile = None
    name = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            s = ln.strip()
            if s == "}" and tile is not None and tile["xy"] is not None:
                # fechamento do bloco tile: registra
                x, y = tile["xy"]
                yield cur["file"], cur["cols"], cur["rows"], y * cur["cols"] + x, tile["props"]
                tile = None
                continue
            if not s or s in ("{", "}") or s.startswith("version"):
                continue
            if s == "tileset":
                cur, tile = None, None
            elif s.startswith("file =") and tile is None:
                cur = {"file": s[6:].strip(), "cols": 8, "rows": 0}
            elif s.startswith("size =") and tile is None and cur is not None:
                c, r = s[6:].split(",")
                cur["cols"], cur["rows"] = int(c), int(r)
            elif s.startswith("//"):
                name = s[2:].strip()
            elif s == "tile":
                tile = {"props": [], "xy": None, "name": name}
            elif "=" in s and tile is not None and cur is not None:
                k, v = s.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "xy":
                    x, y = (int(p) for p in v.split(","))
                    tile["xy"] = (x, y)
                else:
                    tile["props"].append((k, v))


def parse_tiles_bin(path: str):
    """Gera os mesmos itens de parse_tiles_txt a partir do .tiles binário (só tiles com propriedades)."""
    with open(path, "rb") as fh:
        d = fh.read()
    if d[:4] != b"tdef":
        raise ValueError(f"{path}: não é um arquivo tdef")
    pos = 4

    def i32():
        nonlocal pos
        v = struct.unpack_from("<i", d, pos)[0]
        pos += 4
        return v

    def line():
        nonlocal pos
        e = d.index(b"\n", pos)
        s = d[pos:e].decode("utf-8", "replace")
        pos = e + 1
        return s

    i32()  # versão
    for _ in range(i32()):
        name = line()
        line()  # png de origem
        cols, rows = i32(), i32()
        i32()  # id do tileset
        for idx in range(i32()):
            props = []
            for _ in range(i32()):
                k = line()
                v = line()
                props.append((k, v))
            if props:
                yield name, cols, rows, idx, props


def load_definitions(media: str) -> dict:
    """Junta todas as definições: nome -> {tileset, idx, cols, sources[], props{}}."""
    names = set()
    for f in os.listdir(media):
        if f.endswith(".tiles.txt"):
            names.add(f[: -len(".tiles.txt")])
        elif f.endswith(".tiles"):
            names.add(f[: -len(".tiles")])
    order = sorted(names, key=lambda n: (n != DEF_FIRST, n))
    defs: dict = {}
    for base in order:
        txt = os.path.join(media, base + ".tiles.txt")
        binp = os.path.join(media, base + ".tiles")
        if os.path.exists(txt):
            gen, src = parse_tiles_txt(txt), base + ".tiles.txt"
        else:
            gen, src = parse_tiles_bin(binp), base + ".tiles"
        for tileset, cols, rows, idx, props in gen:
            name = f"{tileset}_{idx}"
            d = defs.get(name)
            if d is None:
                d = defs[name] = {"tileset": tileset, "idx": idx, "cols": cols, "sources": [], "props": {}}
            if src not in d["sources"]:
                d["sources"].append(src)
            for k, v in props:
                d["props"][k] = v
    return defs


# ----------------------------------------------------------------------------------------------------------
# Geometria (tileGeometry.txt)
# ----------------------------------------------------------------------------------------------------------

_KV = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*?)\s*,?\s*$")
_COMMENT = re.compile(r"^/\*\s*(.*?)\s*\*/$")


def _triple(s: str):
    """'-4500x0x-6000' -> (-4500.0, 0.0, -6000.0)."""
    parts = s.split("x")
    if len(parts) != 3:
        return None
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        return None


def parse_geometry(path: str):
    """Lê o tileGeometry.txt. Devolve (versão, [tile]) com
    tile = {tileset, name, xy:(x,y), shapes:[{shape, attrs, raw}], props:[(k, v)]}."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")
    version = None
    tiles = []
    stack: list[str] = []          # nomes dos blocos abertos
    pending: str | None = None     # nome de bloco aguardando '{'
    tileset = None
    comment = None
    tile = None
    shape = None
    shape_lines: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = _COMMENT.match(s)
        if m:
            comment = m.group(1)
            continue
        if s == "{":
            stack.append(pending or "?")
            if pending == "tile":
                tile = {"tileset": tileset, "name": comment, "xy": None, "shapes": [], "props": []}
                comment = None
            elif tile is not None and len(stack) == 4 and pending not in ("properties",):
                shape = {"shape": pending, "attrs": {}, "raw": None}
                shape_lines = [pending, "{"]
            pending = None
            continue
        if s == "}":
            name = stack.pop() if stack else None
            if name == "tile" and tile is not None:
                tiles.append(tile)
                tile = None
            elif shape is not None and name == shape["shape"] and len(stack) == 3:
                shape_lines.append("}")
                shape["raw"] = "\n".join(shape_lines)
                tile["shapes"].append(shape)
                shape = None
            continue
        km = _KV.match(s)
        if km:
            k, v = km.group(1), km.group(2)
            if shape is not None:
                shape["attrs"][k] = v
                shape_lines.append(f"    {k} = {v}")
            elif tile is not None and stack and stack[-1] == "properties":
                tile["props"].append((k, v))
            elif tile is not None and stack and stack[-1] == "tile" and k == "xy":
                x, y = v.split("x")
                tile["xy"] = (int(x), int(y))
            elif k == "VERSION":
                version = int(v)
            elif k == "name" and stack and stack[-1] == "tileset":
                tileset = v
            continue
        if re.fullmatch(r"[A-Za-z_]\w*", s):
            pending = s
    return version, tiles


def geometry_rows(tile_name: str, shapes: list[dict]):
    """Linhas da tabela geometry. A caixa usa min/max; as outras formas guardam o bloco original em raw."""
    for i, sh in enumerate(shapes):
        a = sh["attrs"]
        t = _triple(a.get("translate", "")) or (None, None, None)
        r = _triple(a.get("rotate", "")) or (None, None, None)
        mn = _triple(a.get("min", "")) or (None, None, None)
        mx = _triple(a.get("max", "")) or (None, None, None)
        raw = None if sh["shape"] == "box" else sh["raw"]
        yield (tile_name, i, sh["shape"], *t, *r, *mn, *mx, raw)


# ----------------------------------------------------------------------------------------------------------
# Profundidade
# ----------------------------------------------------------------------------------------------------------

def parse_depth(path: str):
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            s = ln.strip()
            if "=" in s and not s.startswith("VERSION"):
                k, v = s.split("=", 1)
                out.append((k.strip(), v.strip().rstrip(",").strip()))
    return out


# ----------------------------------------------------------------------------------------------------------
# Gravação
# ----------------------------------------------------------------------------------------------------------

def extract(conn: sqlite3.Connection, game_dir: str) -> dict:
    """Preenche tiles, tile_props, geometry, geometry_props e depth_assignments. Devolve as contagens."""
    media = media_dir(game_dir)
    for t in ("tiles", "tile_props", "geometry", "geometry_props", "depth_assignments"):
        conn.execute(f"DELETE FROM {t}")

    defs = load_definitions(media)
    per_cat: collections.Counter = collections.Counter()
    tile_rows, prop_rows = [], []
    for name, d in defs.items():
        cat = categorize(d["tileset"], d["props"])
        per_cat[cat] += 1
        tile_rows.append((name, d["tileset"], d["idx"], ",".join(d["sources"]), cat))
        prop_rows.extend((name, k, v) for k, v in d["props"].items())
    conn.executemany("INSERT INTO tiles(name,tileset,idx,source,category) VALUES (?,?,?,?,?)", tile_rows)
    conn.executemany("INSERT INTO tile_props(name,key,value) VALUES (?,?,?)", prop_rows)

    counts: dict = {
        "tiles": len(tile_rows),
        "tile_props": len(prop_rows),
        "tilesets": len({d["tileset"] for d in defs.values()}),
        "categories": dict(per_cat),
    }
    warnings: list[str] = []

    geo_path = os.path.join(media, "tileGeometry.txt")
    geo_names: set = set()
    if os.path.exists(geo_path):
        version, gtiles = parse_geometry(geo_path)
        counts["geometry_version"] = version
        shape_types: collections.Counter = collections.Counter()
        grows, gprops = [], []
        mismatch = dup = 0
        by_name: dict = {}
        for gt in gtiles:
            x, y = gt["xy"] if gt["xy"] else (0, 0)
            # A grade do tileGeometry tem SEMPRE 8 colunas, mesmo nos tilesets cujo .tiles declara outra largura.
            by_rule = f"{gt['tileset']}_{y * GEOMETRY_COLS + x}"
            name = gt["name"] or by_rule
            if gt["name"] and gt["name"] != by_rule:
                mismatch += 1
            if name in by_name:
                dup += 1
            by_name[name] = gt  # em caso de duplicata, vale a última
        for name, gt in by_name.items():
            for sh in gt["shapes"]:
                shape_types[sh["shape"]] += 1
            grows.extend(geometry_rows(name, gt["shapes"]))
            gprops.extend((name, k, v) for k, v in gt["props"])
        geo_names = set(by_name)
        conn.executemany("INSERT INTO geometry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", grows)
        conn.executemany("INSERT INTO geometry_props(name,key,value) VALUES (?,?,?)", gprops)
        counts.update({
            "geometry_tiles": len(by_name),
            "geometry_tiles_with_shapes": len({r[0] for r in grows}),
            "geometry_shapes": len(grows),
            "geometry_props": len(gprops),
            "geometry_shape_types": dict(shape_types),
            "geometry_name_vs_xy_mismatch": mismatch,
            "geometry_duplicates": dup,
        })
        # Tiles com geometria mas sem propriedades nos .tiles (ex. variantes '_on'): entram no catálogo também.
        extra_geo = [(n, by_name[n]["tileset"]) for n in by_name if n not in defs]
    else:
        extra_geo = []
        warnings.append("tileGeometry.txt não encontrado")

    depth_names: set = set()
    depth_path = os.path.join(media, "tileDepthTextureAssignments.txt")
    if os.path.exists(depth_path):
        rows = parse_depth(depth_path)
        conn.executemany("INSERT OR REPLACE INTO depth_assignments(name,depth) VALUES (?,?)", rows)
        depth_names = {n for n, _ in rows}
        counts["depth_assignments"] = conn.execute("SELECT COUNT(*) FROM depth_assignments").fetchone()[0]
    else:
        warnings.append("tileDepthTextureAssignments.txt não encontrado")

    # Sprites só conhecidos pela geometria ou pela profundidade (sem propriedades nos .tiles).
    extra: dict = {}
    for n, ts in extra_geo:
        extra[n] = (ts, "tileGeometry.txt")
    for n in depth_names:
        if n not in defs and n not in extra:
            m = re.fullmatch(r"(.+)_(\d+)", n)
            if m:
                extra[n] = (m.group(1), "tileDepthTextureAssignments.txt")
    extra_rows = []
    for n, (ts, src) in extra.items():
        m = re.fullmatch(r".+_(\d+)", n)
        cat = categorize(ts, {})
        per_cat[cat] += 1
        extra_rows.append((n, ts, int(m.group(1)) if m else 0, src, cat))
    conn.executemany("INSERT OR IGNORE INTO tiles(name,tileset,idx,source,category) VALUES (?,?,?,?,?)", extra_rows)
    counts["tiles_from_definitions"] = len(tile_rows)
    counts["tiles_only_geometry"] = sum(1 for r in extra_rows if r[3] == "tileGeometry.txt")
    counts["tiles_only_depth"] = sum(1 for r in extra_rows if r[3] != "tileGeometry.txt")
    counts["tiles"] = len(tile_rows) + len(extra_rows)
    counts["categories"] = dict(per_cat)

    conn.commit()
    counts["warnings"] = warnings
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("game_dir", nargs="?", default=os.environ.get("PZ_GAME_DIR", DEFAULT_GAME_DIR))
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "acervo.sqlite"))
    args = ap.parse_args(argv)
    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    conn = sqlite3.connect(args.db)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql"), encoding="utf-8") as fh:
        conn.executescript(fh.read())
    counts = extract(conn, args.game_dir)
    conn.close()
    for k, v in counts.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
