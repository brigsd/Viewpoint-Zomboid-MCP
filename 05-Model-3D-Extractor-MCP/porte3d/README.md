# porte3d — objetos 2.5D do Zomboid em modelos 3D

Biblioteca da esteira de porte 3D (plano `planos/2026-10-12-esteira-de-porte-3d.md`). A partir de uma **receita** (as peças do objeto em metros), gera o modelo 3D em dois níveis gráficos e as folhas de imagem para o crítico.

- **arte (legado):** textura tirada do desenho do jogo; não é mais produção.
- **realista:** geometria com chanfro e material gerado no Blender, com a oclusão assada na textura.

O que cada parte entrega para a outra está em [CONTRATO.md](CONTRATO.md).

## Uso

```bash
python -m porte3d.portar porte3d/receitas/mesa_fancy_dark.json
```

Isso roda tudo, nesta ordem: preparar → Blender (malha e buffers) → texturas e OBJ → Blender (vistas) → folhas. A saída vai para `acervo/data/porte3d/<id>/`, que fica fora do git porque tem arte derivada do jogo. Ali ficam:

- `<id>_realista.obj` (e `<id>_arte.obj`, legado), cada um com o seu `.mtl` e a sua textura;
- `folhas/`;
- `resultado.json`, com o contorno em 0° e a diferença de cor.

Leva de 2 a 3 minutos por objeto na CPU.

Precisa do Blender 5.2, por padrão o da Steam. Outro caminho pode ser indicado em `PORTE3D_BLENDER`.

## Peças

| arquivo | o que faz |
|---|---|
| `receita.py`, `receita.schema.json` | valida a receita e aplica os espelhos |
| `acervo.py` | lê o acervo do jogo e converte a geometria (caixa, cilindro, polígono, com translate e rotate) para a receita; também agrupa as direções, mapeia o material e sugere uma receita inicial |
| `preparar.py` | monta a pasta de trabalho: quadros do jogo e receita expandida com as cores |
| `blender/construir.py` | dentro do Blender: monta as peças, faz o UV, assa por texel (posição, normal, peça, visibilidade da câmera do jogo, oclusão e cor do material) e renderiza as vistas |
| `blender/materiais.py` | materiais procedurais do nível realista: madeira, metal, tecido e liso |
| `texturas.py` | compõe as texturas: realista (e o arte legado); grava o OBJ e o MTL |
| `folhas.py` | folhas para o crítico (comparação, giro, wireframe com legenda, sobreposição de contorno, zoom) e as medidas |
| `portar.py` | o caminho completo de um objeto |
| `conferir_formas.py` | folha que desenha a geometria do jogo convertida por cima dos sprites, para conferir a conversão |
| `prever.py` | prévia rápida da receita sobre o desenho do jogo, sem Blender (ferramenta do modelador) |
| `inspecao.py` | medições do inspetor: cobertura da geometria, pé escondido, espelhamento, objeto de parede, dicas |
| `ficha.schema.json`, `veredito.schema.json`, `veredito.py` | contratos do inspetor e do crítico; `veredito.py` extrai e valida o JSON do crítico |
| `fila.py`, `fila/fila.json` | estados de cada objeto, com transições validadas; é o único que grava a fila |
| `relatorio.py` | lista final de reprovados e não portados (gerada por script) |
| `galeria.py` | página local de aprovação (`servir` abre em 127.0.0.1:8765) |
| `calibracao/` | casos e resultado da calibração do inspetor e do crítico |
| `receitas/`, `fichas/`, `vereditos/` | o que a esteira produz (dado nosso, versionado) |

## Esteira com agentes

O laço inspetor → modelador → crítico está na skill `.claude/skills/porte-3d/SKILL.md`, e os agentes estão em `.claude/agents/` (`inspetor-3d`, `modelador-3d` e `critico-3d`).

## Testes

```bash
python -m unittest discover -s 05-Model-3D-Extractor-MCP/porte3d/tests -t 05-Model-3D-Extractor-MCP -v
```

Os testes usam dados sintéticos e não precisam do Blender nem dos arquivos do jogo.
