-- Esquema do índice da API do Project Zomboid 42.21 (data/pz_api.sqlite).
-- Contrato compartilhado entre os extratores e as ferramentas do MCP pz-live.

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,   -- game_version, built_at, count_<tabela>, ...
    value TEXT
);

-- Símbolos chamáveis/consultáveis a partir do Lua.
--   kind: 'global_function' (função global do Lua, ex. getScriptManager, instanceItem)
--         'class'           (classe Java exposta ao Lua; name = nome curto, java_class = FQN)
--         'method'          (método de classe exposta; owner = nome curto da classe)
--         'field'           (campo/constante pública exposta; owner = classe)
--         'event'           (Events.<name>)
--         'lua_global'      (tabela/função global definida no Lua vanilla, ex. ISInventoryPage)
CREATE TABLE IF NOT EXISTS symbols (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    owner      TEXT,              -- classe dona (método/campo) ou NULL
    java_class TEXT,              -- FQN Java quando houver
    signature  TEXT,              -- ex. 'CraftRecipe getCraftRecipe(String)'
    returns    TEXT,
    is_static  INTEGER DEFAULT 0, -- 1 = chamado com '.', 0 = com ':' (métodos)
    origin     TEXT NOT NULL,     -- 'java' | 'lua'
    file       TEXT,              -- onde foi definido (relativo à pasta do jogo) quando origin='lua'
    line       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_symbols_name  ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_owner ON symbols(owner);
CREATE INDEX IF NOT EXISTS idx_symbols_kind  ON symbols(kind);

-- Usos no Lua vanilla (exemplos reais). symbol = nome usado (ex. 'getCraftRecipe', 'OnServerStarted').
CREATE TABLE IF NOT EXISTS usages (
    symbol  TEXT NOT NULL,
    owner   TEXT,                 -- 'Events' para eventos; classe quando inferível; senão NULL
    file    TEXT NOT NULL,        -- relativo a media/lua, com '/'
    line    INTEGER NOT NULL,
    snippet TEXT                  -- a linha de código (máx. 200 caracteres)
);
CREATE INDEX IF NOT EXISTS idx_usages_symbol ON usages(symbol);

-- Blocos de script (media/scripts): item, craftRecipe, fluid, entity, vehicle, ...
CREATE TABLE IF NOT EXISTS script_blocks (
    block_type TEXT NOT NULL,     -- 'item', 'craftRecipe', ...
    module     TEXT,              -- 'Base', ...
    name       TEXT NOT NULL,
    file       TEXT NOT NULL,     -- relativo a media/scripts
    line       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_blocks ON script_blocks(block_type, name);

-- Campos usados em cada tipo de bloco, com contagem e exemplo real.
CREATE TABLE IF NOT EXISTS script_fields (
    block_type    TEXT NOT NULL,
    field         TEXT NOT NULL,  -- como aparece no vanilla (ex. 'ItemType', 'UseDelta', 'inputs')
    count         INTEGER NOT NULL,
    example_value TEXT,
    example_file  TEXT,
    example_line  INTEGER,
    PRIMARY KEY (block_type, field)
);

-- Chaves de tradução (media/lua/shared/Translate/<LANG>/<Categoria>.json)
CREATE TABLE IF NOT EXISTS translations (
    lang     TEXT NOT NULL,       -- 'EN', 'PTBR', ...
    category TEXT NOT NULL,       -- nome do arquivo sem extensão: 'ItemName', 'Recipes', 'UI', ...
    key      TEXT NOT NULL,
    value    TEXT,
    file     TEXT
);
CREATE INDEX IF NOT EXISTS idx_tr_key ON translations(key);

-- Busca textual sobre os símbolos.
CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name, owner, signature, kind, content='symbols', content_rowid='id'
);
