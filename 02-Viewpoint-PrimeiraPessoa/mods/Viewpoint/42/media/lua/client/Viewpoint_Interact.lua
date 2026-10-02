








ViewpointInteract = { actions = {} }

local W = ISWorldObjectContextMenu


local function skipped()
    local set = {}
    for _, f in ipairs({ W.onWalkTo, W.onSitOnGround, W.onGrabWItem, W.onGrabHalfWItems, W.onGrabAllWItems,
                         W.onGrabCorpseItem }) do
        if f then set[f] = true end
    end


    for _, t in ipairs({ DebugContextMenu, ISVehicleMenu }) do
        for _, f in pairs(t or {}) do
            if type(f) == "function" then set[f] = true end
        end
    end
    return set
end




local function primary()
    local set = {}
    local A = AnimalContextMenu or {}
    for _, f in ipairs({ W.onOpenCloseWindow, W.onOpenCloseDoor, W.onOpenCloseCurtain, W.onToggleLight,
                         W.onActivateGenerator, W.onToggleStove, A.onMilkAnimal, A.onShearAnimal, A.onPetAnimal,
                         W.onChopTree }) do
        if f then set[f] = true end
    end
    return set
end


local function handler(option)
    if option.onSelect == ISContextMenu.onGetUpAndThen then return option.param1 end
    return option.onSelect
end


local function curtain(object)
    if instanceof(object, "IsoWindow") or instanceof(object, "IsoDoor") or instanceof(object, "IsoThumpable") then
        return object:HasCurtains()
    end
    return nil
end





local function own(object)
    local set = {}
    local barricadable = instanceof(object, "IsoDoor") or instanceof(object, "IsoWindow")
        or instanceof(object, "IsoWindowFrame") or instanceof(object, "IsoThumpable")
    if barricadable and W.onBarricade then set[W.onBarricade] = true end
    return set
end


local function another(v, state)
    return v ~= nil and v ~= state.object and v ~= state.curtain and instanceof(v, "IsoObject")
        and not instanceof(v, "IsoGameCharacter")
end






local function whose(args, menu, state)
    local other = false
    for i = 1, args.n do
        local v = args[i]
        if v ~= nil and (v == state.object or v == state.curtain) then return true end
        if type(v) == "table" and v ~= state.worldobjects and v ~= menu then
            for _, w in pairs(v) do
                if w == state.object or w == state.curtain then return true end
                other = other or another(w, state)
            end
        else
            other = other or another(v, state)
        end
    end
    if other then return false end
    return nil
end



local function lockedOut(o, state)
    local door = state.object
    return o.notAvailable and handler(o) == W.onOpenCloseDoor
        and (instanceof(door, "IsoDoor") or instanceof(door, "IsoThumpable"))
        and not door:isBarricaded() and (door:isLocked() or door:isLockedByKey())
end



local function keepOwned(out, before)
    for i = before + 1, #out do
        if out[i].mine then return end
    end
    for i = #out, before + 1, -1 do table.remove(out, i) end
end






local function collect(menu, depth, prefix, out, state)
    for i = 1, menu.numOptions - 1 do
        local o = menu.options[i]
        state.seen = (state.seen or 0) + 1
        if o and not o.isDefaultOption and not (state.debugIcon and o.iconTexture == state.debugIcon) then
            local name = prefix and (prefix .. ": " .. o.name) or o.name
            local args = { o.target, o.param1, o.param2, o.param3, o.param4, o.param5, o.param6, o.param7, o.param8,
                           o.param9, o.param10, n = 11 }
            if o.subOption then
                local sub = menu:getSubMenu(o.subOption)
                if sub and not sub:isEmpty() then
                    local before = #out
                    collect(sub, depth + 1, depth >= 1 and name or nil, out, state)
                    if depth == 0 then
                        keepOwned(out, before)
                        for k = before + 1, #out do out[k].group = o.name end
                        if #out > before and not state.title then state.title = o.name end
                    end
                end
            elseif o.onSelect and not state.skip[handler(o)] then
                local mine = state.own[handler(o)] or whose(args, menu, state)
                if mine or mine == nil and depth > 0 then
                    if lockedOut(o, state) then name = name .. " [" .. state.lockedWord .. "]" end
                    table.insert(out, {
                        name = name,
                        fn = o.onSelect,
                        args = args,
                        n = args.n,
                        enabled = not o.notAvailable and not o.isDisabled,
                        first = state.first[handler(o)] == true,
                        mine = mine,
                        menu = true,
                    })
                end
            end
        end
    end
end




local function label(a, title)
    if not a.group or a.group == title then return a.name end
    if a.name == title then return a.group end
    return a.group .. ": " .. a.name
end





local function lightToggle(list, player, object)
    if not instanceof(object, "IsoLightSwitch") then return end
    for _, a in ipairs(list) do
        if a.fn == W.onToggleLight or a.args and a.args[2] == W.onToggleLight then return end
    end
    local name = getText(object:isActivated() and "ContextMenu_Turn_Off" or "ContextMenu_Turn_On")
    table.insert(list, 1, { name = name, fn = W.onToggleLight, args = { nil, object, player:getPlayerNum() }, n = 3,
                            enabled = true, first = true })
end



local function chopTree(worldobjects, playerObj, tree)
    W.doChopTree(playerObj, tree)
end




local function withoutChopCursor(list)
    for _, a in ipairs(list) do
        if a.fn == ISContextMenu.onGetUpAndThen and a.args[2] == W.onChopTree then
            a.args[2] = chopTree
        elseif a.fn == W.onChopTree then
            a.fn = chopTree
        end
    end
end



local function finish(list, title, seen)
    local ordered = {}
    for _, a in ipairs(list) do if a.first then table.insert(ordered, a) end end
    for _, a in ipairs(list) do if not a.first then table.insert(ordered, a) end end
    ViewpointInteract.actions = ordered
    local labels, enabled = {}, {}
    for i, a in ipairs(ordered) do
        labels[i] = a.name
        enabled[i] = a.enabled
    end
    return { title = title, labels = labels, enabled = enabled, seen = seen or #list }
end




local function withoutDebugMenu(build)
    local debug = DebugContextMenu and DebugContextMenu.doDebugMenu
    if debug then DebugContextMenu.doDebugMenu = function() end end
    local ok, result = pcall(build)
    if debug then DebugContextMenu.doDebugMenu = debug end
    return ok, result
end




function ViewpointInteract.harvest(player, object)
    local playerNum = player:getPlayerNum()
    local open = getPlayerContextMenu(playerNum)
    if not open then return { why = "no context menu" } end
    if getCell():getDrag(playerNum) then return { why = "a placement cursor is out" } end
    if open:getIsVisible() then return { why = "the right-click menu is open" } end
    local sq = object:getSquare()
    if not sq then return { why = "not on a square" } end
    local x = isoToScreenX(playerNum, sq:getX(), sq:getY(), sq:getZ())
    local y = isoToScreenY(playerNum, sq:getX(), sq:getY(), sq:getZ())
    local worldobjects = { object }
    local ok, context = withoutDebugMenu(function() return W.createMenu(playerNum, worldobjects, x, y) end)
    local list = {}
    local state = { skip = skipped(), first = primary(), own = own(object), object = object, curtain = curtain(object),
                    worldobjects = worldobjects, debugIcon = getTexture("media/textures/Item_Plumpabug_Left.png"),
                    lockedWord = getText("EC_Locked") }
    if ok and type(context) == "table" then collect(context, 0, nil, list, state) end
    for _, a in ipairs(list) do a.name = label(a, state.title) end
    lightToggle(list, player, object)
    withoutChopCursor(list)

    if not state.title and instanceof(object, "IsoPlayer") then state.title = object:getDisguisedDisplayName() end

    open:hideAndChildren()
    if not ok then error(context) end
    if type(context) ~= "table" then return { why = "the game built no menu (" .. tostring(context) .. ")" } end
    return finish(list, state.title, state.seen or 0)
end



local function seatAt(player, vehicle, part)
    if not part then return vehicle:getBestSeat(player) end
    if not (part:getDoor() and part:getInventoryItem()) then return -1 end
    for seat = 0, vehicle:getMaxPassengers() - 1 do
        if vehicle:getPassengerDoor(seat) == part or vehicle:getPassengerDoor2(seat) == part then return seat end
    end
    return -1
end




local function radialStandIn(list)
    local menu = {
        addSlice = function(self, text, texture, fn, ...)
            table.insert(list, { name = text, fn = fn, args = { ... }, n = select("#", ...), enabled = fn ~= nil })
        end,
        isEmpty = function() return true end,
        isReallyVisible = function() return #list > 0 end,
    }
    return setmetatable(menu, { __index = function() return function() end end })
end




local function radialEntries(player, vehicle)
    local list = {}
    local standIn = radialStandIn(list)
    local radialOf, pick = getPlayerRadialMenu, ISVehicleMenu.getVehicleToInteractWith
    getPlayerRadialMenu = function() return standIn end
    ISVehicleMenu.getVehicleToInteractWith = function() return vehicle end
    local ok, err = pcall(ISVehicleMenu.showRadialMenuOutside, player)
    getPlayerRadialMenu, ISVehicleMenu.getVehicleToInteractWith = radialOf, pick
    if not ok then error(err) end
    return list
end





function ViewpointInteract.harvestVehicle(player, vehicle)
    local list = {}
    local doorPart = vehicle:getUseablePart(player)
    local seat = seatAt(player, vehicle, doorPart)
    local lockedWord = getText("EC_Locked")
    if seat ~= -1 then
        local name = getText("IGUI_EnterVehicle")
        if doorPart and doorPart:getDoor():isLocked() then name = name .. " [" .. lockedWord .. "]" end
        table.insert(list, { name = name, fn = ISVehicleMenu.onEnter,
                             args = { player, vehicle, seat }, n = 3, enabled = true, first = true })
    end
    for _, a in ipairs(radialEntries(player, vehicle)) do
        local door = a.fn == ISVehicleMenu.onOpenDoor or a.fn == ISVehicleMenu.onCloseDoor
        a.first = seat == -1 and door and a.args[2] == doorPart
        if a.fn == ISVehicleMenu.onOpenDoor and a.args[2]:getDoor():isLocked() then
            a.name = a.name .. " [" .. lockedWord .. "]"
        end
        if a.fn ~= ISVehicleMenu.onShowSeatUI then table.insert(list, a) end
    end
    return finish(list, ISVehicleMenu.getVehicleDisplayName(vehicle))
end



function ViewpointInteract.run(player, index)
    local a = ViewpointInteract.actions[index]
    if not a or not a.enabled or not a.fn then return end
    if a.menu then ISContextMenu.globalPlayerContext = player:getPlayerNum() end
    a.fn(unpack(a.args, 1, a.n))
end
