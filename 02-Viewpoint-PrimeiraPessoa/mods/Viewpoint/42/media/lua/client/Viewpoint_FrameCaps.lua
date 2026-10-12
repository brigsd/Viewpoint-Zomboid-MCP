




local RATES_PAST_THE_GAMES = { 540, 480, 360, 300, 280 }
local UNCAPPED, FOLLOW = 0, -1

local function bridge()
    return Viewpoint and Viewpoint.FrameCaps
end



local function rates(gameCombo)
    local out, listed = {}, {}
    local function add(fps)
        if fps and fps > 0 and fps <= bridge().most() and not listed[fps] then
            out[#out + 1] = fps
            listed[fps] = true
        end
    end
    for _, fps in ipairs(RATES_PAST_THE_GAMES) do add(fps) end
    for i = 1, #gameCombo.options do add(tonumber(gameCombo:getOptionText(i))) end
    add(bridge().refreshRate())
    table.sort(out, function(a, b) return a > b end)
    return out
end

local function fill(combo, firsts, list)
    combo.options = {}
    combo.selected = 0
    for _, first in ipairs(firsts) do combo:addOptionWithData(first.text, first.cap) end
    for _, fps in ipairs(list) do combo:addOptionWithData(tostring(fps), fps) end
end


local function show(combo, cap)
    local best, gap = 1, math.huge
    for i = 1, #combo.options do
        local data = combo:getOptionData(i)
        if data == cap then combo.selected = i return end
        if data > 0 and cap > 0 and math.abs(data - cap) < gap then best, gap = i, math.abs(data - cap) end
    end
    combo.selected = best
end

local function findOption(options, name)
    for _, option in ipairs(options.options) do
        if option.name == name then return option end
    end
end


local function attach(page, gameCombo, menuCombo)
    local list = rates(gameCombo)
    local uncapped = getText("UI_optionscreen_Uncapped")
    fill(gameCombo, { { text = uncapped, cap = UNCAPPED } }, list)
    fill(menuCombo, { { text = "Same as in-game", cap = FOLLOW }, { text = uncapped, cap = UNCAPPED } }, list)

    local gameOption = findOption(page.gameOptions, "framerate")
    function gameOption.toUI(option)
        local cap = bridge().gameCap()
        if cap < 0 then
            cap = getPerformance():isFramerateUncapped() and UNCAPPED or getPerformance():getFramerate()
        end
        show(option.control, cap)
    end


    function gameOption.apply(option)
        local cap = option.control:getOptionData(option.control.selected)
        if cap ~= bridge().gameCap() then bridge().setGameCap(cap) end
    end

    local menuOption = GameOption:new("viewpointMenuFramerate", menuCombo)
    function menuOption.toUI(option)
        show(option.control, bridge().menuCap())
    end
    function menuOption.apply(option)
        bridge().setMenuCap(option.control:getOptionData(option.control.selected))
    end
    page.gameOptions:add(menuOption)
end


local function install()
    if not MainOptions or MainOptions.viewpointFrameCaps or not bridge() or not bridge().active() then return end
    MainOptions.viewpointFrameCaps = true
    local buildDisplayPage = MainOptions.addDisplayPanel

    function MainOptions:addDisplayPanel()
        local framerateLabel = getText("UI_optionscreen_framerate")
        local classAddCombo = MainOptions.addCombo
        local gameCombo, menuCombo
        self.addCombo = function(page, x, y, w, h, name, options, selected, target, onchange)
            local combo = classAddCombo(page, x, y, w, h, name, options, selected, target, onchange)
            if name == framerateLabel and not gameCombo then
                gameCombo = combo
                menuCombo = classAddCombo(page, x, y, w, h, "Menu framerate", {}, 1, target, onchange)
            end
            return combo
        end
        buildDisplayPage(self)
        self.addCombo = nil
        if gameCombo then attach(self, gameCombo, menuCombo) end
    end
end

install()
Events.OnGameBoot.Add(install)
