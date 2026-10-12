







ViewpointPad = ViewpointPad or {}

local ICONS = {
    first = "media/ui/viewpoint/view_first.png",
    third = "media/ui/viewpoint/view_third.png",
    isometric = "media/ui/viewpoint/view_isometric.png",
}
local LABELS = { first = "First person", third = "Third person", isometric = "Isometric view" }

local ROW, GLYPH, INDENT, GAP = 32, 32, 16, 11


local promptText, promptRows = nil, {}

local function view()
    return Viewpoint and Viewpoint.View
end


local function cycle()
    local v = view()
    if v then v.cycle() end
end

local function wrapWheel()
    local add = ISBackButtonWheel.addCommands

    function ISBackButtonWheel:addCommands()
        add(self)
        local v = view()
        if not v or self.playerNum ~= 0 then return end
        local to = v.next()
        self:addSlice(LABELS[to] or to, getTexture(ICONS[to]), cycle)
    end
end


local function rowsOf(text)
    if text == promptText then return promptRows end
    promptText, promptRows = text, {}
    for line in string.gmatch(text, "[^\n]+") do
        local glyphs, words = line:match("^(.-)|(.*)$")
        local textures = {}
        for path in string.gmatch(glyphs or "", "[^,]+") do
            local texture = getTexture(path)
            if texture then table.insert(textures, texture) end
        end
        table.insert(promptRows, { textures = textures, words = words or "" })
    end
    return promptRows
end


local function drawPrompts(prompt)
    local pads = Viewpoint and Viewpoint.Pads
    if not pads or prompt.player ~= 0 or not prompt.y1 or getFocusForPlayer(0) ~= nil then return end
    local joypad = JoypadState.players[1]
    if not joypad or not joypad.player or not isJoypadConnected(joypad.id) then return end
    local text = pads.prompts()
    if text == "" then return end
    local fontHgt = getTextManager():getFontFromEnum(UIFont.NewLarge):getLineHeight()
    local left = prompt.x1 + prompt.lmargin + INDENT
    for i, row in ipairs(rowsOf(text)) do
        local top = prompt.y1 - ROW * (i + 1)
        local x = left
        for _, texture in ipairs(row.textures) do
            prompt:drawTextureScaledAspect(texture, x, top, GLYPH, GLYPH, 0.9, 1, 1, 1)
            x = x + GLYPH
        end
        prompt:drawText(row.words, x + GAP, top + (ROW - fontHgt) / 2, 1, 1, 1, 0.9, UIFont.NewLarge)
    end
end

local function wrapPrompts()
    local prerender = ISButtonPrompt.prerender

    function ISButtonPrompt:prerender()
        prerender(self)
        drawPrompts(self)
    end
end

local function install()
    if ViewpointPad.installed or not ISBackButtonWheel or not ISButtonPrompt then return end
    ViewpointPad.installed = true
    wrapWheel()
    wrapPrompts()
end

install()
Events.OnGameBoot.Add(install)
