-- PZInspecao: identificacao de objetos do mundo (funcoes puras, rodam em client e server).
-- Chave de instancia = sprite | x,y,z | indice na lista do quadrado.
-- O indice pode mudar se outro objeto do mesmo quadrado sair, por isso o ID proprio
-- (gravado em getModData) e a referencia estavel quando ele existe.

PZInspecao = PZInspecao or {}
PZInspecao.version = "0.1"
PZInspecao.MODDATA_KEY = "PZInspecaoId"

function PZInspecao.keyOf(sprite, x, y, z, index)
    return tostring(sprite) .. "|" .. tostring(x) .. "," .. tostring(y) .. "," .. tostring(z) .. "|" .. tostring(index)
end

-- Le o ID proprio do objeto, se ele ja tiver um.
function PZInspecao.readId(obj)
    if not obj or not obj.getModData then return nil end
    local md = obj:getModData()
    return md and md[PZInspecao.MODDATA_KEY] or nil
end

-- Gera e grava um ID proprio na primeira vez; nas proximas devolve o mesmo.
function PZInspecao.ensureId(obj)
    local id = PZInspecao.readId(obj)
    if id then return id end
    -- math.random nao existe no Lua do PZ; ZombRand e getTimestampMs sao o substituto.
    id = "PZI-" .. tostring(getTimestampMs()) .. "-" .. tostring(ZombRand(100000, 999999))
    obj:getModData()[PZInspecao.MODDATA_KEY] = id
    return id
end

-- Descreve um objeto. Aceita IsoObject ou qualquer tabela com os mesmos metodos (para teste).
function PZInspecao.describe(obj, withId)
    if not obj then return nil end
    local sq = obj:getSquare()
    local sprite = obj:getSpriteName()
    local index = obj:getObjectIndex()
    local x, y, z
    if sq then x, y, z = sq:getX(), sq:getY(), sq:getZ() end
    local d = {
        sprite = sprite,
        x = x, y = y, z = z,
        index = index,
        key = PZInspecao.keyOf(sprite, x, y, z, index),
    }
    if withId then d.id = PZInspecao.ensureId(obj) else d.id = PZInspecao.readId(obj) end
    return d
end
