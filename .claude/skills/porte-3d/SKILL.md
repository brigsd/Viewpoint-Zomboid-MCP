---
name: porte-3d
description: Laço da esteira de porte 3D do Project Zomboid (inspetor → modelador → crítico, até 3 rodadas, galeria do usuário). Use para portar objetos do jogo para 3D com a biblioteca porte3d, rodar o piloto ou um lote, e gerar a lista final de reprovados.
---

# Esteira de porte 3D

O plano ativo é `planos/2026-10-12-esteira-de-porte-3d.md`, e o contrato da biblioteca está em `05-Model-3D-Extractor-MCP/porte3d/CONTRATO.md`. Todos os comandos rodam a partir de `05-Model-3D-Extractor-MCP/`.

## Papéis

| papel | quem | escreve |
|---|---|---|
| orquestração e estados | script `porte3d/fila.py`, rodado por mim | `porte3d/fila/fila.json` e os artefatos versionados |
| medições do inspetor | script `porte3d/inspecao.py` | `acervo/data/porte3d/inspecao/<id>/` |
| inspetor | agente `.claude/agents/inspetor-3d.md` | a ficha |
| modelador | agente `.claude/agents/modelador-3d.md` | a receita, e só ela |
| geração | script `porte3d/portar.py` (Blender) | `acervo/data/porte3d/<id>/` |
| crítico | agente `.claude/agents/critico-3d.md` | a resposta, com o veredito em ```json |
| validação do veredito | script `porte3d/veredito.py` | `porte3d/vereditos/<id>/rodada_<n>.json` (via fila) |
| aprovação | o usuário, na galeria (`porte3d/galeria.py servir`) | a decisão na fila |
| lista final | script `porte3d/relatorio.py` | o texto, nunca escrito por agente |

**Nível de produção:** o `realista` (materiais procedurais do Blender). O nível `arte` é legado: a textura vem do sprite do jogo e não serve em 3D. Detalhes em `05-Model-3D-Extractor-MCP/porte3d/CONTRATO.md`.

Os tipos de agente novos só valem numa sessão nova. Até lá, despache um `general-purpose` com `model: sonnet` e mande ele primeiro ler e seguir o arquivo do agente.

## Um objeto

1. `python -m porte3d.fila mover <id> em_inspecao`
2. `python -m porte3d.inspecao <sprite_S>` grava as medições e as imagens.
3. **Inspetor:** recebe a pasta da inspeção e grava a ficha em `acervo/data/porte3d/trabalho/<id>/ficha.json`. Depois rode `python -m porte3d.fila ficha <id> <ficha>`. Se a decisão for `nao_portar`, o objeto para aqui.
4. A sugestão inicial da receita sai de `acervo.sugerir_receita` e é gravada em `acervo/data/porte3d/trabalho/<id>/sugestao.json`.
5. **Modelador:** recebe a ficha, a inspeção, a sugestão e o caminho `acervo/data/porte3d/trabalho/<id>/receita.json`. Depois rode `python -m porte3d.fila receita <id> <receita>`.
6. `python -m porte3d.portar porte3d/receitas/<id>.json --tex 1024`
7. **Crítico:** recebe só as folhas e as peças prometidas da ficha (nome, forma e descrição, nada além). Copie as folhas para uma pasta com nome neutro, para o nome do objeto não entregar nada.
8. Grave a resposta do crítico em `trabalho/<id>/critica_<n>.txt` e rode:
   - `python -m porte3d.veredito <arquivo> --gravar trabalho/<id>/veredito_<n>.json`;
   - se o veredito for recusado, refaça a crítica;
   - depois, `python -m porte3d.fila veredito <id> <veredito>`.
9. Se a fila disser `retrabalho`, volte ao passo 5 com o veredito, até a rodada 3. Se disser `aguardando_aprovacao`, o objeto vai para a galeria. Se disser `reprovado`, ele entra na lista final.

## Regras (do plano)

- **Lotes:**
  - lotes de 10 a 20 objetos, com no máximo 3 a 4 agentes ao mesmo tempo;
  - no máximo 2 gerações no Blender ao mesmo tempo, porque a CPU é o gargalo;
  - se mais da metade do lote cair em reprovado ou não portar, **pare**: o problema vira ajuste da ferramenta, e não mais rodadas.
- **Conferência:** antes de mandar para a galeria, eu confiro visualmente uma amostra dos aprovados pelo crítico (memória "conferir visualmente").
- **Variantes:** objetos com `forma_de` reaproveitam a receita aprovada da forma, e só a cor e os sprites mudam.
- **Despacho em massa:** os lotes além do piloto só rodam por workflow, e só depois que o usuário pedir ("use um workflow").
- **Git:** fichas, receitas, vereditos e fila são commitados ao fim de cada lote. As imagens ficam fora do git.
