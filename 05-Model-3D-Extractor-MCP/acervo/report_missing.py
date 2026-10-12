#!/usr/bin/env python3
"""Relatorio dos tiles sem PNG de sprite: classifica o motivo e escreve data/report_missing.md e .csv.

Motivos (exclusivos, nesta ordem de decisao):
  lit_so_geometria   variante acesa (tileset terminado em `_on`) que so aparece em tileGeometry/tileDepthTextureAssignments
                     (o jogo desenha a luz por cima do sprite base: nao ha sprite proprio)
  lit_definida       tileset `_on` definido nos .tiles, mas sem sprite nos packs
  tileset_sem_sprite nenhum sprite do tileset em nenhum pack (ex. crafted_03: tem mapa de profundidade, nao tem cor)
  indice_alem_pack   definido nos .tiles, o pack tem o tileset, mas so ate um indice menor
                     (ex. definicoes de overlay com mais indices do que o pack fornece)
  lacuna_no_pack     definido nos .tiles; o pack tem o tileset e indices maiores, mas nao este
  sem_definicao      nao esta em nenhum .tiles (so em tileGeometry/profundidade) e nao e variante acesa

Uso: python report_missing.py [--data-dir DIR]
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBJECT_CATS = ["moveis", "eletrodomesticos", "containers", "cozinha", "banheiro", "iluminacao"]
NON_DEF_SOURCES = {"tileGeometry.txt", "tileDepthTextureAssignments.txt"}
LIT_RE = re.compile(r"(^|_)on(_|$)", re.I)

REASONS = {
    "lit_so_geometria": ("Variante acesa (`_on`) so em geometria/profundidade",
                         "O nome so existe em `tileGeometry.txt` e/ou `tileDepthTextureAssignments.txt`. "
                         "Sao as versoes acesas de luminarias, TVs e eletrodomesticos: o jogo nao tem sprite proprio, "
                         "reaproveita o sprite base. Alguns tem mapa de profundidade proprio."),
    "lit_definida": ("Variante acesa (`_on`) definida, sem sprite",
                     "O tileset `_on` esta nos `.tiles`, mas nenhum pack tem a imagem."),
    "tileset_sem_sprite": ("Tileset inteiro sem sprite nos packs",
                           "Nenhum pack traz imagem para o tileset (ex. `crafted_03` tem mapa de profundidade "
                           "`DEPTH_crafted_03.png` mas nao tem cor)."),
    "indice_alem_pack": ("Indice alem do que o pack fornece",
                         "A definicao (muitas vezes de overlay) lista mais indices do que o pack tem para aquele tileset."),
    "lacuna_no_pack": ("Lacuna no meio do tileset",
                       "Definido nos `.tiles`; o pack tem indices maiores do mesmo tileset, mas nao este."),
    "sem_definicao": ("Sem definicao nos .tiles",
                      "So aparece em `tileGeometry.txt` ou nas atribuicoes de profundidade: nao ha propriedades nem imagem."),
}


def is_definition(source: str | None) -> bool:
    return any(s and s not in NON_DEF_SOURCES for s in (source or "").split(","))


def classify(conn: sqlite3.Connection) -> list[dict]:
    """Uma linha por tile sem sprite: name, tileset, idx, category, source, reason."""
    sprite_idx: dict[str, set[int]] = collections.defaultdict(set)
    for (n,) in conn.execute("SELECT name FROM sprites"):
        m = re.match(r"^(.*?)_(\d+)$", n)
        if m:
            sprite_idx[m.group(1)].add(int(m.group(2)))
    out = []
    q = """SELECT t.name, t.tileset, t.idx, COALESCE(t.category,'outros'), COALESCE(t.source,'')
           FROM tiles t WHERE NOT EXISTS (SELECT 1 FROM sprites s WHERE s.name = t.name)
           ORDER BY t.tileset, t.idx"""
    for name, ts, idx, cat, src in conn.execute(q):
        have = sprite_idx.get(ts, set())
        d = is_definition(src)
        if LIT_RE.search(ts):
            r = "lit_definida" if d else "lit_so_geometria"
        elif not have:
            r = "tileset_sem_sprite" if d else "sem_definicao"
        elif not d:
            r = "sem_definicao"
        elif idx > max(have):
            r = "indice_alem_pack"
        else:
            r = "lacuna_no_pack"
        out.append({"name": name, "tileset": ts, "idx": idx, "category": cat, "source": src, "reason": r})
    return out


def ranges(nums: list[int]) -> str:
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def depth_coverage(conn, cats):
    """Por categoria: tiles com PNG, quantos tem mapa de profundidade proprio / por atribuicao / nenhum."""
    own = {r[0] for r in conn.execute("SELECT name FROM depth_maps")}
    assigned = dict(conn.execute("SELECT name, depth FROM depth_assignments"))
    res = {}
    for cat in cats:
        n = o = a = z = 0
        for (name,) in conn.execute("""SELECT t.name FROM tiles t JOIN sprites s ON s.name=t.name WHERE t.category=?""", (cat,)):
            n += 1
            if name in own:
                o += 1
            elif assigned.get(name) in own:
                a += 1
            else:
                z += 1
        res[cat] = (n, o, a, z)
    return res


def write_report(conn: sqlite3.Connection, data_dir) -> dict:
    data_dir = Path(data_dir)
    rows = classify(conn)
    total_tiles = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    total_png = conn.execute("SELECT COUNT(*) FROM tiles t WHERE EXISTS (SELECT 1 FROM sprites s WHERE s.name=t.name)").fetchone()[0]
    cats = [r[0] for r in conn.execute("SELECT COALESCE(category,'outros') c, COUNT(*) FROM tiles GROUP BY c ORDER BY 2 DESC")]
    other_cats = [c for c in cats if c not in OBJECT_CATS]
    by = collections.Counter((r["category"], r["reason"]) for r in rows)
    reason_ids = list(REASONS)

    # contagens por categoria
    per_cat = {}
    for cat in cats:
        n = conn.execute("SELECT COUNT(*) FROM tiles WHERE COALESCE(category,'outros')=?", (cat,)).fetchone()[0]
        miss = sum(by[(cat, r)] for r in reason_ids)
        # cobertura sobre as definicoes dos .tiles (criterio do gate)
        defs = defs_png = 0
        for src, has in conn.execute("""SELECT t.source, EXISTS(SELECT 1 FROM sprites s WHERE s.name=t.name)
                                         FROM tiles t WHERE COALESCE(t.category,'outros')=?""", (cat,)):
            if is_definition(src):
                defs += 1
                defs_png += has
        per_cat[cat] = {"tiles": n, "png": n - miss, "faltam": miss, "defs": defs, "defs_png": defs_png,
                        **{r: by[(cat, r)] for r in reason_ids}}

    L: list[str] = []
    w = L.append
    w("# Tiles sem PNG de sprite")
    w("")
    w(f"Gerado por `report_missing.py` a partir de `acervo.sqlite` (nao versionado). "
      f"{total_tiles} tiles no catalogo, {total_png} com PNG, **{len(rows)} sem PNG**.")
    w("")
    w("## Motivos")
    w("")
    w("| Motivo | Total | Explicacao |")
    w("|---|---:|---|")
    for r in reason_ids:
        t = sum(1 for x in rows if x["reason"] == r)
        w(f"| `{r}` {REASONS[r][0]} | {t} | {REASONS[r][1]} |")
    w("")
    w("## Categorias de objeto")
    w("")
    w("Cobertura (gate 2) = tiles definidos nos `.tiles` que tem PNG / tiles definidos nos `.tiles`.")
    w("")
    head = "| Categoria | Tiles | Com PNG | Sem PNG | " + " | ".join(f"`{r}`" for r in reason_ids) + " | Cobertura das definicoes |"
    w(head)
    w("|---|" + "---:|" * (3 + len(reason_ids)) + "---:|")

    def line(cat):
        p = per_cat[cat]
        cov = f"{p['defs_png']}/{p['defs']} ({100 * p['defs_png'] / p['defs']:.1f}%)" if p["defs"] else "-"
        return (f"| {cat} | {p['tiles']} | {p['png']} | {p['faltam']} | "
                + " | ".join(str(p[r]) for r in reason_ids) + f" | {cov} |")

    for cat in OBJECT_CATS:
        if cat in per_cat:
            w(line(cat))
    tot = {k: sum(per_cat[c][k] for c in OBJECT_CATS if c in per_cat) for k in ["tiles", "png", "faltam", "defs", "defs_png"] + reason_ids}
    w(f"| **soma dos objetos** | {tot['tiles']} | {tot['png']} | {tot['faltam']} | "
      + " | ".join(str(tot[r]) for r in reason_ids)
      + f" | {tot['defs_png']}/{tot['defs']} ({100 * tot['defs_png'] / max(1, tot['defs']):.1f}%) |")
    w("")
    w("## Demais categorias")
    w("")
    w(head)
    w("|---|" + "---:|" * (3 + len(reason_ids)) + "---:|")
    for cat in other_cats:
        w(line(cat))
    w("")

    w("## Cobertura de profundidade (tiles com PNG, categorias de objeto)")
    w("")
    w("Mapa proprio = quadro em `DEPTH_<tileset>.png`; atribuido = via `tileDepthTextureAssignments.txt` para outro quadro.")
    w("")
    w("| Categoria | Com PNG | Mapa proprio | Mapa atribuido | Sem mapa |")
    w("|---|---:|---:|---:|---:|")
    dc = depth_coverage(conn, [c for c in OBJECT_CATS if c in per_cat])
    for cat, (n, o, a, z) in dc.items():
        w(f"| {cat} | {n} | {o} | {a} | {z} |")
    w("")

    w("## Lista dos que faltam nas categorias de objeto")
    w("")
    w("Agrupados por categoria, motivo e tileset; indices em intervalos.")
    for cat in OBJECT_CATS:
        sub = [x for x in rows if x["category"] == cat]
        w("")
        w(f"### {cat} ({len(sub)})")
        if not sub:
            w("")
            w("Nenhum.")
            continue
        for r in reason_ids:
            s2 = [x for x in sub if x["reason"] == r]
            if not s2:
                continue
            w("")
            w(f"**{REASONS[r][0]}** ({len(s2)})")
            w("")
            g = collections.defaultdict(list)
            for x in s2:
                g[x["tileset"]].append(x["idx"])
            for ts in sorted(g):
                w(f"- `{ts}`: {ranges(g[ts])} ({len(g[ts])})")
    w("")
    w("A lista completa, de todas as categorias, esta em `report_missing.csv`.")
    w("")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "report_missing.md").write_text("\n".join(L), encoding="utf-8")
    with open(data_dir / "report_missing.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["name", "tileset", "idx", "category", "reason", "source"])
        for x in rows:
            wr.writerow([x["name"], x["tileset"], x["idx"], x["category"], x["reason"], x["source"]])
    return {"missing": len(rows), "per_cat": per_cat, "by_reason": {r: sum(1 for x in rows if x["reason"] == r) for r in reason_ids},
            "depth": dc}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", default=str(HERE / "data"))
    a = ap.parse_args(argv)
    conn = sqlite3.connect(Path(a.data_dir) / "acervo.sqlite")
    res = write_report(conn, a.data_dir)
    conn.close()
    print(f"{res['missing']} tiles sem PNG; por motivo: {res['by_reason']}")
    print(f"Relatorio em {Path(a.data_dir) / 'report_missing.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
