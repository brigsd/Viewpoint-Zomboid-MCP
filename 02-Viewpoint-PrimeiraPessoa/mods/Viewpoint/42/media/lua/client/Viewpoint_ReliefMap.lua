





local LAYER = "viewpoint-relief"

local function reliefMap()
    return Viewpoint and Viewpoint.ReliefMap
end


local function underLabels(styleAPI)
    for i = 0, styleAPI:getLayerCount() - 1 do
        if styleAPI:getLayerByIndex(i):getTypeString() == "Text" then return i end
    end
    return styleAPI:getLayerCount() - 1
end

local function lay(mapUI)
    local r = reliefMap()
    if not r or not mapUI.javaObject then return end
    local mapAPI = mapUI.javaObject:getAPIv3()
    local styleAPI = mapAPI:getStyleAPI()
    local file = r.file()
    if file and mapAPI:getImagePyramidMinX(file) < 0 then
        mapAPI:addImagePyramid(file)
    end
    local layer = styleAPI:getLayerByName(LAYER)
    if not layer then
        layer = styleAPI:newPyramidLayer(LAYER)
        layer:addFill(0.0, 255, 255, 255, r.alpha())
        styleAPI:moveLayer(styleAPI:indexOfLayer(LAYER), underLabels(styleAPI))
    end
    layer:setPyramidFileName(file and file:match("[^/\\]+$") or "")
end

local function wrap(class)
    if not class or class.viewpointReliefWrapped then return end
    local prerender = class.prerender
    class.prerender = function(self, ...)
        lay(self)
        return prerender(self, ...)
    end
    class.viewpointReliefWrapped = true
end

Events.OnGameStart.Add(function()
    wrap(ISWorldMap)
    wrap(ISMiniMapInner)
end)
