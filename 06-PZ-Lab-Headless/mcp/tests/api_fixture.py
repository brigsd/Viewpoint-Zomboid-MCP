"""
Fixture do índice da API: cria um SQLite pequeno com linhas SINTÉTICAS usando o esquema real
(07-PZ-API-Knowledge/schema.sql). Nada aqui vem do jogo.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE.parent.parent.parent / "07-PZ-API-Knowledge" / "schema.sql"

# (kind, name, owner, java_class, signature, returns, is_static, origin, file, line)
SYMBOLS = [
    ("global_function", "getScriptManager", None, None, "ScriptManager getScriptManager()", "ScriptManager", 0, "java", None, None),
    ("global_function", "instanceItem", None, None, "InventoryItem instanceItem(String)", "InventoryItem", 0, "java", None, None),
    ("class", "ScriptManager", None, "zombie.scripting.ScriptManager", None, None, 0, "java", None, None),
    ("method", "getCraftRecipe", "ScriptManager", "zombie.scripting.ScriptManager", "CraftRecipe getCraftRecipe(String)", "CraftRecipe", 0, "java", None, None),
    ("method", "getItem", "ScriptManager", "zombie.scripting.ScriptManager", "Item getItem(String)", "Item", 0, "java", None, None),
    ("field", "instance", "ScriptManager", "zombie.scripting.ScriptManager", "ScriptManager instance", "ScriptManager", 1, "java", None, None),
    ("class", "CraftRecipe", None, "zombie.scripting.entity.components.crafting.CraftRecipe", None, None, 0, "java", None, None),
    ("method", "getInputs", "CraftRecipe", "zombie.scripting.entity.components.crafting.CraftRecipe", "ArrayList getInputs()", "ArrayList", 0, "java", None, None),
    ("class", "ItemContainer", None, "zombie.inventory.ItemContainer", None, None, 0, "java", None, None),
    ("method", "new", "ItemContainer", "zombie.inventory.ItemContainer", "ItemContainer new()", "ItemContainer", 1, "java", None, None),
    ("method", "getItems", "ItemContainer", "zombie.inventory.ItemContainer", "ArrayList getItems()", "ArrayList", 0, "java", None, None),
    ("class", "Translator", None, "zombie.core.Translator", None, None, 0, "java", None, None),
    ("method", "loadFiles", "Translator", "zombie.core.Translator", "void loadFiles()", "void", 1, "java", None, None),
    ("method", "getText", "Translator", "zombie.core.Translator", "String getText(String)", "String", 1, "java", None, None),
    ("event", "OnServerStarted", None, None, "OnServerStarted()", None, 0, "java", None, None),
    ("event", "OnPlayerUpdate", None, None, None, None, 0, "java", None, None),
    ("event", "OnFillInventoryObjectContextMenu", None, None, None, None, 0, "java", None, None),
    ("lua_global", "ISInventoryPage", None, None, None, None, 0, "lua", "client/ISUI/ISInventoryPage.lua", 12),
]

# (symbol, owner, file, line, snippet)
USAGES = [
    ("OnServerStarted", "Events", "server/Init.lua", 10, "Events.OnServerStarted.Add(function() print('up') end)"),
    ("OnServerStarted", "Events", "server/Other.lua", 4, "Events.OnServerStarted.Add(onStart)"),
    ("OnPlayerUpdate", "Events", "client/A.lua", 20, "Events.OnPlayerUpdate.Add(function(player) tick(player) end)"),
    ("OnPlayerUpdate", "Events", "client/B.lua", 30, "Events.OnPlayerUpdate.Add(function(player) x() end)"),
    ("OnPlayerUpdate", "Events", "client/C.lua", 31, "Events.OnPlayerUpdate.Add(function(p) y() end)"),
    ("OnFillInventoryObjectContextMenu", "Events", "client/M.lua", 5, "Events.OnFillInventoryObjectContextMenu.Add("),
    ("getCraftRecipe", "ScriptManager", "shared/Craft.lua", 7, "local r = getScriptManager():getCraftRecipe(name)"),
    ("getCraftRecipe", None, "shared/Craft.lua", 40, "local r = mgr:getCraftRecipe(id)"),
    ("getCraftRecipe", "OtherThing", "shared/Other.lua", 9, "foo:getCraftRecipe(1)"),
    ("getScriptManager", None, "shared/Craft.lua", 6, "local m = getScriptManager()"),
    ("OnPlayerUpdate", None, "client/NotEvent.lua", 1, "function OnPlayerUpdate() end"),
]

BLOCKS = [
    ("item", "Base", "Axe", "items/weapons.txt", 3),
    ("item", "Base", "Hammer", "items/tools.txt", 8),
    ("craftRecipe", "Base", "MakeNail", "recipes/nails.txt", 1),
]

# (block_type, field, count, example_value, example_file, example_line)
FIELDS = [
    ("item", "ItemType", 900, "base:weapon", "items/weapons.txt", 5),
    ("item", "UseDelta", 120, "0.1", "items/food.txt", 44),
    ("item", "Weight", 1000, "1.5", "items/weapons.txt", 6),
    ("craftRecipe", "inputs", 300, "{ ... }", "recipes/nails.txt", 4),
    ("craftRecipe", "inputs.item", 800, "item 1 [Base.Hammer] flags[Prop1],", "recipes/nails.txt", 5),
    ("craftRecipe", "inputs.fluid", 20, "fluid 0.5 [Water],", "recipes/drink.txt", 9),
    ("craftRecipe", "timedAction", 250, "Making", "recipes/nails.txt", 3),
]


def build_fixture_db(path: Path, *, with_meta: bool = True, populate_fts: bool = True) -> Path:
    path = Path(path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        if with_meta:
            conn.executemany("INSERT INTO meta VALUES (?,?)",
                             [("game_version", "42.21.0-fixture"), ("built_at", "2026-10-11T12:00:00Z")])
        conn.executemany("INSERT INTO symbols (kind,name,owner,java_class,signature,returns,is_static,origin,file,line) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)", SYMBOLS)
        conn.executemany("INSERT INTO usages VALUES (?,?,?,?,?)", USAGES)
        conn.executemany("INSERT INTO script_blocks VALUES (?,?,?,?,?)", BLOCKS)
        conn.executemany("INSERT INTO script_fields VALUES (?,?,?,?,?,?)", FIELDS)
        if populate_fts:
            conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('rebuild')")
        conn.commit()
    finally:
        conn.close()
    return path
