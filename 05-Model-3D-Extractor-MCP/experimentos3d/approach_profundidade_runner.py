"""Executor paralelo (multiprocessing) equivalente a `harness.py run`, mesmas saídas (resultado.json + folhas PNG).
Uso: python approach_profundidade_runner.py <abordagem> [--limit N] [--only i,j,k] [--workers 16]"""
import json
import sqlite3
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H   # noqa: E402


def work(args):
    approach, i, entry, sets, outname = args
    mod = __import__(f"approach_{approach}")
    for k, v in sets.items():
        setattr(mod, k, v)
    db = sqlite3.connect(H.DATA / "acervo.sqlite")
    obj = H.load_obj(db, entry)
    if any(v.rgba is None for v in obj.views.values()):
        return None
    tiles, per, tris, bt = [], {}, [], []
    for held in H.FACINGS:
        train = [f for f in H.FACINGS if f != held]
        try:
            t = time.time()
            mesh = mod.build(obj, train)
            bt.append(time.time() - t)
            tris.append(int(len(mesh.faces)))
            pred = H.render(mesh, obj.views[held].angle)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ! {entry['key']} [{held}]: {e}")
            pred = np.zeros((H.FH, H.FW, 4), np.uint8)
        per[held] = H.score(pred, obj.views[held].rgba)
        tiles.append((obj.views[held].rgba, pred))
    mean = {k: round(float(np.mean([p[k] for p in per.values()])), 4) for k in ("iou", "mae", "nota")}
    res = {"key": entry["key"], "category": entry["category"], "por_direcao": per, **mean,
           "triangulos": float(np.mean(tris)) if tris else 0, "build_s": float(np.mean(bt)) if bt else 0}
    out = H.OUT / outname
    sheet = Image.new("RGBA", (H.FW * 4, H.FH * 2), (40, 42, 48, 255))
    for j, (real, pred) in enumerate(tiles):
        for k, im in enumerate((real, pred)):
            tile = Image.fromarray(im)
            sheet.paste(tile, (j * H.FW, k * H.FH), tile)
    ImageDraw.Draw(sheet).text((4, 4), f"{entry['key'][:60]}  nota {mean['nota']}", fill=(255, 255, 0))
    sheet.save(out / f"{i:02d}.png")
    return i, res


def main():
    approach = sys.argv[1]
    sets = {}
    for j, a in enumerate(sys.argv):
        if a == "--set":
            k, v = sys.argv[j + 1].split("=")
            sets[k] = json.loads(v)
    outname = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else approach
    entries = json.loads((HERE / "testset.json").read_text(encoding="utf-8"))
    idx = list(range(len(entries)))
    if "--limit" in sys.argv:
        idx = idx[:int(sys.argv[sys.argv.index("--limit") + 1])]
    if "--only" in sys.argv:
        idx = [int(x) for x in sys.argv[sys.argv.index("--only") + 1].split(",")]
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 16
    (H.OUT / outname).mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with Pool(workers) as p:
        out = [r for r in p.imap_unordered(work, [(approach, i, entries[i], sets, outname) for i in idx]) if r]
    out.sort()
    results = [r for _, r in out]
    for i, r in out:
        print(f"[{i:2d}] {r['key'][:50]:<50} iou {r['iou']:.3f} mae {r['mae']:6.1f} nota {r['nota']:.3f} tris {r['triangulos']:.0f} t {r['build_s']:.1f}s")
    summary = {"abordagem": outname, "objetos": len(results), "segundos": round(time.time() - t0, 1),
               **{k: round(float(np.mean([r[k] for r in results])), 4) for k in ("iou", "mae", "nota")},
               "triangulos_medios": round(float(np.mean([r["triangulos"] for r in results]))),
               "build_s_medio": round(float(np.mean([r["build_s"] for r in results])), 2),
               "por_categoria": {}}
    for cat in sorted({r["category"] for r in results}):
        rs = [r for r in results if r["category"] == cat]
        summary["por_categoria"][cat] = {k: round(float(np.mean([r[k] for r in rs])), 4) for k in ("iou", "mae", "nota")}
    if len(idx) == len(entries):
        (H.OUT / outname / "resultado.json").write_text(
            json.dumps({"resumo": summary, "objetos": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "por_categoria"}), {c: v["nota"] for c, v in summary["por_categoria"].items()})


if __name__ == "__main__":
    main()
