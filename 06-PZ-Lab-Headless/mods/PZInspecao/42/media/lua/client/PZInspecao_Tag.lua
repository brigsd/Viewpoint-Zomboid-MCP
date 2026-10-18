-- PZInspecao (cliente): F6 descreve os objetos do quadrado do jogador e grava no log.
-- A mira (objeto apontado pelo mouse) ainda nao esta ligada: depende do Viewpoint,
-- e a Lua nao ve o alvo da mira. Ver o plano 2026-10-18 (fatia 2, risco).

PZInspecao = PZInspecao or {}
PZInspecao.TAG_KEY = Keyboard.KEY_F6

local function tagSquare(player)
    local sq = player:getCurrentSquare()
    if not sq then
        print("[PZInspecao] jogador fora de quadrado")
        return
    end
    local objects = sq:getObjects()
    if objects:size() == 0 then
        print("[PZInspecao] quadrado sem objetos")
        return
    end
    for i = 0, objects:size() - 1 do
        local d = PZInspecao.describe(objects:get(i), true)
        print("[PZInspecao] " .. d.key .. " id=" .. tostring(d.id))
    end
end

Events.OnKeyPressed.Add(function(key)
    if key ~= PZInspecao.TAG_KEY then return end
    local player = getPlayer()
    if player then tagSquare(player) end
end)
