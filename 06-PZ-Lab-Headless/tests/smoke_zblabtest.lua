-- smoke_zblabtest.lua
-- Teste de fumaca (server-side, headless) do mod ZBLabTest.
--
-- Executado via MCP `run_lua_test(path)` -> POST /lua do ZombieBuddy.
-- Roda no servidor dedicado SEM jogador: nenhum IsoPlayer e usado. So APIs de script/inventario.
--
-- Convencao de retorno (ver tests/README.md):
--   return { ok=bool, test=string, total=n, passed=n, failed=n, softFailed=n,
--            summary=string, report=string, checks={ {name=,ok=,soft=,detail=}, ... } }
--
--   * `ok` so e false se algum check "hard" falhar. Checks "soft" (soft=true) sao informativos:
--     falha neles aparece em `softFailed`/`report`, mas nao reprova o teste.
--   * `summary` e `report` sao strings: continuam completas mesmo se o HTTP serializar com depth=1
--     (o LuaHandler do ZombieBuddy usa depth=1 por padrao e troca tabelas aninhadas por "[table]").
--     Para ver `checks` por completo, chame /lua?depth=4 (ou maior).

local TEST_NAME = "smoke_zblabtest"

local ITEM_FULL   = "ZBLabTest.LabSample"
local RECIPE_NAME = "MakeLabSample"

local checks = {}
local passed, failed, softFailed = 0, 0, 0

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- Registra um check. `fn` retorna (okBoolean, detail). Qualquer erro Lua/Java vira falha.
-- soft=true => check informativo (nao reprova o teste).
local function check(name, soft, fn)
    local okCall, okVal, detail = pcall(fn)
    local ok, msg
    if not okCall then
        ok = false
        msg = "EXCECAO: " .. tostring(okVal)
    else
        ok = (okVal == true)
        msg = detail ~= nil and tostring(detail) or ""
    end
    checks[#checks + 1] = { name = name, ok = ok, soft = soft and true or false, detail = msg }
    if ok then
        passed = passed + 1
    elseif soft then
        softFailed = softFailed + 1
    else
        failed = failed + 1
    end
end

local function approx(a, b, eps)
    return type(a) == "number" and type(b) == "number" and math.abs(a - b) <= (eps or 0.0001)
end

-- Converte java.util.List (ArrayList/Set) em tabela Lua (indices Java 0-based).
local function listToTable(list)
    local t = {}
    if list == nil then return t end
    for i = 0, list:size() - 1 do
        t[#t + 1] = list:get(i)
    end
    return t
end

local function join(t, sep)
    local parts = {}
    for i = 1, #t do parts[i] = tostring(t[i]) end
    return table.concat(parts, sep or ", ")
end

-- Nomes completos (Module.Type) dos Items de script de uma lista de Item.
local function itemFullNames(javaList)
    local names = {}
    for _, it in ipairs(listToTable(javaList)) do
        names[#names + 1] = it:getFullName()
    end
    return names
end

local function contains(t, v)
    for i = 1, #t do if t[i] == v then return true end end
    return false
end

-- Cache de estado compartilhado entre checks (preenchido pelos primeiros checks).
local state = {}

-- ---------------------------------------------------------------------------
-- 1. Mod ativo e Lua do mod executado
-- ---------------------------------------------------------------------------

check("mod_active", false, function()
    local mods = listToTable(getActivatedMods())
    local found = false
    for _, id in ipairs(mods) do
        if string.find(tostring(id), "ZBLabTest") then found = true end
    end
    return found, "mods ativos: [" .. join(mods) .. "]"
end)

check("lua_marker_loaded", false, function()
    if type(ZBLabTest) ~= "table" then
        return false, "global ZBLabTest ausente (type=" .. type(ZBLabTest) .. ")"
    end
    return ZBLabTest.loaded == true and ZBLabTest.version == "0.1",
        "loaded=" .. tostring(ZBLabTest.loaded) .. " version=" .. tostring(ZBLabTest.version)
end)

check("lua_function_callable", false, function()
    return ZBLabTest.sum(2, 3) == 5, "ZBLabTest.sum(2,3)=" .. tostring(ZBLabTest.sum(2, 3))
end)

check("lua_server_file_ran", false, function()
    return ZBLabTest.serverLuaLoaded == true, "serverLuaLoaded=" .. tostring(ZBLabTest.serverLuaLoaded)
end)

-- Diagnosticos (soft): eventos e contexto de execucao.
check("ctx_is_server", true, function()
    return isServer() == true, "isServer()=" .. tostring(isServer()) ..
        " sharedLoadedAs=" .. tostring(ZBLabTest and ZBLabTest.sharedLoadedAs)
end)

check("event_on_server_started_fired", true, function()
    return ZBLabTest.serverStarted == true, "serverStarted=" .. tostring(ZBLabTest.serverStarted)
end)

-- ---------------------------------------------------------------------------
-- 2. Item (script)
-- ---------------------------------------------------------------------------

check("item_script_exists", false, function()
    local item = getScriptManager():getItem(ITEM_FULL)
    state.itemScript = item
    return item ~= nil, "getItem(" .. ITEM_FULL .. ") -> " .. tostring(item)
end)

check("item_script_names", false, function()
    local item = state.itemScript
    if not item then return false, "sem item (check anterior falhou)" end
    local ok = item:getFullName() == ITEM_FULL
        and item:getModuleName() == "ZBLabTest"
        and item:getName() == "LabSample"
    return ok, "fullName=" .. tostring(item:getFullName()) ..
        " module=" .. tostring(item:getModuleName()) .. " name=" .. tostring(item:getName())
end)

check("item_script_type_drainable", false, function()
    local item = state.itemScript
    if not item then return false, "sem item" end
    local t = tostring(item:getItemType())
    return string.find(string.lower(t), "drainable") ~= nil, "getItemType()=" .. t
end)

check("item_script_weight", false, function()
    local item = state.itemScript
    if not item then return false, "sem item" end
    return approx(item:getActualWeight(), 0.2), "getActualWeight()=" .. tostring(item:getActualWeight())
end)

check("item_script_useDelta", false, function()
    local item = state.itemScript
    if not item then return false, "sem item" end
    return approx(item:getUseDelta(), 0.1), "getUseDelta()=" .. tostring(item:getUseDelta())
end)

check("item_script_display_category", true, function()
    local item = state.itemScript
    if not item then return false, "sem item" end
    return item:getDisplayCategory() == "Material", "getDisplayCategory()=" .. tostring(item:getDisplayCategory())
end)

check("item_script_icon", true, function()
    local item = state.itemScript
    if not item then return false, "sem item" end
    return item:getIcon() == "Thread", "getIcon()=" .. tostring(item:getIcon())
end)

check("item_display_name_translated", true, function()
    local item = state.itemScript
    if not item then return false, "sem item" end
    local name = item:getDisplayName()
    return name == "Lab Sample", "getDisplayName()=" .. tostring(name) ..
        " (se vier o ID cru, o JSON de traducao do mod nao foi lido no servidor)"
end)

check("negative_control_missing_item", false, function()
    -- Controle negativo: garante que getItem() nao devolve algo para qualquer string.
    local item = getScriptManager():getItem("ZBLabTest.DoesNotExist")
    return item == nil, "getItem(ZBLabTest.DoesNotExist) -> " .. tostring(item)
end)

-- ---------------------------------------------------------------------------
-- 3. Item (instancia + container sem jogador)
-- ---------------------------------------------------------------------------

check("item_instantiate", false, function()
    local inst = instanceItem(ITEM_FULL)
    state.instance = inst
    if not inst then return false, "instanceItem retornou nil" end
    local ok = inst:getFullType() == ITEM_FULL
        and inst:getType() == "LabSample"
        and inst:getModule() == "ZBLabTest"
    return ok, "fullType=" .. tostring(inst:getFullType()) ..
        " type=" .. tostring(inst:getType()) .. " module=" .. tostring(inst:getModule())
end)

check("item_instance_is_drainable", false, function()
    local inst = state.instance
    if not inst then return false, "sem instancia" end
    local isDrainable = instanceof(inst, "DrainableComboItem")
    local okUses, uses = pcall(function() return inst:getCurrentUsesFloat() end)
    return isDrainable == true and approx(inst:getUseDelta(), 0.1),
        "instanceof(DrainableComboItem)=" .. tostring(isDrainable) ..
        " useDelta=" .. tostring(inst:getUseDelta()) ..
        " currentUsesFloat=" .. (okUses and tostring(uses) or "n/a")
end)

check("container_without_player", false, function()
    -- ItemContainer.new() sem square/objeto/jogador; mesmo padrao do vanilla
    -- (client/FeedingTrough/ISUI/ISFeedingTroughMenu.lua:171).
    local c = ItemContainer.new()
    state.container = c
    local added = c:AddItem(ITEM_FULL)
    local items = c:getItems()
    local ok = added ~= nil and items:size() == 1 and items:get(0):getFullType() == ITEM_FULL
    return ok, "size=" .. tostring(items:size()) .. " added=" .. tostring(added)
end)

check("container_contains_with_module", false, function()
    local c = state.container
    if not c then return false, "sem container" end
    return c:containsWithModule(ITEM_FULL) == true, "containsWithModule(" .. ITEM_FULL .. ")"
end)

-- ---------------------------------------------------------------------------
-- 4. craftRecipe (script)
-- ---------------------------------------------------------------------------

-- ScriptManager aceita nome com ou sem modulo? Tentamos ambos e registramos qual funcionou.
check("recipe_exists", false, function()
    local sm = getScriptManager()
    local withModule = sm:getCraftRecipe("ZBLabTest." .. RECIPE_NAME)
    local bare = sm:getCraftRecipe(RECIPE_NAME)
    state.recipe = withModule or bare
    return state.recipe ~= nil, "getCraftRecipe('ZBLabTest." .. RECIPE_NAME .. "')=" .. tostring(withModule) ..
        " | getCraftRecipe('" .. RECIPE_NAME .. "')=" .. tostring(bare)
end)

check("recipe_basic_fields", false, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local ok = r:getName() == RECIPE_NAME
        and r:getTime() == 20
        and r:getCategory() == "Miscellaneous"
        and r:needToBeLearn() == false
    return ok, "name=" .. tostring(r:getName()) .. " time=" .. tostring(r:getTime()) ..
        " category=" .. tostring(r:getCategory()) .. " needToBeLearn=" .. tostring(r:needToBeLearn())
end)

check("recipe_in_hand_craft", true, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    return r:isInHandCraftCraft() == true, "isInHandCraftCraft()=" .. tostring(r:isInHandCraftCraft()) ..
        " tags=[" .. join(listToTable(r:getTags())) .. "]"
end)

check("recipe_counts", false, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local nIn, nOut = r:getInputs():size(), r:getOutputs():size()
    return nIn == 3 and nOut == 1, "inputs=" .. tostring(nIn) .. " outputs=" .. tostring(nOut)
end)

-- Mapeia cada input pelo primeiro item possivel (independe da ordem das linhas).
-- Resultado: byItem["Base.Paperclip"] = InputScript
check("recipe_inputs_content", false, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local byItem, desc = {}, {}
    for _, input in ipairs(listToTable(r:getInputs())) do
        local names = itemFullNames(input:getPossibleInputItems())
        desc[#desc + 1] = "[" .. join(names, ";") .. "] x" .. tostring(input:getIntAmount()) ..
            (input:isKeep() and " keep" or "")
        for _, n in ipairs(names) do byItem[n] = input end
    end
    state.inputsByItem = byItem
    local paper, twigs, scissors = byItem["Base.Paperclip"], byItem["Base.Twigs"], byItem["Base.Scissors"]
    local ok = paper ~= nil and twigs ~= nil and scissors ~= nil
        and paper:getIntAmount() == 2 and paper:isKeep() == false
        and twigs:getIntAmount() == 1 and twigs:isKeep() == false
        and scissors:getIntAmount() == 1 and scissors:isKeep() == true
    return ok, join(desc, " | ")
end)

check("recipe_output_content", false, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local out = r:getOutputs():get(0)
    local names = itemFullNames(out:getPossibleResultItems())
    return #names == 1 and names[1] == ITEM_FULL and out:getIntAmount() == 1,
        "outputs=[" .. join(names, ";") .. "] x" .. tostring(out:getIntAmount())
end)

check("recipe_listed_in_all_craft_recipes", true, function()
    local all = getScriptManager():getAllCraftRecipes()
    local found, count = nil, all:size()
    for i = 0, count - 1 do
        local r = all:get(i)
        if r:getName() == RECIPE_NAME then found = r break end
    end
    if not found then return false, "nao achada em getAllCraftRecipes() (total=" .. tostring(count) .. ")" end
    return found:isVanilla() == false, "total=" .. tostring(count) ..
        " isVanilla=" .. tostring(found:isVanilla()) ..
        " modID=" .. tostring(found:getModID()) .. " modName=" .. tostring(found:getModName())
end)

check("recipe_translated_name", true, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local n = r:getTranslationName()
    return n == "Make Lab Sample", "getTranslationName()=" .. tostring(n)
end)

check("negative_control_missing_recipe", false, function()
    local r = getScriptManager():getCraftRecipe("ZBLabTest.NoSuchRecipe")
    return r == nil, "getCraftRecipe(ZBLabTest.NoSuchRecipe) -> " .. tostring(r)
end)

-- ---------------------------------------------------------------------------
-- 5. Avaliacao da receita contra inventario (sem jogador)
-- ---------------------------------------------------------------------------

-- Parte "dados puros" (hard): cada InputScript aceita os itens certos e rejeita os errados.
check("recipe_inputs_accept_script_items", false, function()
    local by = state.inputsByItem
    if not by then return false, "sem mapa de inputs" end
    local sm = getScriptManager()
    local paperItem, twigsItem = sm:getItem("Base.Paperclip"), sm:getItem("Base.Twigs")
    local scissorsItem, nailsItem = sm:getItem("Base.Scissors"), sm:getItem("Base.Nails")
    local pos = by["Base.Paperclip"]:containsItem(paperItem)
        and by["Base.Twigs"]:containsItem(twigsItem)
        and by["Base.Scissors"]:containsItem(scissorsItem)
    -- controle negativo: Nails nao e ingrediente desta receita
    local neg = by["Base.Paperclip"]:containsItem(nailsItem)
        or by["Base.Twigs"]:containsItem(nailsItem)
        or by["Base.Scissors"]:containsItem(nailsItem)
    return pos == true and neg == false, "positivos=" .. tostring(pos) .. " nailsAceito(deve ser false)=" .. tostring(neg)
end)

-- Parte "avaliacao real" (soft): usa CraftRecipeManager com character=nil.
-- Pode falhar em algumas versoes se alguma flag exigir um IsoGameCharacter -> por isso soft.
check("recipe_manager_validates_items_nochar", true, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local inv = ItemContainer.new()
    local paper = inv:AddItem("Base.Paperclip")
    local twigs = inv:AddItem("Base.Twigs")
    local scissors = inv:AddItem("Base.Scissors")
    local nails = inv:AddItem("Base.Nails")
    local function valid(item)
        return CraftRecipeManager.isItemValidForRecipe(r, item, nil)
    end
    local vp, vt, vs, vn = valid(paper), valid(twigs), valid(scissors), valid(nails)
    return vp == true and vt == true and vs == true and vn == false,
        "paperclip=" .. tostring(vp) .. " twigs=" .. tostring(vt) ..
        " scissors=" .. tostring(vs) .. " nails(deve ser false)=" .. tostring(vn)
end)

check("recipe_manager_input_script_per_item_nochar", true, function()
    local r = state.recipe
    if not r then return false, "sem receita" end
    local inv = ItemContainer.new()
    local twigs = inv:AddItem("Base.Twigs")
    local input = CraftRecipeManager.getValidInputScriptForItem(r, twigs, nil)
    if not input then return false, "getValidInputScriptForItem(Twigs) -> nil" end
    local names = itemFullNames(input:getPossibleInputItems())
    return contains(names, "Base.Twigs"), "input=[" .. join(names, ";") .. "]"
end)

-- ---------------------------------------------------------------------------
-- Resultado
-- ---------------------------------------------------------------------------

local total = #checks
local lines = {}
for i = 1, total do
    local c = checks[i]
    local tag = c.ok and "PASS" or (c.soft and "WARN" or "FAIL")
    lines[#lines + 1] = "[" .. tag .. "] " .. c.name .. " - " .. c.detail
end

local overallOk = (failed == 0)
local summary = TEST_NAME .. ": " .. (overallOk and "OK" or "FALHOU") ..
    " (" .. tostring(passed) .. "/" .. tostring(total) .. " passaram, " ..
    tostring(failed) .. " falhas, " .. tostring(softFailed) .. " avisos soft)"

print("[ZBLabTest][" .. TEST_NAME .. "] " .. summary)

return {
    ok = overallOk,
    test = TEST_NAME,
    total = total,
    passed = passed,
    failed = failed,
    softFailed = softFailed,
    summary = summary,
    report = table.concat(lines, "\n"),
    checks = checks,
}
