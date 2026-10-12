












ViewpointPadSwap = ViewpointPadSwap or {}


local PUSHED = 0.5

local function pads()
    return Viewpoint and Viewpoint.Pads
end


local function alone()
    local p = pads()
    local playerObj = getSpecificPlayer(0)
    return p ~= nil and p.hotSwap() and playerObj ~= nil and not playerObj:isDead() and getNumActivePlayers() == 1
end

local function onPad()
    return JoypadState.players[1] ~= nil
end



local function takes(controller)
    return alone() and not onPad() and pads().usable(controller.id)
end

local function pushed(controller)
    local id = controller.id
    return controller.up or controller.down or controller.left or controller.right
        or math.abs(getJoypadMovementAxisX(id)) > PUSHED or math.abs(getJoypadMovementAxisY(id)) > PUSHED
        or math.abs(getJoypadAimingAxisX(id)) > PUSHED or math.abs(getJoypadAimingAxisY(id)) > PUSHED
        or isJoypadLTPressed(id) or isJoypadRTPressed(id)
end


local function takeOver(controller, by)
    local playerObj = getSpecificPlayer(0)
    local joypadData = JoypadState.joypads[1]
    if joypadData.listBox then
        joypadData.listBox:removeFromUIManager()
        joypadData.listBox = nil
    end
    joypadData.focus = nil
    joypadData.lastfocus = nil
    JoypadState.players[1] = joypadData
    joypadData:setController(controller)
    joypadData:setActive(true)
    joypadData.player = 0
    setPlayerJoypad(0, controller.id, playerObj, nil, false)
    pads().activate(controller.id)
    createPlayerData(0)
    getPlayerInventory(0):setController(controller.id)
    getPlayerLoot(0):setController(controller.id)
    pads().mouseUsed()
    print("[Viewpoint] pad switch: player 0 on pad " .. tostring(controller.id) .. " (" .. by .. ")")
end


local function giveBack(by)
    JoypadState.useKeyboardMouse()
    createPlayerData(0)
    print("[Viewpoint] pad switch: player 0 on the keyboard and mouse (" .. by .. ")")
end

local function wrapController()
    local press = JoypadControllerData.onPressButton
    local hold = JoypadControllerData.onHoldButton
    local release = JoypadControllerData.onReleaseButton
    local update = JoypadControllerData.update

    function JoypadControllerData:onPressButton(button)
        if takes(self) then
            self.viewpointTook = button
            takeOver(self, "a button")
            return
        end
        press(self, button)
    end

    function JoypadControllerData:onHoldButton(button, time)
        if self.viewpointTook == button then return end
        hold(self, button, time)
    end

    function JoypadControllerData:onReleaseButton(button)
        if self.viewpointTook == button then
            self.viewpointTook = nil
            return
        end
        release(self, button)
    end



    function JoypadControllerData:update(time)
        update(self, time)
        local was = self.viewpointPushed
        self.viewpointPushed = self.connected and pushed(self)
        if self.viewpointPushed and not was and takes(self) then
            takeOver(self, "a stick, trigger or D-pad")
        end
    end
end

local function onKey()
    if alone() and onPad() then giveBack("a key") end
end


local function onRenderTick()
    local p = pads()
    if p and p.mouseUsed() and alone() and onPad() then giveBack("the mouse") end
end

local function install()
    if ViewpointPadSwap.installed or not JoypadControllerData or not JoypadState then return end
    ViewpointPadSwap.installed = true
    wrapController()
    Events.OnKeyStartPressed.Add(onKey)
    Events.OnRenderTick.Add(onRenderTick)
end

install()
Events.OnGameBoot.Add(install)
