-- ZBLabTest: marcador de "mod Lua carregou" para os testes do PZ Lab Headless.
-- Roda em client e server (pasta shared). Nao depende de IsoPlayer nem de ZombieBuddy.

ZBLabTest = ZBLabTest or {}

ZBLabTest.loaded = true
ZBLabTest.version = "0.1"
ZBLabTest.itemType = "ZBLabTest.LabSample"
ZBLabTest.recipeName = "MakeLabSample"

-- Funcao pura, so para provar que codigo do mod e chamavel via /lua.
function ZBLabTest.sum(a, b)
    return a + b
end

if isServer() then
    ZBLabTest.sharedLoadedAs = "server"
elseif isClient() then
    ZBLabTest.sharedLoadedAs = "client"
else
    ZBLabTest.sharedLoadedAs = "singleplayer"
end

print("[ZBLabTest] shared Lua loaded (v" .. ZBLabTest.version .. ", as " .. ZBLabTest.sharedLoadedAs .. ")")
