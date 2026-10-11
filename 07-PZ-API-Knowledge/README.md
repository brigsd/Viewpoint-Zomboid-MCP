# 📚 Módulo 07: Base de Conhecimento da API 42.21

Índice pesquisável da API real do *Project Zomboid Build 42.21*. Ele é montado direto do jogo instalado, e as ferramentas do MCP `pz-live` o consultam antes de qualquer código de mod ser escrito. Assim o código é escrito contra a API verdadeira, e não contra o que se lembra da B41.

## Montar o índice

```bash
python 07-PZ-API-Knowledge/build_index.py
```

Leva ~10 s e gera `data/pz_api.sqlite` (~80 MB). A pasta `data/` fica fora do git, porque é conteúdo extraído do jogo. A pasta do jogo só é lida, nunca alterada.

| O que entra | De onde vem | Quantidade (42.21) |
| :--- | :--- | ---: |
| Classes Java expostas ao Lua | `LuaManager$Exposer` no `projectzomboid.jar` | 1.037 |
| Métodos e campos dessas classes (estáticos e de instância) | bytecode das classes | 108.670 + 14.561 |
| Funções globais do Lua (`getScriptManager`, `instanceItem`, …) | `@LuaMethod(global=true)` | 759 |
| Eventos (`Events.*`) | Lua vanilla | 197 |
| Globais definidos no Lua vanilla | Lua vanilla | 18.477 |
| Usos reais com arquivo:linha | Lua vanilla | 138.209 |
| Blocos e campos de script (`item`, `craftRecipe`, …) | `media/scripts` | 14.430 blocos, 1.742 campos |
| Traduções EN e PTBR | `media/lua/shared/Translate` | 96.948 |

## Consultar

Pelas ferramentas do `pz-live`: `api_exists`, `api_class`, `api_search`, `api_event`, `script_fields` e `vanilla_examples`. O guia de uso está na skill [`pz-modding`](../.claude/skills/pz-modding/SKILL.md).

## Conferir

| Comando | O que prova |
| :--- | :--- |
| `python 07-PZ-API-Knowledge/index_check.py` | As consultas acham as 18 APIs reais do [`acceptance.json`](acceptance.json) e recusam os 5 controles falsos |
| `python 07-PZ-API-Knowledge/live_check.py --start --stop` | As mesmas 23 entradas conferidas no servidor vivo do [laboratório](../06-PZ-Lab-Headless/) |
| `python -m unittest discover -s 07-PZ-API-Knowledge/tests` | Testes dos extratores, com dados sintéticos |

## Arquivos

| Arquivo | Papel |
| :--- | :--- |
| `schema.sql` | Estrutura do banco, compartilhada pelos extratores e pelo MCP |
| `build_index.py` | Monta o banco chamando os extratores |
| `extract_java.py` | Classes expostas, métodos, campos e funções globais (lê os `.class` direto do jar, sem descompilar) |
| `extract_lua.py` | Eventos, globais e usos no Lua vanilla |
| `extract_scripts.py` | Blocos e campos de `media/scripts` |
| `extract_translations.py` | Traduções EN e PTBR |
| `acceptance.json` | Conjunto de aceitação: APIs reais e controles falsos |

## Limites

- Os nomes dos parâmetros não aparecem nas assinaturas, só os tipos (ex.: `CraftRecipe getCraftRecipe(String)`).
- Globais do Lua definidos dentro de `if ... end` não entram, só os do nível de cima do arquivo.
- Classes expostas em tempo de execução por mods (como o ZombieBuddy) não estão no índice.
- 43 classes têm o mesmo nome curto que outra. A segunda aparece como `Externa.Interna` (ex.: `ItemKey.Food`).
- A busca textual trata um nome em camelCase como uma palavra só: procure por `getScript`, não por "script manager".
