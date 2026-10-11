-- ZBLabTest (lado servidor): prova que a pasta lua/server do mod foi executada
-- e que eventos de servidor disparam.

ZBLabTest = ZBLabTest or {}
ZBLabTest.serverLuaLoaded = true
ZBLabTest.serverStarted = false

local function onServerStarted()
    ZBLabTest.serverStarted = true
    print("[ZBLabTest] OnServerStarted fired")
end

Events.OnServerStarted.Add(onServerStarted)

print("[ZBLabTest] server Lua loaded")
