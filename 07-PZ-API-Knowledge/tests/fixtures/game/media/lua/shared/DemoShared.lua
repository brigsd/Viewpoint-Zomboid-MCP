LuaEventManager.AddEvent("OnDemoThing")
DemoShared = DemoShared or {}
DemoShared.value = function(x, y) return x + y end
function DemoShared:method(a) return a end
function globalFunc(arg) return arg end
if isServer() then
    Inside = {}
end
