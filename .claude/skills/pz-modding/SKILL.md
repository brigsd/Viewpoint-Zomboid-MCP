---
name: pz-modding
description: Criar, alterar ou testar mods do Project Zomboid Build 42.21 nesta suíte. Use sempre que for escrever Lua, scripts (item, craftRecipe), traduções ou mod.info para o PZ, ou testar um mod no laboratório headless. Traz as regras da B42 comprovadas no laboratório e o ciclo consultar → escrever → testar.
---

# Mods do Project Zomboid 42.21

Regras comprovadas nesta suíte. Cada uma diz de onde veio: **[índice]** é a base em `07-PZ-API-Knowledge` (montada do jogo instalado); **[lab]** foi conferido no servidor vivo do `06-PZ-Lab-Headless`; **[não verificado]** ainda precisa de prova.

## 1. Nunca chute a API — consulte primeiro

A B42 mudou muito em relação à B41, e o que se sabe de cabeça costuma ser B41. Antes de usar qualquer função, classe, evento ou campo de script, consulte o MCP `pz-live`:

| Pergunta | Ferramenta |
| :--- | :--- |
| "Isso existe?" (`Languages`, `getCraftingManager`, `Translator.loadFiles`) | `api_exists(name, owner)` |
| Métodos e campos de uma classe, separados em estáticos e de instância | `api_class(name, filter)` |
| Busca por parte do nome | `api_search(query, kind)` |
| Evento existe? Quais argumentos o callback recebe? | `api_event(name)` |
| Campos válidos de `item`, `craftRecipe`, … com exemplo real | `script_fields(block_type, field)` |
| Como o jogo usa isso de verdade (arquivo:linha) | `vanilla_examples(symbol)` |

Se o índice estiver faltando ou velho: `python 07-PZ-API-Knowledge/build_index.py` (~10 s). Para conferir o índice: `python 07-PZ-API-Knowledge/index_check.py`.

Exemplo real de chute errado: `Languages.instance:getByName("EN")` não existe (`Languages` não é exposto ao Lua). O certo é percorrer `Translator.getAvailableLanguage()` comparando `:name()`. **[índice + lab]**

## 2. Como o Lua enxerga o Java

- Uma classe exposta vira uma tabela global com **só os métodos estáticos**, `new` (se houver construtor público) e `.class`. Métodos de instância só existem no objeto: `getScriptManager():getItem(...)`, nunca `ScriptManager.getItem`. **[índice + lab]**
- Estático com ponto (`Translator.loadFiles()`), instância com dois-pontos (`recipe:getInputs()`). O `api_class` e o campo `call` das respostas já mostram a forma certa. **[índice]**
- Para testar se um método existe sem chamá-lo: `obj.metodo ~= nil`. Chamar um método inexistente com `:` dá erro "tried to call nil". **[lab]**
- `pairs()` não funciona em objetos Java (userdata). **[lab]**
- Muitos getters devolvem objetos Java, não strings: `item:getItemType()` precisa de `tostring()` (dá `base:drainable`). **[lab]**

## 3. Estrutura de um mod B42

```text
<ModId>/
├── common/
│   ├── mod.info                                   # id, name, versionMin=42.21
│   └── media/lua/shared/Translate/<LANG>/*.json   # traduções
└── 42/media/
    ├── lua/{shared,server,client}/*.lua
    └── scripts/*.txt                              # item, craftRecipe, ...
```

- Funciona só com `common/mod.info`, sem `42/mod.info`. **[lab]**
- Traduções em JSON: `ItemName.json` com chave `"Modulo.Item"` (ex.: `"ZBLabTest.LabSample": "Lab Sample"`). **[lab]** A chave de `Recipes.json` (nome da receita sem módulo) **[não verificado]**.
- Para começar um mod: `scaffold_mod(mod_id, name)` cria o esqueleto em `06-PZ-Lab-Headless/mods/`. Ele já cria com `versionMin=42.21`.
- Modelo completo e testado: `06-PZ-Lab-Headless/mods/ZBLabTest/`.

## 4. Scripts

Item e receita, no formato que o servidor aceitou **[lab]**:

```text
module MeuMod
{
    imports { Base }

    item MeuItem
    {
        DisplayCategory = Material,
        ItemType = base:drainable,
        Weight = 0.2,
        Icon = Thread,
        UseDelta = 0.1,
    }

    craftRecipe FazerMeuItem
    {
        timedAction = Making,
        time = 20,
        Tags = InHandCraft,
        category = Miscellaneous,
        inputs
        {
            item 2 [Base.Paperclip],
            item 1 [Base.Scissors] mode:keep,
        }
        outputs
        {
            item 1 MeuMod.MeuItem,
        }
    }
}
```

- Para qualquer outro campo ou forma de linha (`flags[...]`, `tags[...]`, `mappers[...]`, fluidos), consulte `script_fields`. Ele traz a linha real do vanilla. **[índice]**
- Receita de mod se busca **com o módulo**: `getScriptManager():getCraftRecipe("MeuMod.FazerMeuItem")`. Só o nome devolve `nil`. As receitas vanilla funcionam com ou sem `Base.`. **[lab]**
- O tempo da ação vem de `recipe:getTimedActionScript()`. Não existem `getTimedAction` nem `getTimedActionName`. **[índice + lab]**

## 5. Ciclo de teste no laboratório

1. `lab_start()`, ~45 s na primeira vez. Carrega todos os mods de `06-PZ-Lab-Headless/mods/`.
2. Mudou **Lua**: `reload_lua("Arquivo.lua")`, sem reiniciar. Mudou **script, tradução ou mod.info**: `lab_restart()`.
3. `run_lua_test("tests/meu_teste.lua")` roda o teste no servidor.
4. `lua_errors()` mostra os erros do log, agrupados e já sem o ruído conhecido do boot.
5. `lua_exec("expressão")` serve para explorar ao vivo. `lua_inspect(expr)` mostra os métodos e campos de um objeto.
6. `lab_stop()` no final. O servidor usa ~2,5 GB de RAM.

Testes seguem o padrão de `06-PZ-Lab-Headless/tests/README.md`: devolvem `{ ok, summary, report, checks = {{name, ok, soft, detail}} }`, com cada verificação em `pcall`. Use `soft = true` para o que é só aviso.

## 6. Limites do servidor sem tela

- Não existe jogador (`IsoPlayer`). Não dá para executar a receita de verdade, nem testar skills, XP, interface, menus de contexto, Viewpoint, shaders ou eventos de jogador. Esses casos precisam do cliente. **[lab]**
- Traduções de mod não aparecem no boot do servidor, porque o Translator carrega antes dos mods. Para testar, chame `Translator.loadFiles()` e depois `Translator.getItemNameFromFullType("Mod.Item")`. **[lab]**
- O lab força o idioma inglês (`-Duser.language=en`) para os testes darem sempre o mesmo resultado. **[lab]**
- `getActivatedMods()`, `instanceItem(...)` e `ItemContainer.new()` funcionam sem jogador. **[lab]**

## 7. Nunca

- Gravar na pasta do jogo (`C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid`) ou em `C:\Users\micro\Zomboid`. O lab usa `06-PZ-Lab-Headless/runtime/`.
- Versionar dados extraídos do jogo (`07-PZ-API-Knowledge/data/` é ignorado pelo git).
