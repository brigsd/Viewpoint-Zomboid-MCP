# Testes Lua do PZ Lab Headless

Testes **server-side** para mods de Project Zomboid Build 42.21, executados no servidor dedicado do lab
(sem jogador conectado) por meio do endpoint `/lua` do ZombieBuddy. O MCP expõe isso como
`run_lua_test(path)`: ele lê o arquivo `.lua`, faz `POST /lua` com o conteúdo e devolve o valor retornado
pelo script, serializado em JSON.

```
tests/
  README.md                 <- este arquivo
  smoke_zblabtest.lua       <- "prova de fogo": valida o mod mods/ZBLabTest
../mods/ZBLabTest/          <- mod de teste (item + craftRecipe + Lua marcador)
```

## 1. Como o teste é executado

1. O servidor sobe com o mod ativo (`Mods=ZBLabTest` no `.ini` do servidor) e o ZombieBuddy expõe o `/lua`.
2. `run_lua_test` envia o arquivo inteiro como corpo do POST (`LuaHandler.java`).
3. O ZombieBuddy compila o corpo como **um chunk Lua**, roda na thread Lua do jogo e serializa o
   **primeiro valor retornado** (`return ...`) com `LuaJson`.
4. Por padrão (`sandbox=true`) o chunk roda num ambiente próprio cujo `__index` é o ambiente global do jogo:
   você enxerga todos os globais (`getScriptManager`, `ZBLabTest`, ...), mas globais que **você criar** no
   teste não vazam para o jogo. Use `local` de qualquer forma.

### Atenção: profundidade do JSON (`depth`)

`LuaJson` usa `depth=1` por padrão: o objeto raiz é expandido, mas **qualquer tabela aninhada vira a string
`"[table]"`**. Para receber `checks` completo, a chamada deve usar `POST /lua?depth=4` (ou maior).
Por isso todo teste deve devolver, além de `checks`, as strings `summary` e `report` na raiz — elas ficam
completas mesmo com `depth=1`. O MCP deve preferir passar `depth=4`.

Detalhes de serialização úteis (de `LuaJson.java`):

- números inteiros viram inteiros JSON (`3.0` -> `3`); decimais continuam decimais;
- tabela Lua cuja chave `1` existe (ou vazia) vira **array**; senão vira objeto;
- `nil` em campo de tabela simplesmente some; valores Java viram `toString()`;
- ciclos viram `"[ref]"`. Retorne só dados simples (strings, números, booleanos, tabelas).

## 2. Convenção de retorno

Todo teste termina com `return { ... }` neste formato:

```lua
return {
    ok         = true,            -- false se algum check "hard" falhou
    test       = "smoke_zblabtest",
    total      = 31,
    passed     = 31,
    failed     = 0,               -- checks hard que falharam
    softFailed = 0,               -- checks soft (informativos) que falharam
    summary    = "smoke_zblabtest: OK (31/31 passaram, 0 falhas, 0 avisos soft)",
    report     = "[PASS] nome - detalhe\n[FAIL] outro - detalhe\n...",
    checks     = {
        { name = "mod_active", ok = true, soft = false, detail = "mods ativos: [ZBLabTest]" },
        -- ...
    },
}
```

Regras:

- **Um check = uma afirmação.** Nome em `snake_case`, estável (o MCP/Claude pode filtrar por nome).
- **Cada check roda em `pcall`.** Um erro Lua/Java (NPE, método inexistente) vira `ok=false` com
  `detail = "EXCECAO: ..."` e os demais checks continuam. Nunca deixe uma exceção escapar do chunk: isso
  vira HTTP 500 e você perde o relatório inteiro.
- **`detail` sempre explica o valor observado** (`"getUseDelta()=0.1"`), não só "falhou". Quando falhar, o
  detalhe precisa bastar para diagnosticar sem rodar de novo.
- **Hard vs soft.** `soft=true` marca checks informativos ou dependentes de comportamento ainda não
  verificado no servidor real (tradução, `CraftRecipeManager` com `character=nil`, eventos). Falha soft
  aparece como `[WARN]` e em `softFailed`, mas não zera `ok`. Quando um check soft se provar estável no
  servidor real, promova-o a hard.
- **Inclua controles negativos** (ex.: `getItem("Mod.NaoExiste") == nil`). Eles provam que o check não
  passaria por acidente.
- **Sem efeitos colaterais persistentes.** Use `ItemContainer.new()` e itens `instanceItem`; não toque em
  `ModData`, mundo ou arquivos. O teste deve poder rodar N vezes seguidas com o mesmo resultado.
- Termine com um `print("[ZBLabTest][nome] " .. summary)` opcional: vai para o `console.txt`/log do servidor.

## 3. O que dá (e o que não dá) para testar sem jogador

O servidor dedicado sem clientes **não tem `IsoPlayer`**: `getPlayer()`/`getSpecificPlayer(0)` devolvem
`nil`. Qualquer API que exija jogador, UI, câmera ou render fica fora.

| Dá para testar (headless) | Como |
|---|---|
| Mod ativo / Lua do mod carregou | `getActivatedMods()`, globais criados pelo mod (`ZBLabTest.loaded`) |
| Funções puras do mod | chamar direto (`ZBLabTest.sum(2,3)`) |
| Eventos de servidor | flag setada em handler de `Events.OnServerStarted` (**soft**: ordem de init não verificada) |
| Scripts de item (`item ...`) | `getScriptManager():getItem("Mod.Item")` + getters (`getFullName`, `getActualWeight`, `getUseDelta`, `getItemType`, ...) |
| Instanciar itens | `instanceItem("Mod.Item")` ou `container:AddItem("Mod.Item")` |
| Inventário sem dono | `ItemContainer.new()` (sem square/objeto/jogador) |
| Scripts de `craftRecipe` | `getScriptManager():getCraftRecipe(nome)`, `:getInputs()`, `:getOutputs()`, `getPossibleInputItems()`, `getPossibleResultItems()`, `getIntAmount()`, `isKeep()` |
| Item pertence a input | `InputScript:containsItem(scriptItem)` (dados puros, confiável) |
| Validação de recipe vs item | `CraftRecipeManager.isItemValidForRecipe(recipe, item, nil)` (**soft**: passa `character=nil`) |
| Listagens globais | `getScriptManager():getAllItems()`, `getAllCraftRecipes()` |
| Traduções | `item:getDisplayName()`, `recipe:getTranslationName()` (**soft**) — no servidor dedicado as traduções são carregadas **antes** de ativar os mods, então a tradução do mod não aparece no boot. Para testar, chame `Translator.loadFiles()` e consulte `Translator.getItemNameFromFullType("Mod.Item")` (verificado na 42.21). |

| NÃO dá (ou não é confiável) sem jogador | Por quê |
|---|---|
| **Executar** a receita de verdade (`CraftRecipeData.perform`, timed action) | exige `IsoGameCharacter`/`IsoPlayer`, `OnCreate` com jogador |
| Skills, XP, `NeedToBeLearn`, receitas conhecidas | estado do personagem |
| UI, context menu, tooltips, ISUI, atalhos de teclado | só client |
| Render, shaders, câmera, modelos 3D | só client com GPU (o servidor é headless) |
| Eventos que dependem de jogador (`OnPlayerUpdate`, `OnFillInventoryObjectContextMenu`...) | nunca disparam |
| Mundo/mapa/zumbis (`IsoCell`, `getCell()`) | pode existir no servidor, mas depende do estado do save; evite no smoke test |
| Qualquer coisa de Java fora do que o Kahlua expõe | classes não expostas dão erro em runtime |

Para cobrir o que não dá no servidor (ex.: executar a receita), será preciso um cliente headless/real
conectado — fora do escopo desta pasta.

## 4. Pegadinhas do Kahlua (Lua 5.1-ish) no PZ

- Listas Java (`ArrayList`, `Set`) **não** são tabelas Lua: use `list:size()` e `list:get(i)` com índice
  **base 0**. `#list` e `ipairs(list)` não funcionam. O helper `listToTable()` do smoke test converte.
- Sobrecargas Java com `nil` explícito: `CraftRecipeManager.isItemValidForRecipe(r, item, nil)`.
- Evite `string.format("%d", ...)` com valores vindos do Java e flags raras de `string.find`; use
  concatenação com `tostring()`, que é o que o smoke test faz.
- `float` do Java chega como `number` com ruído (`0.2f` -> `0.2000000029...`): compare com tolerância
  (`approx(a, b, 0.0001)`).
- `instanceof(obj, "NomeDaClasseJava")` é o jeito de checar tipo (ex.: `"DrainableComboItem"`).
- Sempre indexe campos aninhados com cuidado: um `nil` inesperado é a causa nº 1 de falha; o `pcall` do
  `check` pega, mas o `detail` precisa dizer qual valor veio `nil`.
- Os nomes de receita aceitam o formato curto (`"SharpenBlade"`, usado pelo vanilla) e provavelmente
  `Modulo.Nome`. O smoke test tenta os dois e reporta qual funcionou.

## 5. Escrevendo um novo teste (template)

```lua
-- tests/meu_mod_smoke.lua
local checks, passed, failed, softFailed = {}, 0, 0, 0

local function check(name, soft, fn)
    local okCall, okVal, detail = pcall(fn)
    local ok = okCall and okVal == true
    local msg = okCall and (detail ~= nil and tostring(detail) or "") or ("EXCECAO: " .. tostring(okVal))
    checks[#checks + 1] = { name = name, ok = ok, soft = soft and true or false, detail = msg }
    if ok then passed = passed + 1 elseif soft then softFailed = softFailed + 1 else failed = failed + 1 end
end

check("item_exists", false, function()
    local it = getScriptManager():getItem("MeuMod.MeuItem")
    return it ~= nil, "getItem -> " .. tostring(it)
end)

-- ... mais checks ...

local lines = {}
for i = 1, #checks do
    local c = checks[i]
    lines[i] = "[" .. (c.ok and "PASS" or (c.soft and "WARN" or "FAIL")) .. "] " .. c.name .. " - " .. c.detail
end
return {
    ok = (failed == 0), test = "meu_mod_smoke", total = #checks,
    passed = passed, failed = failed, softFailed = softFailed,
    summary = "meu_mod_smoke: " .. (failed == 0 and "OK" or "FALHOU"),
    report = table.concat(lines, "\n"), checks = checks,
}
```

Dica: copie `smoke_zblabtest.lua` inteiro (helpers `check`, `approx`, `listToTable`, `join` já estão prontos).

## 6. O mod de teste `ZBLabTest`

Estrutura (padrão B42 do repositório: `common/mod.info` + `42/media/...`):

```
mods/ZBLabTest/
  common/mod.info
  42/media/
    scripts/ZBLabTest_items.txt        item ZBLabTest.LabSample (base:drainable)
    scripts/ZBLabTest_recipes.txt      craftRecipe ZBLabTest.MakeLabSample
    lua/shared/ZBLabTest.lua           marcador ZBLabTest = { loaded = true, version = "0.1" } + sum()
    lua/server/ZBLabTest_Server.lua    serverLuaLoaded + flag em Events.OnServerStarted
    lua/shared/Translate/EN/ItemName.json   "ZBLabTest.LabSample": "Lab Sample"
    lua/shared/Translate/EN/Recipes.json    "MakeLabSample": "Make Lab Sample"
```

- **Item:** `ZBLabTest.LabSample` — `ItemType = base:drainable`, `Weight = 0.2`, `UseDelta = 0.1`,
  `DisplayCategory = Material`, `Icon = Thread` (ícone vanilla, sem assets novos).
- **Receita:** `ZBLabTest.MakeLabSample` — `InHandCraft`, `time = 20`, `category = Miscellaneous`;
  entradas: 2x `Base.Paperclip`, 1x `Base.Twigs`, 1x `Base.Scissors` (`mode:keep`, ferramenta);
  saída: 1x `ZBLabTest.LabSample`. Sem skill nem `NeedToBeLearn`.
- O mod **não** depende do ZombieBuddy (só scripts + Lua). Para instalar no lab: copiar/linkar
  `mods/ZBLabTest/` para a pasta de mods do servidor (`~/Zomboid/mods/`) e listar `ZBLabTest` em `Mods=`.

### Resultado esperado

`smoke_zblabtest` deve retornar `ok = true` com todos os checks hard em `PASS`. Os checks soft
(`ctx_is_server`, `event_on_server_started_fired`, `item_script_display_category`, `item_script_icon`,
`item_display_name_translated`, `recipe_in_hand_craft`, `recipe_listed_in_all_craft_recipes`,
`recipe_translated_name`, `recipe_manager_*_nochar`) podem aparecer como `[WARN]` na primeira execução
real; leia o `detail`, ajuste a expectativa e promova a hard o que se confirmar.

## 7. Validação estática (feita sem abrir o jogo)

- `luac`/`lua` não existem na máquina; a sintaxe Lua 5.1 foi validada com `lupa` (`pip install lupa`,
  módulo `lupa.lua51`), que também executou o teste contra um *mock* do ambiente PZ (31/31 checks).
  O mock só valida a lógica do teste, **não** a existência das APIs no jogo.
- A existência das APIs Java usadas foi conferida com `javap` em `projectzomboid.jar` (42.21) e a
  exposição ao Lua conferida em `LuaManager$Exposer`.
- Campos de `item`/`craftRecipe` usados no mod foram comparados com os scripts vanilla em
  `media/scripts/generated/` (todas as chaves e formas de linha existem no vanilla).
