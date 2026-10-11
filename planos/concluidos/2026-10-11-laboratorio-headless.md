# Laboratório headless (camada 1) — testar mods sem abrir o jogo

**Estado:** concluído

**Módulos:** `06-PZ-Lab-Headless/` (novo), `.mcp.json`, `.gitignore`

## Problema observado

Para criar mods, o Claude escrevia código sem poder executá-lo. O usuário precisava abrir o jogo, testar e relatar o erro, e repetir isso a cada mudança.

## Resultado

O Claude sobe, testa e derruba um servidor Project Zomboid 42.21 sozinho, executa Lua dentro dele e lê os erros, sem o usuário abrir o jogo.

## Incluído

- Launcher `lab/pzlab.py` para o servidor dedicado (`zombie.network.GameServer`), com ZombieBuddy e HTTP local, `-nosteam` e `-cachedir` isolado em `runtime/`.
- Mini-agente Java (`lab/agent/`) que contorna dois problemas do ZombieBuddy 2.3.2 no Windows e permite parar o servidor salvando o mundo.
- MCP `pz-live` (`mcp/server.py`) com 13 ferramentas, registrado em `.mcp.json`.
- Mod de prova `ZBLabTest` (item + `craftRecipe`) e o teste `tests/smoke_zblabtest.lua`.

## Excluído

- Cliente com jogador, interface, Viewpoint e shaders (sem `IsoPlayer` no servidor dedicado).
- Base de conhecimento da API (virou a camada 2 no backlog).

## Gate de saída

1. O servidor sobe sem janela e responde Lua pelo HTTP.
2. O mod de prova é carregado e o smoke test passa sem falhas.
3. `reload_lua`, `lua_inspect` e `lua_errors` funcionam contra o servidor real.
4. O servidor para salvando o mundo e não deixa processo `java` para trás.
5. Nada é gravado na pasta do jogo, em `C:\Users\micro\Zomboid` ou em `~/.zombie_buddy`.
6. Os testes do MCP passam.

## Fatias

1. Launcher + boot real (agente Sonnet).
2. MCP contra um servidor falso (agente Sonnet).
3. Mod de prova + smoke test com validação estática (agente Sonnet).
4. Integração no servidor real, correções e documentação.

## Riscos e parada

Parar se o ZombieBuddy não pudesse ser injetado no servidor dedicado. Isso não aconteceu: o HTTP experimental falhava no Windows e foi contornado pelo mini-agente, sem tocar no jogo.

## Fechamento

**Estado final:** concluído em 2026-10-11, commit `dbd4f6f`.

**Evidências do gate:**
1. Boot sem janela em 44–50 s; `getCore():getVersion()` devolveu `"42.21.0 4a0e9546ec"` com `isServer() == true`.
2. `smoke_zblabtest`: 29/31 verificações, 0 falhas e 2 avisos soft de tradução.
3. `reload_lua` recarregou `ZBLabTest.lua` via `reloadLuaFile`; `lua_inspect` listou métodos e campos de `zombie.scripting.objects.Item`; `lua_errors` agrupou os erros do log.
4. Parada graciosa em ~8 s; `tasklist` sem `java`.
5. Verificado pelo agente do launcher depois de todas as execuções.
6. 65 testes do MCP passando.

**Descobertas registradas:**
- No servidor dedicado, as traduções são carregadas antes de os mods serem ativados. A tradução do mod só aparece depois de `Translator.loadFiles()`.
- Sem configuração, o servidor usa o idioma do Windows (PT). O lab força `-Duser.language=en` para os testes darem sempre o mesmo resultado.
- Traduções B42 em JSON ficam em `common/media/lua/shared/Translate/<LANG>/`.

**Devolvido ao backlog:** camada 2 (API), linha de base de erros vanilla, senha na linha de comando, modo cliente automatizado e relato dos bugs do ZombieBuddy.
