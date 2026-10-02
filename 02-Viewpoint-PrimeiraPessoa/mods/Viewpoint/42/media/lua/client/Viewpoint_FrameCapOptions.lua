




local FPS_TABLE = { 500, 430, 400, 360, 330, 300, 244, 240, 165, 144, 120, 95, 90, 75, 60, 55, 45, 30, 24 }

local function caps()
    return Viewpoint and Viewpoint.FrameCaps
end

local function fpsLabels(prefix)
    local t = {}
    for _, v in ipairs(prefix) do table.insert(t, v) end
    for _, fps in ipairs(FPS_TABLE) do table.insert(t, tostring(fps)) end
    return t
end

local function indexOfFps(fps, labels)
    for i, label in ipairs(labels) do
        if tonumber(label) == fps then return i end
    end
    return nil
end

local function extendGameOption(option)
    function option.toUI(self)
        local box = self.control
        local fc = caps()
        if (fc and fc.isFramerateUncapped()) or (not fc and getPerformance():isFramerateUncapped()) then
            box.selected = 1
        else
            local currentFps = fc and fc.getGameFramerate() or getPerformance():getFramerate()
            box.selected = indexOfFps(currentFps, box.options) or indexOfFps(60, box.options) or 1
        end
    end
    function option.apply(self)
        local box = self.control
        local fps = tonumber(box.options[box.selected])
        local fc = caps()
        if box.selected == 1 then
            if fc then fc.setGameFramerate(0) else getPerformance():setFramerateUncapped(true) end
        elseif fps then
            if fc then
                fc.setGameFramerate(fps)
            else
                getPerformance():setFramerateUncapped(false)
                getPerformance():setFramerate(fps)
            end
        end
    end
end

local function install()
    if not MainOptions or MainOptions.viewpointMenuFramerate then return end
    MainOptions.viewpointMenuFramerate = true
    local stockAddCombo = MainOptions.addCombo
    local frameLabel = getText("UI_optionscreen_framerate")
    function MainOptions:addCombo(x, y, w, h, name, options, selected, target, onchange)
        if name ~= frameLabel or self.viewpointMenuCombo then
            return stockAddCombo(self, x, y, w, h, name, options, selected, target, onchange)
        end
        local uncappedLabel = getText("UI_optionscreen_Uncapped")
        local combo = stockAddCombo(self, x, y, w, h, name, fpsLabels({ uncappedLabel }), selected, target, onchange)
        local menu = stockAddCombo(self, x, y, w, h, "Menu framerate",
                                   fpsLabels({ "Same as in-game", uncappedLabel }), 1, target, onchange)
        self.viewpointMenuCombo = menu
        local stockAdd = self.gameOptions.add
        self.gameOptions.add = function(opts, option)
            if option and option.name == 'framerate' and option.control == combo then
                extendGameOption(option)
                opts.add = stockAdd
                local r = stockAdd(opts, option)
                local gameOption = GameOption:new('viewpointMenuFramerate', menu)
                function gameOption.toUI(self)
                    local fc = caps()
                    if fc then self.control.selected = fc.getMenuFramerateIndex() end
                end
                function gameOption.apply(self)
                    local box = self.control
                    local fc = caps()
                    if box.options[box.selected] and fc then fc.setMenuFramerateIndex(box.selected) end
                end
                stockAdd(opts, gameOption)
                return r
            end
            return stockAdd(opts, option)
        end
        return combo
    end
end

install()
Events.OnGameBoot.Add(install)
