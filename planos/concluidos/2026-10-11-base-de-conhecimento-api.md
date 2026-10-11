# Base de conhecimento da API 42.21 (camada 2) — consultar a API real antes de escrever o mod

**Estado:** concluído

**Módulos:** `07-PZ-API-Knowledge/` (novo), `06-PZ-Lab-Headless/mcp/` (ferramentas novas no `pz-live`), `.claude/skills/pz-modding/` (novo), `.gitignore`

## Problema observado

O laboratório da [camada 1](concluidos/2026-10-11-laboratorio-headless.md) permite testar, mas o código ainda é escrito no escuro. Evidências de hoje:

- O agente que escreveu o mod de prova precisou procurar à mão no Lua vanilla e rodar `javap` no `projectzomboid.jar` para descobrir quais APIs existem. Mesmo assim, ele deixou 9 pontos "a verificar no servidor real".
- No laboratório, `Translator.setLanguage(Languages.instance:getByName("EN"))` foi um chute e falhou ("attempted index: instance of non-table").
- A B42 mudou muito em relação à B41 (`craftRecipe`, `ItemType = base:...`, traduções em JSON). O que se sabe de cabeça sobre a API costuma ser da B41.

## Resultado

Antes de escrever um mod, o Claude consulta pelo MCP `pz-live` a assinatura real de funções globais, classes Java expostas ao Lua, eventos, campos de script e chaves de tradução da 42.21, junto com exemplos do vanilla (arquivo:linha).

## Incluído

- Gerador em Python (`07-PZ-API-Knowledge/build_index.py`) que monta, com um comando, um banco pesquisável (SQLite FTS) a partir da instalação do jogo, sem gravar nada nela:
  - funções globais e classes Java expostas ao Lua, com métodos e assinaturas (via `javap` no `projectzomboid.jar`; JDK 21 já instalado);
  - eventos `Events.*`, com os arquivos vanilla que os usam;
  - blocos de script (`item`, `craftRecipe`, `fluid`, entidades), com os campos válidos e exemplos;
  - chaves de tradução por categoria;
  - referências `arquivo:linha` para os usos no Lua vanilla.
- Ferramentas novas no `pz-live`: `api_search`, `api_class`, `api_event`, `script_fields` e `vanilla_examples`, com testes.
- Skill `.claude/skills/pz-modding/SKILL.md` (pt-BR) com as convenções da B42 e o ciclo de teste no laboratório. Cada afirmação deve vir do índice ou do que o laboratório provou.
- Conferência ao vivo no laboratório de uma amostra das APIs indexadas.

## Excluído

- Descompilar o código-fonte do jogo para o disco ou baixar um descompilador. Se o `javap` não bastar, parar e perguntar ao usuário.
- Versionar dados gerados a partir do jogo. O banco fica no `.gitignore`, para não redistribuir conteúdo da The Indie Stone.
- Linha de base de erros vanilla no `lua_errors` (continua no backlog).
- Modo cliente e qualquer API que só exista no cliente: ela entra no índice, mas não é conferida ao vivo.

## Gate de saída

1. `python 07-PZ-API-Knowledge/build_index.py` monta o banco do zero com um comando e informa as contagens (funções, classes, métodos, eventos, campos de script, chaves de tradução).
2. **Conjunto de aceitação** definido na fatia 1, com ~15 APIs conhecidas e 3 inexistentes como controle negativo. As ferramentas novas acertam todas as conhecidas e dão "não encontrado" para as inexistentes. Exemplos esperados: `getScriptManager`, `ScriptManager:getCraftRecipe`, `CraftRecipe:getInputs`, `instanceItem`, `ItemContainer.new`, `Events.OnServerStarted`, `Translator.loadFiles` e os campos `ItemType` e `UseDelta` do bloco `item`.
3. Pelo menos 10 APIs do conjunto conferidas ao vivo no laboratório: a existência e o tipo batem com o índice. O servidor fica desligado no final.
4. Os 65 testes atuais do MCP continuam passando, e os testes novos também.
5. A skill `pz-modding` existe e cita a origem de cada regra.
6. Nada é gravado na pasta do jogo nem em `C:\Users\micro\Zomboid`.
7. `python planos/check.py` passa.

## Fatias

1. **Linha de base:** escrever o conjunto de aceitação (`07-PZ-API-Knowledge/acceptance.json`) e confirmar no laboratório quais itens existem de fato.
2. **Lua, scripts e traduções:** extrator do Lua vanilla (globais, `Events.*`, usos com arquivo:linha), dos blocos de script e dos JSON de tradução.
3. **Java exposto:** lista das classes expostas ao Lua (a partir do `LuaManager$Exposer` e da anotação `@LuaMethod`) e assinaturas via `javap`.
4. **Ferramentas no MCP:** as cinco consultas, com testes contra um banco pequeno de fixture.
5. **Skill:** `pz-modding`, montada a partir do índice e dos achados da camada 1.
6. **Prova e fechamento:** gate completo, documentação do módulo 07, atualização deste plano e do índice.

## Riscos e parada

- Se não for possível descobrir quais classes são expostas ao Lua só com análise estática (`javap`), usar o laboratório como fonte: a introspecção `zbinspect`/`zbmethods` no servidor vivo. Se nem assim der, congelar o plano e registrar o motivo.
- Se o banco ficar grande demais para ser útil (consultas que devolvem ruído), parar na fatia 4 e redesenhar o ranqueamento antes de seguir.
- Se o `javap` não bastar e um descompilador parecer necessário, parar e pedir autorização ao usuário.

## Fechamento

**Estado final:** concluído em 2026-10-11, no commit que move este arquivo para `concluidos/`. Executado por 4 agentes Sonnet em paralelo (fatias 1 a 4), com integração, skill e revisão feitas na sessão principal.

**Evidências do gate:**
1. `build_index.py` monta do zero em ~10 s (81,8 MB): 1.037 classes, 108.670 métodos, 14.561 campos, 759 funções globais, 197 eventos, 18.477 globais Lua, 138.209 usos, 14.430 blocos de script, 1.742 campos de script e 96.948 traduções.
2. `index_check.py`: 23/23. As 18 APIs reais foram encontradas e os 5 controles falsos, recusados.
3. `live_check.py --start --stop`: 23/23 no servidor vivo (versão `42.21.0 4a0e9546ec`), e o servidor parou sem deixar `java` rodando.
4. Testes: 103 do MCP (65 antigos e 38 novos) e 30 dos extratores, todos passando.
5. A skill `.claude/skills/pz-modding/SKILL.md` marca a origem de cada regra (índice, lab ou não verificado).
6. Os extratores só leem o jogo, e o lab usa `06-PZ-Lab-Headless/runtime/`.
7. `python planos/check.py` passando.

**Descobertas:**
- `Languages` não é exposto ao Lua. O caminho certo é `Translator.getAvailableLanguage()`. Isso explica o chute que falhou no lab.
- Uma classe exposta, como tabela global, só tem os métodos estáticos, `new` e `.class`. Os métodos de instância só existem no objeto.
- Receita de mod precisa do módulo no nome (`getCraftRecipe("Mod.Receita")`). O tempo da ação vem de `getTimedActionScript()`.
- O `javap` sozinho era lento demais. O extrator Java lê os `.class` direto do jar, sem descompilar.

**Ajustes feitos na integração:** `scaffold_mod` passou a criar mods com `versionMin=42.21`, e foi criado o `index_check.py` (item 2 do gate).

**Devolvido ao backlog:** nomes dos parâmetros nas assinaturas e globais Lua definidos dentro de blocos `if`.
