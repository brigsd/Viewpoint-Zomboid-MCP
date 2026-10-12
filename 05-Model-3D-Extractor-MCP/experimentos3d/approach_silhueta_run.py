"""Roda variantes da abordagem silhueta no harness, registra nota, triângulos e tempo.
Uso: python approach_silhueta_run.py nome1 nome2 ...   (nomes de VARIANTS)  |  all"""
import contextlib, io, json, sys, types
import numpy as np
sys.path.insert(0, ".")
import harness, approach_silhueta as S

VARIANTS = {
    "silhueta": {},                                   # padrão: res 32
    "silhueta_r24": dict(res=24),
    "silhueta_r48": dict(res=48),
    "silhueta_r64": dict(res=64),
    "silhueta_a128": dict(alpha=128),
    "silhueta_a1": dict(alpha=1),
    "silhueta_sombra": dict(shadow=True),
    "silhueta_dil1": dict(dilate=1),
    "silhueta_s5": dict(samples=5, minvotes=3),
    "silhueta_fillfront": dict(fill="front"),
    "silhueta_fillneigh": dict(fill="neigh"),
    "silhueta_q0": dict(quant=0),
    "silhueta_nomerge": dict(merge=False),
    "silhueta_al": dict(align=True),
    "silhueta_al_r1": dict(align=True, alrange=3),
    "silhueta_ad60": dict(adapt=0.60, maxdil=2),
    "silhueta_ad75": dict(adapt=0.75, maxdil=2),
    "silhueta_q60": dict(adapt=0.60, adaptmode="quorum"),
    "silhueta_q75": dict(adapt=0.75, adaptmode="quorum"),
    "silhueta_r48n": dict(res=48, fill="neigh"),
    "silhueta_r40n": dict(res=40, fill="neigh"),
    "silhueta_r32n": dict(res=32, fill="neigh"),
    "silhueta_ad85": dict(adapt=0.85),
    "silhueta_ad90": dict(adapt=0.90),
    "silhueta_ad95": dict(adapt=0.95, maxdil=3),
}
LOG = harness.HERE / "approach_silhueta_log.jsonl"

def run_variant(name):
    mod = types.ModuleType("approach_" + name)
    mod.build = S.make_build(**VARIANTS[name])
    sys.modules["approach_" + name] = mod
    S.STATS.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        harness.run(name)
    res = json.loads((harness.OUT / name / "resultado.json").read_text(encoding="utf-8"))["resumo"]
    tr = np.array([s["tris"] for s in S.STATS]); sec = np.array([s["seconds"] for s in S.STATS])
    rec = dict(variante=name, params=VARIANTS[name], nota=res["nota"], iou=res["iou"], mae=res["mae"],
               cat={k: v["nota"] for k, v in res["por_categoria"].items()},
               tris_media=int(tr.mean()), tris_max=int(tr.max()), tris_mediana=int(np.median(tr)),
               build_ms=round(float(sec.mean() * 1000)))
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    names = list(VARIANTS) if sys.argv[1:] == ["all"] else sys.argv[1:]
    for n in names:
        run_variant(n)
