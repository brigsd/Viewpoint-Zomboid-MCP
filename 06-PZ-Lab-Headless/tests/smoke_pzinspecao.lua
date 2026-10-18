-- smoke_pzinspecao.lua
-- Teste server-side (headless, sem jogador) das funcoes puras do mod PZInspecao.
-- Usa objetos falsos com os mesmos metodos de IsoObject (getSquare, getSpriteName,
-- getObjectIndex, getModData). A tecla F6 e a mira ficam de fora: exigem cliente.
--
-- Rodar: python lab/pzlab.py lua --file tests/smoke_pzinspecao.lua
-- Convencao de retorno igual a de smoke_zblabtest.lua.

local TEST_NAME = "smoke_pzinspecao"

local checks = {}
local passed, failed = 0, 0

local function check(name, fn)
    local okCall, okVal, detail = pcall(fn)
    local ok, msg
    if not okCall then
        ok = false
        msg = "EXCECAO: " .. tostring(okVal)
    else
        ok = (okVal == true)
        msg = detail ~= nil and tostring(detail) or ""
    end
    checks[#checks + 1] = { name = name, ok = ok, detail = msg }
    if ok then passed = passed + 1 else failed = failed + 1 end
end

-- Objeto falso: md e a moddata (tabela persistente do teste).
local function fakeObject(sprite, x, y, z, index, md)
    local sq = { getX = function() return x end, getY = function() return y end, getZ = function() return z end }
    return {
        getSquare = function() return sq end,
        getSpriteName = function() return sprite end,
        getObjectIndex = function() return index end,
        getModData = function() return md end,
    }
end

-- ---------------------------------------------------------------------------

check("mod_loaded", function()
    return type(PZInspecao) == "table" and PZInspecao.version == "0.1", "version=" .. tostring(PZInspecao and PZInspecao.version)
end)

check("keyOf_format", function()
    local k = PZInspecao.keyOf("furniture_storage_01_16", 10354, 9876, 0, 3)
    return k == "furniture_storage_01_16|10354,9876,0|3", "key=" .. k
end)

check("keyOf_distinct_index", function()
    local a = PZInspecao.keyOf("s", 1, 2, 0, 0)
    local b = PZInspecao.keyOf("s", 1, 2, 0, 1)
    return a ~= b, "a=" .. a .. " b=" .. b
end)

check("describe_fake_object", function()
    local o = fakeObject("appliances_refrig_01_0", 100, 200, 0, 5, {})
    local d = PZInspecao.describe(o, false)
    local ok = d.sprite == "appliances_refrig_01_0" and d.x == 100 and d.y == 200 and d.z == 0
        and d.index == 5 and d.key == "appliances_refrig_01_0|100,200,0|5" and d.id == nil
    return ok, "key=" .. tostring(d.key) .. " id=" .. tostring(d.id)
end)

check("describe_nil_object", function()
    return PZInspecao.describe(nil, true) == nil, "describe(nil) deve ser nil"
end)

check("ensureId_persists_in_moddata", function()
    local md = {}
    local o = fakeObject("s", 0, 0, 0, 0, md)
    local id1 = PZInspecao.ensureId(o)
    local id2 = PZInspecao.ensureId(o)
    return id1 == id2 and md[PZInspecao.MODDATA_KEY] == id1 and string.sub(id1, 1, 4) == "PZI-",
        "id1=" .. tostring(id1) .. " id2=" .. tostring(id2)
end)

check("ensureId_separate_objects_differ", function()
    local a = PZInspecao.ensureId(fakeObject("s", 0, 0, 0, 0, {}))
    local b = PZInspecao.ensureId(fakeObject("s", 0, 0, 0, 1, {}))
    return a ~= b, "a=" .. tostring(a) .. " b=" .. tostring(b)
end)

check("describe_with_id_reuses_moddata", function()
    local md = { [PZInspecao.MODDATA_KEY] = "PZI-fixo" }
    local d = PZInspecao.describe(fakeObject("s", 1, 1, 0, 0, md), true)
    return d.id == "PZI-fixo", "id=" .. tostring(d.id)
end)

check("describe_without_square", function()
    local o = { getSquare = function() return nil end, getSpriteName = function() return "s" end,
                getObjectIndex = function() return 2 end, getModData = function() return {} end }
    local d = PZInspecao.describe(o, false)
    return d.key == "s|nil,nil,nil|2", "key=" .. tostring(d.key)
end)

-- ---------------------------------------------------------------------------

local lines = {}
for i = 1, #checks do
    local c = checks[i]
    lines[#lines + 1] = "[" .. (c.ok and "PASS" or "FAIL") .. "] " .. c.name .. " - " .. c.detail
end

local overallOk = failed == 0
local summary = TEST_NAME .. ": " .. (overallOk and "OK" or "FALHOU") ..
    " (" .. tostring(passed) .. "/" .. tostring(#checks) .. " passaram, " .. tostring(failed) .. " falhas)"

print("[PZInspecao][" .. TEST_NAME .. "] " .. summary)

return {
    ok = overallOk,
    test = TEST_NAME,
    total = #checks,
    passed = passed,
    failed = failed,
    summary = summary,
    report = table.concat(lines, "\n"),
}
