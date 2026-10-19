"""Receita de porte 3D: carregar, validar e expandir os espelhamentos (ver CONTRATO.md).

Uso:  python -m porte3d.receita <receita.json>     (valida e mostra as peças expandidas)
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "receita.schema.json").read_text(encoding="utf-8"))
AXES = "xyz"


class ReceitaInvalida(ValueError):
    pass


def carregar(path: str | Path) -> dict:
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    validar(r)
    return r


def validar(r: dict) -> None:
    """Esquema JSON + regras que o esquema não expressa. Levanta ReceitaInvalida com todos os problemas."""
    erros = [f"{'/'.join(map(str, e.absolute_path)) or '(raiz)'}: {e.message}"
             for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(r)]
    if erros:
        raise ReceitaInvalida("\n".join(erros))
    nomes = [p["nome"] for p in r["pecas"]]
    for n in {n for n in nomes if nomes.count(n) > 1}:
        erros.append(f"peça repetida: {n}")
    for p in r["pecas"]:
        if p["forma"] == "caixa":
            if any(a >= b for a, b in zip(p["min"], p["max"])):
                erros.append(f"{p['nome']}: min precisa ser menor que max em x, y e z")
            if "afinar" in p:
                lado = min(p["max"][0] - p["min"][0], p["max"][1] - p["min"][1])
                if p["afinar"]["quanto"] * 2 >= lado:
                    erros.append(f"{p['nome']}: afinar maior que a peça")
        if p["forma"] == "prisma" and p["de"] >= p["ate"]:
            erros.append(f"{p['nome']}: 'de' precisa ser menor que 'ate'")
    arte = r.get("arte", {"modo": "adesivo"})   # bloco legado: o nível arte não é mais aprovado
    if arte["modo"] == "kit":
        recortes = arte.get("recortes", {})
        if not recortes or not arte.get("faces"):
            erros.append("arte kit precisa de 'recortes' e 'faces'")
        for nome, rc in recortes.items():
            if rc["peca"] not in nomes:
                erros.append(f"recorte {nome}: peça {rc['peca']} não existe")
            u0, v0, u1, v1 = rc["recorte"]
            if u0 >= u1 or v0 >= v1:
                erros.append(f"recorte {nome}: precisa de u0 < u1 e v0 < v1")
        for peca, fs in arte.get("faces", {}).items():
            if peca not in nomes:
                erros.append(f"faces: peça {peca} não existe")
            for rc in fs.values():
                if rc not in recortes:
                    erros.append(f"faces de {peca}: recorte {rc} não existe")
    if r.get("tras") == "N" and "N" not in r["sprites"]:
        erros.append("tras = N, mas não há sprite N")
    if erros:
        raise ReceitaInvalida("\n".join(erros))


def _espelhar(p: dict, eixo: str) -> dict:
    """Cópia da peça espelhada no plano eixo = 0."""
    i = AXES.index(eixo)
    q = copy.deepcopy(p)
    if p["forma"] == "caixa":
        q["min"][i], q["max"][i] = -p["max"][i], -p["min"][i]
        if "afinar" in q:
            troca = {f"+{eixo}": f"-{eixo}", f"-{eixo}": f"+{eixo}"}
            q["afinar"]["lados"] = [troca.get(s, s) for s in q["afinar"]["lados"]]
    elif p["forma"] == "prisma":
        if p["eixo"] == eixo:
            q["de"], q["ate"] = -p["ate"], -p["de"]
        else:
            q["perfil"] = [[-a, z] for a, z in p["perfil"]][::-1]
    elif p["forma"] == "cilindro":
        q["centro"][i] = -p["centro"][i]
    if "rot" in q:   # espelhar no plano eixo=0 inverte o giro em torno dos outros dois eixos
        q["rot"] = [(-v if k != i else v) for k, v in enumerate(q["rot"])]
    return q


def tamanho(p: dict) -> list[float]:
    if p["forma"] == "caixa":
        return [b - a for a, b in zip(p["min"], p["max"])]
    if p["forma"] == "prisma":
        a = [v[0] for v in p["perfil"]]
        z = [v[1] for v in p["perfil"]]
        comp = p["ate"] - p["de"]
        return [comp, max(a) - min(a), max(z) - min(z)] if p["eixo"] == "x" else [max(a) - min(a), comp, max(z) - min(z)]
    d = 2 * max(p["raio"], p.get("raio_topo", 0))
    s = [d, d, d]
    s[AXES.index(p.get("eixo", "z"))] = p["altura"]
    return s


def expandir(r: dict) -> dict:
    """Receita com os espelhos aplicados (cada cópia vira uma peça) e os padrões preenchidos."""
    validar(r)
    out = copy.deepcopy(r)
    out.setdefault("tras", "simetrico")
    out.setdefault("material", "madeira")
    pecas = []
    for p in r["pecas"]:
        base = copy.deepcopy(p)
        base.setdefault("material", out["material"])
        base.setdefault("chanfro", 0.0)
        if base["forma"] == "cilindro":
            base.setdefault("eixo", "z")
            base.setdefault("segmentos", 24)
        if "veio" not in base:
            s = tamanho(base)
            base["veio"] = AXES[s.index(max(s))]
        eixos = base.pop("espelhar", [])
        base["origem"] = p["nome"]
        copias = [("", base)]
        for e in eixos:
            copias += [(suf + "." + e if suf else "." + e, _espelhar(c, e)) for suf, c in copias]
        for suf, c in copias:
            c["nome"] = p["nome"] + suf.replace(".x.y", ".xy")
            pecas.append(c)
    out["pecas"] = pecas
    return out


def main(argv: list[str]) -> int:
    try:
        r = expandir(carregar(argv[1]))
    except ReceitaInvalida as e:
        print("receita inválida:\n" + str(e))
        return 1
    for p in r["pecas"]:
        print(f"{p['nome']:<20} {p['forma']:<8} material={p['material']:<8} veio={p['veio']}  tamanho={[round(v, 3) for v in tamanho(p)]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
