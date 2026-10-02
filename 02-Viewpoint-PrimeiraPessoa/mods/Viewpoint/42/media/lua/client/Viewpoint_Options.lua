







ViewpointOptions = ViewpointOptions or {}


local binds = {}

local pending = {}
local lootSwitch

local function keys()
    return Viewpoint and Viewpoint.Keys
end



local function show(bind, text)
    local element = bind.option.element
    if type(element) ~= "table" or not element.btn then return end
    local k = keys()
    element.keyCode = k.trigger(text)
    element.shift = k.holds(text, "SHIFT")
    element.ctrl = k.holds(text, "CTRL")
    element.alt = k.holds(text, "ALT")
    element.btn:setTitle(k.display(text))
end

local function current(bind)
    return pending[bind.id] or bind.shown or keys().get(bind.id)
end

local function choose(bind, text)
    local k = keys()
    for _, other in pairs(binds) do
        if other ~= bind then
            local theirs = current(other)
            local left = k.without(bind.id, text, other.id, theirs)
            if left ~= theirs then
                pending[other.id] = left
                show(other, left)
            end
        end
    end
    pending[bind.id] = text
    show(bind, text)
    if MainOptions.instance then MainOptions.instance.gameOptions.changed = true end
end


local function sync()
    local k = keys()
    if not k then return end
    pending = {}
    for _, bind in pairs(binds) do
        bind.shown = k.get(bind.id)
        show(bind, bind.shown)
    end
end

local function sendLoot()
    if lootSwitch and Viewpoint and Viewpoint.Loot then Viewpoint.Loot.setEnabled(lootSwitch:getValue()) end
end

local function apply()
    sendLoot()
    local k = keys()
    if not k then return end
    for _, bind in pairs(binds) do
        local element = bind.option.element
        local text = pending[bind.id]

        if text == nil and type(element) == "table" and element.keyCode == 0 and bind.shown ~= "" then text = "" end
        if text ~= nil then k.set(bind.id, text) end
    end
    sync()
end

local function ours(dialog)
    return dialog.isModBind and keys() and binds[dialog.keybindName]
end


local function wrapDialog()
    local release, default, clear, mouse = ISSetKeybindDialog.onKeyRelease, ISSetKeybindDialog.onDefault,
        ISSetKeybindDialog.onClear, ISSetKeybindDialog.onMouseButtonDown

    function ISSetKeybindDialog:onKeyRelease(key)
        local bind = ours(self)
        if not bind then return release(self, key) end
        self:destroy()
        if key ~= Keyboard.KEY_ESCAPE then choose(bind, keys().captured(key)) end
    end

    function ISSetKeybindDialog:onDefault()
        local bind = ours(self)
        if not bind then return default(self) end
        self:destroy()
        choose(bind, keys().fallback(bind.id))
    end

    function ISSetKeybindDialog:onClear()
        local bind = ours(self)
        if not bind then return clear(self) end
        self:destroy()
        choose(bind, "")
    end

    function ISSetKeybindDialog:onMouseButtonDown(button)
        if not ours(self) then return mouse(self, button) end
    end
end



local function wrapOptions()
    local build, relabel = MainOptions.addModOptionsPanel, MainOptions.onKeyboardLayoutChanged

    function MainOptions:addModOptionsPanel()
        build(self)
        sync()
    end

    function MainOptions:onKeyboardLayoutChanged()
        relabel(self)
        sync()
    end
end

local function addLootSwitch(page)
    lootSwitch = page:addTickBox("lootMenu", "Show the loot menu", true,
        "In first and third person, what you aim at within reach is outlined and its items listed beside the crosshair. Off: the game's own loot window only.")
end

local function install()
    if ViewpointOptions.page or not (PZAPI and PZAPI.ModOptions and MainOptions and ISSetKeybindDialog) then return end
    local page = PZAPI.ModOptions:create("Viewpoint", "Viewpoint")
    ViewpointOptions.page = page
    local k, group = keys(), nil
    for i = 0, (k and k.count() or 0) - 1 do
        local id = k.id(i)
        if k.group(id) ~= group then
            group = k.group(id)
            page:addTitle(group)
            if k.loot(id) then addLootSwitch(page) end
        end
        local label = k.label(id)
        binds[label] = { id = id, option = page:addKeyBind(id, label, k.trigger(k.fallback(id)), k.tooltip(id)) }
    end
    if not lootSwitch then addLootSwitch(page) end
    page.apply = apply
    wrapOptions()
    wrapDialog()

    Events.OnGameStart.Add(function()
        PZAPI.ModOptions:load()
        sendLoot()
    end)
end

install()
Events.OnGameBoot.Add(install)
