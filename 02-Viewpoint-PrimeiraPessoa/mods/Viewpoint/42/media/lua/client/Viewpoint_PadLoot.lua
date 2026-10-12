





ViewpointPadLoot = ViewpointPadLoot or {}

local function pads()
    return Viewpoint and Viewpoint.Pads
end


local function takes(controller, button)
    local p = pads()
    if not p or not p.menuPress(controller.id, button) then return false end
    controller.viewpointMenu = controller.viewpointMenu or {}
    controller.viewpointMenu[button] = true
    return true
end

local function taken(controller, button)
    return controller.viewpointMenu ~= nil and controller.viewpointMenu[button] == true
end

local function released(controller, button)
    if not taken(controller, button) then return false end
    controller.viewpointMenu[button] = nil
    return true
end



local dpad = {}

local function wrapController()
    local C = JoypadControllerData
    local press, hold, release = C.onPressButton, C.onHoldButton, C.onReleaseButton

    function C:onPressButton(button)
        if dpad[button] then
            if taken(self, button) then return end
        elseif takes(self, button) then
            return
        end
        press(self, button)
    end

    function C:onHoldButton(button, time)
        if taken(self, button) then return end
        hold(self, button, time)
    end

    function C:onReleaseButton(button)
        if released(self, button) then return end
        release(self, button)
    end


    for _, dir in ipairs({ "Up", "Down", "Left", "Right" }) do
        local onPress, onRelease = C["onPress" .. dir], C["onRelease" .. dir]
        local button = JoypadButton["DPad" .. dir]
        dpad[button] = true
        C["onPress" .. dir] = function(self)
            if takes(self, button) then return end
            onPress(self)
        end
        C["onRelease" .. dir] = function(self)
            if released(self, button) then return end
            onRelease(self)
        end
    end
end

local function install()
    if ViewpointPadLoot.installed or not JoypadControllerData or not JoypadButton then return end
    ViewpointPadLoot.installed = true
    wrapController()
end

install()
Events.OnGameBoot.Add(install)
