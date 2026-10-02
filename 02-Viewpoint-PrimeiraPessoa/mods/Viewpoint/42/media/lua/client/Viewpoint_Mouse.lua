





local function mouse()
    return Viewpoint and Viewpoint.Mouse
end

local function wrap()
    if not ISCoordConversion or ISCoordConversion.viewpointWrapped then return end
    local toWorld = ISCoordConversion.ToWorld
    ISCoordConversion.ToWorld = function(x, y, z)
        local m = mouse()
        local wx = m and m.worldX()
        local wy = m and m.worldY()
        if wx and wy then return wx, wy end
        return toWorld(x, y, z)
    end
    ISCoordConversion.viewpointWrapped = true
end

Events.OnGameStart.Add(wrap)
