





require "ISUI/ISPanel"

ViewpointPadDialog = ISPanel:derive("ViewpointPadDialog")

local FONT_HGT = getTextManager():getFontHeight(UIFont.Medium)
local BUTTON_W, BUTTON_H, PAD = 100, 25, 16

local function pads()
    return Viewpoint and Viewpoint.Pads
end


function ViewpointPadDialog:new(id, text, done)
    local w, h = 460, 190
    local o = ISPanel.new(self, (getCore():getScreenWidth() - w) / 2, (getCore():getScreenHeight() - h) / 2, w, h)
    o.id = id
    o.text = text
    o.done = done
    o.moveWithMouse = true
    o.backgroundColor = { r = 0, g = 0, b = 0, a = 0.9 }
    return o
end

function ViewpointPadDialog:createChildren()
    ISPanel.createChildren(self)
    local p = pads()
    if not (p and p.hold(self.id)) then
        self.aiming = ISTickBox:new(PAD, PAD * 2 + FONT_HGT * 2, BUTTON_H, BUTTON_H, "", self, nil)
        self.aiming:initialise()
        self:addChild(self.aiming)
        self.aiming:addOption("While aiming only")
        self.aiming:setSelected(1, p and p.aiming(self.text) or false)
    end
    local y = self.height - PAD - BUTTON_H
    self:addAction(PAD, y, "Default", self.onDefault)
    self:addAction(PAD * 2 + BUTTON_W, y, "Clear", self.onClear)
    self:addAction(self.width - PAD - BUTTON_W, y, getText("UI_Cancel"), self.onCancel)
end

function ViewpointPadDialog:addAction(x, y, title, onClick)
    local button = ISButton:new(x, y, BUTTON_W, BUTTON_H, title, self, onClick)
    button:initialise()
    self:addChild(button)
end

function ViewpointPadDialog:prerender()
    ISPanel.prerender(self)
    local p = pads()
    if not p then return self:close() end
    self:drawTextCentre("Press a button of your pad for", self.width / 2, PAD, 1, 1, 1, 1, UIFont.Medium)
    self:drawTextCentre(p.label(self.id), self.width / 2, PAD + FONT_HGT, 1, 1, 1, 1, UIFont.Medium)
    p.poll()
    if p.capturing(self.id) then return end
    local caught = p.caught()
    if caught ~= "" then
        self:finish(p.withAiming(caught, self.aiming ~= nil and self.aiming:isSelected(1)))
    else
        self:close()
    end
end

function ViewpointPadDialog:onDefault()
    local p = pads()
    self:finish(p and p.fallback(self.id) or "")
end

function ViewpointPadDialog:onClear()
    self:finish("")
end

function ViewpointPadDialog:onCancel()
    self:close()
end


function ViewpointPadDialog:onJoypadDown(button, joypadData)
end

function ViewpointPadDialog:finish(text)
    self:close()
    self.done(text)
end

function ViewpointPadDialog:close()
    local p = pads()
    if p then p.cancel() end
    local joypad = self.joypad
    if joypad and joypad.focus == self then joypad.focus = self.previousFocus end
    self:setVisible(false)
    self:removeFromUIManager()
end


function ViewpointPadDialog.show(id, text, done)
    local p = pads()
    if not p then return end
    local dialog = ViewpointPadDialog:new(id, text, done)
    dialog:initialise()
    dialog:addToUIManager()
    dialog:setAlwaysOnTop(true)
    p.capture(id)

    local joypad = JoypadState and (JoypadState.getMainMenuJoypad() or JoypadState.players[1])
    if joypad then
        dialog.joypad = joypad
        dialog.previousFocus = joypad.focus
        joypad.focus = dialog
    end
end
