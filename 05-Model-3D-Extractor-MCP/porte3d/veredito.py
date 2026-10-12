"""Extrai e valida o veredito do crítico (o último bloco ```json da resposta) contra veredito.schema.json, e
aplica as regras de nota que o crítico promete seguir (peça ausente -> no máximo 5; defeito grave -> no máximo 6).

Uso: python -m porte3d.veredito <resposta.txt> [--gravar <veredito.json>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "veredito.schema.json").read_text(encoding="utf-8"))
NOTA_MIN = 8


class VereditoInvalido(ValueError):
    pass


def extrair(texto: str) -> dict:
    blocos = re.findall(r"```json\s*(\{.*?\})\s*```", texto, flags=re.S)
    if not blocos:
        raise VereditoInvalido("a resposta não tem bloco ```json")
    try:
        v = json.loads(blocos[-1])
    except json.JSONDecodeError as e:
        raise VereditoInvalido(f"JSON inválido: {e}") from e
    validar(v)
    return v


def validar(v: dict) -> None:
    erros = [f"{'/'.join(map(str, e.absolute_path)) or '(raiz)'}: {e.message}"
             for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(v)]
    if erros:
        raise VereditoInvalido("\n".join(erros))
    for nivel in ("arte", "realista"):
        nota = v[f"nota_{nivel}"]
        defs = [d for d in v["defeitos"] if d["nivel"] in (nivel, "ambos")]
        if any(p["situacao"] == "ausente" for p in v["pecas"]) and nota > 5:
            erros.append(f"nota_{nivel} = {nota}, mas há peça prometida ausente (máximo 5)")
        if any(d["gravidade"] == "grave" for d in defs) and nota > 6:
            erros.append(f"nota_{nivel} = {nota}, mas há defeito grave nesse nível (máximo 6)")
    if erros:
        raise VereditoInvalido("\n".join(erros))


def aprovado(v: dict) -> bool:
    return v["nota_arte"] >= NOTA_MIN and v["nota_realista"] >= NOTA_MIN


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("resposta", type=Path)
    ap.add_argument("--gravar", type=Path)
    a = ap.parse_args(argv)
    try:
        v = extrair(a.resposta.read_text(encoding="utf-8"))
    except VereditoInvalido as e:
        print("veredito recusado:\n" + str(e))
        return 1
    if a.gravar:
        a.gravar.parent.mkdir(parents=True, exist_ok=True)
        a.gravar.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"nota_arte": v["nota_arte"], "nota_realista": v["nota_realista"], "aprovado": aprovado(v),
                      "defeitos": len(v["defeitos"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
