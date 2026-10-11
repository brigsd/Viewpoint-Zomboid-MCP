-- comentario com getFake() e Events.OnFake.Add(x)
ISDemo = ISPanel:derive("ISDemo")
ISDemoHelper = {}

local function localHelper(a, cb)
    cb(a)
    return localHelper2(a)
end

function ISDemo:render()
    local sm = getScriptManager()
    local recipe = sm:getCraftRecipe("Base.Foo")
    self:drawText(getText("UI_Demo"), 0, 0)
    local text = "isto nao e chamada: fakeCall(1) e Events.OnString.Add(x)"
    --[[ bloco
       comentado: getBlockComment() ]]
    local long = [[ texto longo com longCall() ]]
    local item = instanceItem("Base.Paperclip")
    Translator.loadFiles()
    table.insert(list, item)
end

function ISDemoHelper.doThing(player, item)
    if isClient() then
        triggerEvent("OnDemoThing", player)
    end
end

local function onStart()
    print("start")
end

Events.OnServerStarted.Add(onStart)
Events.OnTick.Add(function() ISDemoHelper.doThing(nil, nil) end)
Events.OnTick.Remove(onStart)
