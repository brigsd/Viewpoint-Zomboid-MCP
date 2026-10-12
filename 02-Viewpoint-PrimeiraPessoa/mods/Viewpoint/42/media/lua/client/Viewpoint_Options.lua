











ViewpointOptions = ViewpointOptions or {}


local FIRST_BUTTON = 2


local binds = {}

local pending = {}
local lootSwitch


local pads = {}
local padPending = {}
local looks = {}

local function keys()
    return Viewpoint and Viewpoint.Keys
end

local function padApi()
    return Viewpoint and Viewpoint.Pads
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

local function padCurrent(pad)
    return padPending[pad.id] or pad.shown or padApi().get(pad.id)
end



local function padShow(pad, text)
    local button = pad.option.element
    if type(button) ~= "table" or not button.setTitle then return end
    local p = padApi()
    local warning = p.warning(pad.id, text)
    local chord = text == "" and "None" or p.display(text)
    button:setTitle((warning ~= "" and "! " or "") .. p.label(pad.id) .. ": " .. chord)
    button:setWidthToTitle()
    button:setTooltip((warning ~= "" and warning .. " <LINE> " or "") .. p.tooltip(pad.id))
    local glyph = p.glyph(text)
    pad.glyph = glyph ~= "" and getTexture(glyph) or nil
    if pad.drawn == button then return end
    pad.drawn = button
    local render = button.render
    function button:render()
        render(self)
        if pad.glyph then self:drawTextureScaledAspect(pad.glyph, self.width + 6, 0, self.height, self.height, 1, 1, 1, 1) end
    end
end

local function padChoose(pad, text)
    padPending[pad.id] = text
    padShow(pad, text)
    if MainOptions.instance then MainOptions.instance.gameOptions.changed = true end
end

local function onPadButton(_, _, id)
    local pad = pads[id]
    if not pad or not ViewpointPadDialog then return end
    ViewpointPadDialog.show(id, padCurrent(pad), function(text) padChoose(pad, text) end)
end


local function padSync()
    local p = padApi()
    if not p then return end
    padPending = {}
    for _, pad in pairs(pads) do
        pad.shown = p.get(pad.id)
        padShow(pad, pad.shown)
    end
    for id, option in pairs(looks) do
        local value = p.lookValue(id)
        if p.lookToggle(id) then option:setValue(value ~= 0) else option:setValue(value) end
    end
end

local function padApply()
    local p = padApi()
    if not p then return end
    for id, text in pairs(padPending) do p.set(id, text) end
    for id, option in pairs(looks) do
        local element = option.element
        if element and p.lookToggle(id) then
            p.lookSet(id, element:isSelected(1) and 1 or 0)
        elseif element then
            p.lookSet(id, element:getCurrentValue())
        end
    end
    padSync()
end

local function addController(page)
    local p = padApi()
    if not p then return end
    page:addTitle("Controller")
    for i = 0, p.count() - 1 do
        local id = p.id(i)
        pads[id] = { id = id, option = page:addButton(id, p.label(id), p.tooltip(id), onPadButton, nil, id) }
    end
    for i = 0, p.lookCount() - 1 do
        local id = p.lookId(i)
        if p.lookToggle(id) then
            looks[id] = page:addTickBox(id, p.lookLabel(id), p.lookValue(id) ~= 0, p.lookTooltip(id))
        else
            looks[id] = page:addSlider(id, p.lookLabel(id), p.lookMin(id), p.lookMax(id), p.lookStep(id),
                p.lookValue(id), p.lookTooltip(id))
        end
    end
end

local function sendLoot()
    if lootSwitch and Viewpoint and Viewpoint.Loot then Viewpoint.Loot.setEnabled(lootSwitch:getValue()) end
end

local function apply()
    sendLoot()
    padApply()
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
        if keys().waits(key) then return end
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
        local bind = ours(self)
        if not bind then return mouse(self, button) end
        if button < FIRST_BUTTON then return end
        self:destroy()
        choose(bind, keys().captured(Mouse.BTN_OFFSET + button))
    end
end



local function wrapOptions()
    local build, relabel = MainOptions.addModOptionsPanel, MainOptions.onKeyboardLayoutChanged

    function MainOptions:addModOptionsPanel()
        build(self)
        sync()
        padSync()
    end

    function MainOptions:onKeyboardLayoutChanged()
        relabel(self)
        sync()
        padSync()
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
    addController(page)
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
