"""Porta um objeto de ponta a ponta: receita -> entrada -> malha e buffers (Blender) -> texturas e OBJ ->
vistas (Blender) -> folhas para o crítico. Ver CONTRATO.md.

Uso: python -m porte3d.portar <receita.json> [--saida DIR] [--tex 2048] [--escala 4]
A saída padrão é acervo/data/porte3d/<id>/ (fora do git: tem arte derivada do jogo).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from porte3d import folhas, preparar, texturas

HERE = Path(__file__).resolve().parent
SAIDA = HERE.parent / "acervo" / "data" / "porte3d"
CONSTRUIR = HERE / "blender" / "construir.py"
BLENDER_PADRAO = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"


def blender() -> str:
    b = os.environ.get("PORTE3D_BLENDER", BLENDER_PADRAO)
    if not Path(b).exists():
        raise SystemExit(f"Blender não encontrado em {b} (defina PORTE3D_BLENDER)")
    return b


def rodar_blender(args: list[str], log: Path) -> None:
    with open(log, "a", encoding="utf-8") as f:
        p = subprocess.run([blender(), "-b", *args], stdout=f, stderr=subprocess.STDOUT, timeout=1800)
    if p.returncode != 0 or "Traceback" in log.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError(f"Blender falhou; veja {log}")


def portar(receita: Path, saida: Path = SAIDA, tex: int = 2048, escala: int = 4) -> dict:
    t0 = time.time()
    pasta = Path(preparar.preparar(receita, saida)).resolve()
    if pasta.name == "entrada":
        pasta = pasta.parent
    log = pasta / "blender.log"
    log.write_text("", encoding="utf-8")
    tempos = {}
    t = time.time()
    rodar_blender(["--factory-startup", "-P", str(CONSTRUIR), "--", "malha", str(pasta), str(tex)], log)
    tempos["malha"] = round(time.time() - t, 1)
    t = time.time()
    info = texturas.compor(pasta)
    tempos["texturas"] = round(time.time() - t, 1)
    t = time.time()
    rodar_blender([str(pasta / "cena.blend"), "-P", str(CONSTRUIR), "--", "vistas", str(pasta), str(escala)], log)
    tempos["vistas"] = round(time.time() - t, 1)
    t = time.time()
    medidas = folhas.gerar(pasta)
    tempos["folhas"] = round(time.time() - t, 1)
    tempos["total"] = round(time.time() - t0, 1)
    resultado = {"pasta": str(pasta), **info, **(medidas or {}), "tempos_s": tempos}
    (pasta / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultado


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("receita", type=Path)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--tex", type=int, default=2048)
    ap.add_argument("--escala", type=int, default=4)
    a = ap.parse_args(argv)
    print(json.dumps(portar(a.receita, a.saida, a.tex, a.escala), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
