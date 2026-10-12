"""Lista final de reprovados e não portados da esteira de porte 3D, gerada por script a partir da fila
(nunca escrita por agente). Uma linha por objeto: `objeto · última nota (arte/realista) · motivo`.

Uso:  python -m porte3d.relatorio [--md caminho.md]
"""
from __future__ import annotations

import argparse
import contextlib
import re
import sys
from pathlib import Path

from . import fila

TITULOS = {"reprovado": "Reprovados (3 rodadas sem nota 8)", "nao_portar": "Não portados (decisão do inspetor)"}
MAX_MOTIVO = 160


def _nota(o: dict) -> str:
    """Última nota 'arte/realista', ou '-' se o objeto nunca foi para a crítica."""
    if not o["notas"]:
        return "-"
    n = o["notas"][-1]
    return f"{n['arte']:g}/{n['realista']:g}"


def _motivo(o: dict) -> str:
    m = re.sub(r"\s+", " ", o["motivo"] or "sem motivo registrado").strip()
    return m if len(m) <= MAX_MOTIVO else m[:MAX_MOTIVO - 1].rstrip() + "…"


def _cabecalho(cont: dict) -> str:
    partes = [f"{e}: {cont[e]}" for e in fila.ESTADOS if cont[e]]
    return f"{sum(cont.values())} objetos  |  " + (", ".join(partes) if partes else "fila vazia")


def gerar(formato: str = "texto") -> str:
    """O relatório final como texto simples (padrão) ou markdown (`formato="md"`)."""
    md = formato == "md"
    cont = fila.resumo()
    out = ["# Porte 3D: reprovados e não portados", "", _cabecalho(cont), ""] if md else [
        "PORTE 3D: reprovados e não portados", _cabecalho(cont), ""]
    for estado in ("reprovado", "nao_portar"):
        objs = fila.objetos(estado)
        titulo = f"{TITULOS[estado]}: {len(objs)}"
        out.append(f"## {titulo}" if md else titulo)
        if md and objs:
            out += ["", "| objeto | última nota | motivo |", "|---|---|---|"]
            out += [f"| {o['id']} | {_nota(o)} | {_motivo(o).replace('|', '/')} |" for o in objs]
        elif objs:
            out += [f"  {o['id']} · {_nota(o)} · {_motivo(o)}" for o in objs]
        else:
            out.append("" if md else "  (nenhum)")
            if md:
                out.append("(nenhum)")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m porte3d.relatorio", description="Lista final de reprovados e não portados")
    ap.add_argument("--md", metavar="CAMINHO", help="grava também em markdown neste arquivo")
    a = ap.parse_args(argv)
    print(gerar(), end="")
    if a.md:
        destino = Path(a.md)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(gerar("md").encode("utf-8"))
        print(f"markdown gravado em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
