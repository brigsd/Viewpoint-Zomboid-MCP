"""Gera o PLANO.md da esteira de porte 3D a partir da fila (fila/fila.json).

O plano agrupa os objetos em lotes temáticos / ordens de prioridade com:
- Caixas de marcação de progresso:
    [x] Aprovado (pronto / aguardando decisão do usuário)
    [~] Em andamento (retrabalho / modelagem / crítica)
    [-] Não portar / Reprovado
    [ ] Pendente na fila
- Barra de progresso visual por lote e total geral
- Agrupamento de variantes sob a forma base
- Métricas e resumo por categoria

Uso:
    python -m porte3d.plano [--caminho PLANO.md]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import fila

HERE = Path(__file__).resolve().parent
RAIZ_REPO = HERE.parent
CAMINHO_PLANO_PADRAO = RAIZ_REPO / "PLANO.md"


def _barra_progresso(concluidos: int, total: int, tamanho: int = 14) -> str:
    if total <= 0:
        return "░" * tamanho + "  0%"
    pct = concluidos / total
    cheios = min(tamanho, int(math.floor(pct * tamanho)))
    vazios = tamanho - cheios
    return f"{'▓' * cheios}{'░' * vazios} {int(pct * 100):>3}%"


def _icone_estado(o: dict) -> tuple[str, str]:
    """Retorna (tag_markdown, descricao_curta)."""
    st = o.get("estado", "fila")
    rodada = o.get("rodada", 0)
    notas = o.get("notas", [])
    ultima_nota = f"{notas[-1]['arte']:g}/{notas[-1]['realista']:g}" if notas else ""

    if st in ("aprovado", "aguardando_aprovacao"):
        info = f"r{rodada} · {ultima_nota}" if ultima_nota else f"r{rodada}"
        tag = "[x]"
        return tag, f"**aprovado** ({info})" if st == "aguardando_aprovacao" else f"**publicado/aprovado** ({info})"
    elif st in ("reprovado", "nao_portar"):
        motivo = o.get("motivo") or ""
        motivo_curto = f" — {motivo[:60]}…" if len(motivo) > 60 else (f" — {motivo}" if motivo else "")
        info = f" ({ultima_nota})" if ultima_nota and st == "reprovado" else ""
        return "[-]", f"*{st}*{info}{motivo_curto}"
    elif st in ("retrabalho", "em_modelagem", "em_critica", "em_inspecao"):
        info = f"r{rodada} ({ultima_nota})" if ultima_nota else f"r{rodada}"
        return "[~]", f"`{st}` ({info})"
    else:
        return "[ ]", "na fila"


def gerar_markdown() -> str:
    todos = fila._ler()
    objetos = todos.get("objetos", {})

    total_objs = len(objetos)
    cont_estados = Counter(o.get("estado", "fila") for o in objetos.values())

    concluidos_ok = cont_estados["aprovado"] + cont_estados["aguardando_aprovacao"]
    descartados = cont_estados["reprovado"] + cont_estados["nao_portar"]
    em_progresso = cont_estados["retrabalho"] + cont_estados["em_modelagem"] + cont_estados["em_critica"] + cont_estados["em_inspecao"]
    pendentes = cont_estados["fila"]
    resolvidos = concluidos_ok + descartados

    # Identificar variantes por forma_de
    variantes_por_base = defaultdict(list)
    bases = []
    for oid, o in objetos.items():
        base = o.get("forma_de")
        if base and base in objetos and base != oid:
            variantes_por_base[base].append(o)
        else:
            bases.append(o)

    # Ordenar bases:
    # 1. Primeiro os já iniciados/concluídos (não fila)
    # 2. Depois pela maior prioridade (-prioridade, categoria, id)
    def chave_ordenacao(o: dict):
        st = o.get("estado", "fila")
        iniciado = 0 if st != "fila" else 1
        prio = o.get("prioridade", 0)
        return (iniciado, -prio, o.get("categoria", ""), o.get("id", ""))

    bases_ordenadas = sorted(bases, key=chave_ordenacao)

    # Separar em lotes:
    # Lote 1: Os 18 objetos pioneiros do lote 1
    # Lote 2: Objetos de cozinha/eletrodomésticos iniciados e próximos na fila (prio 401-403)
    # Demais lotes: fatias de 15 a 20 bases
    lote1_ids = {
        "combo_washer_dryer_blue", "deluxe_espresso", "dishwasher_brown",
        "dishwasher_metal", "freezer_chest", "fridge_blue", "fridge_mini",
        "fridge_steel", "fridge_white", "generator_red", "hood_extractor",
        "microwave_chrome", "microwave_white", "oven_antique", "oven_green",
        "oven_grey", "oven_industrial", "oven_modern", "oven_red",
        "radio_valutech", "sink_chrome", "television_antique",
        "television_premium_technologies", "television_valutech",
        "washing_machine_white", "x_press_coffee", "fridge_industrial",
        "fridge_white_industrial", "conditioner_air"
    }

    itens_lote1 = []
    outros = []
    for b in bases_ordenadas:
        if b["id"] in lote1_ids:
            itens_lote1.append(b)
        else:
            outros.append(b)

    # Dividir outros em lotes
    TAM_LOTE = 15
    lotes = []
    lotes.append(("Lote 1 — Eletrodomésticos e Cozinha Pioneiros", itens_lote1))

    for i in range(0, len(outros), TAM_LOTE):
        chunk = outros[i:i + TAM_LOTE]
        prio_max = max(o.get("prioridade", 0) for o in chunk)
        prio_min = min(o.get("prioridade", 0) for o in chunk)
        cats = sorted(set(o.get("categoria", "") for o in chunk))
        cats_str = "/".join(cats)
        num_lote = len(lotes) + 1
        lotes.append((f"Lote {num_lote} — {cats_str.capitalize()} (prio {prio_max}..{prio_min})", chunk))

    # Construção do documento
    linhas = [
        "# Plano de Produção 3D — Esteira Project Zomboid (Viewpoint)",
        "",
        "> Plano gerado e sincronizado automaticamente a partir de `porte3d/fila/fila.json` via `python -m porte3d.plano`.",
        "",
        "## Progresso Geral",
        "",
        f"- **Total de Objetos:** {total_objs} ({len(bases)} bases + {len(objetos) - len(bases)} variantes)",
        f"- **Aprovados / Prontos:** {concluidos_ok} objetos",
        f"- **Em Andamento (Retrabalho / Modelagem):** {em_progresso} objetos",
        f"- **Não Portados / Reprovados:** {descartados} objetos",
        f"- **Pendentes na Fila:** {pendentes} objetos",
        f"- **Progresso Resolvido:** `{_barra_progresso(resolvidos, total_objs, 20)}` ({resolvidos}/{total_objs})",
        "",
        "### Legenda de Marcadores",
        "- `[x]` **Aprovado / Aguardando Aprovação** (modelo 3D validado pelo crítico com notas 8+)",
        "- `[~]` **Em Andamento** (em inspeção, modelagem, crítica ou retrabalho)",
        "- `[-]` **Não Portar / Reprovado** (objeto 2D de parede/vazado ou atingiu teto de 3 rodadas)",
        "- `[ ]` **Pendente na Fila**",
        "",
        "---",
        ""
    ]

    for titulo_lote, itens in lotes:
        # Calcular progresso do lote (incluindo variantes)
        todos_lote = []
        for b in itens:
            todos_lote.append(b)
            todos_lote.extend(variantes_por_base.get(b["id"], []))

        total_l = len(todos_lote)
        resolvidos_l = sum(1 for o in todos_lote if o.get("estado") in ("aprovado", "aguardando_aprovacao", "reprovado", "nao_portar"))
        aprovados_l = sum(1 for o in todos_lote if o.get("estado") in ("aprovado", "aguardando_aprovacao"))

        barra = _barra_progresso(resolvidos_l, total_l, 12)
        linhas.append(f"## {titulo_lote}  `{barra}`  ({resolvidos_l}/{total_l})")
        linhas.append("")

        for b in itens:
            tag, desc = _icone_estado(b)
            cat = b.get("categoria", "")
            prio = b.get("prioridade", "")
            linhas.append(f"- {tag} **`{b['id']}`** — {desc} `[{cat} | prio {prio}]`")

            # Variantes sob a base
            vars_b = variantes_por_base.get(b["id"], [])
            for v in vars_b:
                v_tag, v_desc = _icone_estado(v)
                linhas.append(f"  - {v_tag} *↳ variante:* `{v['id']}` — {v_desc}")

        linhas.append("")

    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            s.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="python -m porte3d.plano", description="Gera PLANO.md a partir da fila")
    ap.add_argument("--caminho", default=str(CAMINHO_PLANO_PADRAO), help="caminho do PLANO.md de saída")
    args = ap.parse_args(argv)

    md = gerar_markdown()
    destino = Path(args.caminho)
    destino.write_text(md, encoding="utf-8")
    print(f"PLANO.md gerado com sucesso em: {destino} ({len(md.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
