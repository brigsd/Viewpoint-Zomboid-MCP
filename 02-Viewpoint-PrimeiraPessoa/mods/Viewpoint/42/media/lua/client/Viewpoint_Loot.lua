



ViewpointLoot = {}



function ViewpointLoot.explore(player, container)
    ISInventoryPage.checkExplored(nil, container, player)
end



local function fromGround(item, playerNum)
    if item:getWorldItem() == nil then return end
    local floor = ISInventoryPage.GetFloorContainer(playerNum)
    if not floor:contains(item) then floor:AddItem(item) end
end




local function withoutBar(queue)
    local add = ISTimedActionQueue.add
    ISTimedActionQueue.add = function(action)
        action.useProgressBar = false
        return add(action)
    end
    local ok, err = pcall(queue)
    ISTimedActionQueue.add = add
    if not ok then error(err) end
end



function ViewpointLoot.take(player, item)
    if item:isHumanCorpse() and player:getVehicle() then return end
    local playerNum = player:getPlayerNum()
    fromGround(item, playerNum)
    withoutBar(function()
        if isForceDropHeavyItem(item) then
            ISInventoryPaneContextMenu.equipHeavyItem(player, item)
        elseif luautils.walkToContainer(item:getContainer(), playerNum) then
            local into = getPlayerInventory(playerNum).inventory
            local from = item:getContainer()
            ISTimedActionQueue.add(ISInventoryTransferUtil.newInventoryTransferAction(player, item, from, into))
        end
    end)
end


function ViewpointLoot.takeAll(player, items)
    local playerNum = player:getPlayerNum()
    local list, heavy = {}, nil
    for i = 0, items:size() - 1 do
        local item = items:get(i)
        fromGround(item, playerNum)
        if not item:isUnwanted(player) then
            if isForceDropHeavyItem(item) then heavy = item else table.insert(list, item) end
        end
    end
    withoutBar(function()
        if #list == 0 then
            if heavy then ISInventoryPaneContextMenu.equipHeavyItem(player, heavy) end
        elseif luautils.walkToContainer(list[1]:getContainer(), playerNum) then
            getPlayerLoot(playerNum).inventoryPane:transferItemsByWeight(list, getPlayerInventory(playerNum).inventory)
        end
    end)
end



function ViewpointLoot.openWindow(player, container)
    local playerNum = player:getPlayerNum()
    local inventory, loot = getPlayerInventory(playerNum), getPlayerLoot(playerNum)
    if not (inventory and loot) then return end
    ViewpointLoot.shown = loot:getIsVisible()
    inventory:setVisible(true)
    loot:setVisible(true)
    loot:refreshBackpacks()
    local wanted = container or ISInventoryPage.GetFloorContainer(playerNum)
    for _, button in ipairs(loot.backpacks) do
        if button.inventory == wanted then
            loot:selectContainer(button)
            break
        end
    end
    loot.isCollapsed = false
    loot:clearMaxDrawHeight()
    loot.collapseCounter = 0
end


function ViewpointLoot.closeWindow(player)
    local playerNum = player:getPlayerNum()
    local inventory, loot = getPlayerInventory(playerNum), getPlayerLoot(playerNum)
    if not (inventory and loot) then return end
    if ViewpointLoot.shown == false then
        inventory:setVisible(false)
        loot:setVisible(false)
    elseif not loot.pin then
        loot:collapseNow()
    end
end
