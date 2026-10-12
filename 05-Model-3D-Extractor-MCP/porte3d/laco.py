"""Passos do laço da esteira para um objeto, sem agente (os agentes são despachados por quem orquestra).
Ver .claude/skills/porte-3d/SKILL.md.

  python -m porte3d.laco inspecionar <id>         fila -> em_inspecao, roda as medições e cria a pasta de trabalho
  python -m porte3d.laco ficha <id>               registra trabalho/<id>/ficha.json; se portar, grava a sugestão de receita
  python -m porte3d.laco gerar <id>               registra trabalho/<id>/receita.json, gera o modelo e as folhas,
                                                  copia as folhas para uma pasta neutra e imprime o pedido do crítico
  python -m porte3d.laco critica <id> <resposta>  valida o veredito do crítico e registra na fila
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from porte3d import acervo, fila, inspecao, portar, veredito

HERE = Path(__file__).resolve().parent
DADOS = HERE.parent / "acervo" / "data" / "porte3d"
TRABALHO = DADOS / "trabalho"
CEGA = DADOS / "cega"


def trabalho(id_: str) -> Path:
    p = TRABALHO / id_
    p.mkdir(parents=True, exist_ok=True)
    return p


def cmd_inspecionar(id_: str) -> dict:
    o = fila.obter(id_)
    if o["estado"] != "em_inspecao":
        fila.mover(id_, "em_inspecao")
    med = inspecao.inspecionar(o["sprites"]["S"], id=id_)
    t = trabalho(id_)
    return {"id": id_, "inspecao": str(DADOS / "inspecao" / id_), "ficha": str(t / "ficha.json"),
            "sugestao": med.get("sugestao", [])}


def cmd_ficha(id_: str) -> dict:
    t = trabalho(id_)
    fila.registrar_ficha(id_, t / "ficha.json")
    o = fila.obter(id_)
    if o["estado"] == "nao_portar":
        return {"id": id_, "estado": "nao_portar", "motivo": o["motivo"]}
    sug = acervo.sugerir_receita(acervo.abrir(), o["sprites"]["S"])
    sug["id"] = id_
    (t / "sugestao.json").write_text(json.dumps(sug, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"id": id_, "estado": o["estado"], "sugestao": str(t / "sugestao.json"), "receita": str(t / "receita.json")}


def pedido_critico(id_: str, rodada: int, pasta_cega: Path) -> str:
    ficha = json.loads(fila.caminho_ficha(id_).read_text(encoding="utf-8"))
    linhas = [f"objeto: {pasta_cega.name}", f"rodada: {rodada}", "peças prometidas (da ficha do inspetor):"]
    for p in ficha.get("pecas", []):
        q = f", {p['quantidade']}x" if p.get("quantidade", 1) > 1 else ""
        linhas.append(f"- {p['nome']} ({p['forma']}{q}): {p['descricao']}")
    linhas.append(f"\nfolhas, na pasta {pasta_cega / 'folhas'}\\ :")
    linhas.append("comparacao.png, giro_arte.png, giro_realista.png, fio.png, sobreposicao.png, zoom.png")
    linhas.append(f"\ngravar resposta em: {pasta_cega / 'resposta.txt'}")
    return "\n".join(linhas)


def cmd_gerar(id_: str, tex: int = 1024) -> dict:
    t = trabalho(id_)
    if fila.obter(id_)["estado"] == "retrabalho":
        fila.mover(id_, "em_modelagem")
    fila.registrar_receita(id_, t / "receita.json")
    o = fila.obter(id_)
    res = portar.portar(fila.caminho_receita(id_), tex=tex)
    nome = "caso_" + hashlib.sha1(f"{id_}:{o['rodada']}".encode()).hexdigest()[:8]
    destino = CEGA / nome
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(Path(res["pasta"]) / "folhas", destino / "folhas")
    pedido = pedido_critico(id_, o["rodada"], destino)
    (t / f"pedido_critico_{o['rodada']}.txt").write_text(pedido, encoding="utf-8")
    (destino / "pedido.txt").write_text(pedido, encoding="utf-8")         # o crítico lê daqui (nome neutro)
    return {"id": id_, "rodada": o["rodada"], "contorno_0": res.get("contorno_0"), "tempo_s": res["tempos_s"]["total"],
            "pedido": str(destino / "pedido.txt"), "resposta": str(destino / "resposta.txt")}


def cmd_critica(id_: str, resposta: str) -> dict:
    o = fila.obter(id_)
    texto = Path(resposta).read_text(encoding="utf-8")
    v = veredito.extrair(texto)
    v["objeto"], v["rodada"] = id_, o["rodada"]          # o crítico viu um nome neutro
    veredito.validar(v)
    t = trabalho(id_)
    arq = t / f"veredito_{o['rodada']}.json"
    arq.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    fila.registrar_veredito(id_, arq)
    o = fila.obter(id_)
    return {"id": id_, "rodada": o["rodada"], "nota_arte": v["nota_arte"], "nota_realista": v["nota_realista"],
            "estado": o["estado"], "motivo": o.get("motivo")}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd, id_ = argv[1], argv[2]
    try:
        if cmd == "inspecionar":
            r = cmd_inspecionar(id_)
        elif cmd == "ficha":
            r = cmd_ficha(id_)
        elif cmd == "gerar":
            r = cmd_gerar(id_)
        elif cmd == "critica":
            r = cmd_critica(id_, argv[3])
        else:
            print(__doc__)
            return 1
    except (fila.FilaErro, veredito.VereditoInvalido, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
