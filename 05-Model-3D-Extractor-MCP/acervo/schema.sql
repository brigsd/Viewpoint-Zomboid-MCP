-- Catálogo do acervo de objetos (acervo/data/acervo.sqlite). Contrato entre os extratores.
-- Nome de sprite = como o jogo chama o tile, ex. 'furniture_bedding_01_0' (tileset 'furniture_bedding_01', índice 0).

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- [extract_textures.py] Uma linha por sprite encontrado nos .pack (a melhor resolução disponível).
CREATE TABLE IF NOT EXISTS sprites (
    name      TEXT PRIMARY KEY,   -- nome do sprite no .pack
    pack      TEXT NOT NULL,      -- arquivo .pack de origem (ex. 'Tiles2x.pack')
    page      TEXT,               -- página/atlas dentro do .pack
    png       TEXT NOT NULL,      -- caminho do PNG extraído, relativo a acervo/data/
    width     INTEGER,            -- tamanho do recorte
    height    INTEGER,
    offset_x  INTEGER,            -- deslocamento do recorte dentro do quadro original
    offset_y  INTEGER,
    frame_w   INTEGER,            -- tamanho do quadro original (antes do recorte de transparência)
    frame_h   INTEGER,
    scale     INTEGER             -- 1 ou 2 (resolução 1x/2x)
);

-- [extract_tiles.py] Definições de tile: uma linha por sprite definido nos .tiles.
CREATE TABLE IF NOT EXISTS tiles (
    name     TEXT PRIMARY KEY,    -- 'furniture_bedding_01_0'
    tileset  TEXT NOT NULL,       -- 'furniture_bedding_01'
    idx      INTEGER NOT NULL,    -- índice no tileset
    source   TEXT,                -- arquivo .tiles de origem
    category TEXT                 -- categoria inferida: moveis, eletrodomesticos, containers, construcao,
                                  -- portas_janelas, decoracao, vegetacao, iluminacao, banheiro, cozinha, outros
);
CREATE INDEX IF NOT EXISTS idx_tiles_tileset ON tiles(tileset);
CREATE INDEX IF NOT EXISTS idx_tiles_category ON tiles(category);

-- [extract_tiles.py] Propriedades de cada tile (chave/valor, como no .tiles).
CREATE TABLE IF NOT EXISTS tile_props (
    name  TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_props_name ON tile_props(name);
CREATE INDEX IF NOT EXISTS idx_props_key ON tile_props(key);

-- [extract_tiles.py] Geometria 3D da B42 (media/tileGeometry.txt), uma linha por forma.
-- Unidades como no arquivo (ex. min = -4500x0x-6000); 'raw' guarda o bloco original para formas não-caixa.
CREATE TABLE IF NOT EXISTS geometry (
    name      TEXT NOT NULL,      -- sprite
    shape_idx INTEGER NOT NULL,   -- ordem da forma no tile
    shape     TEXT NOT NULL,      -- 'box', 'cylinder', 'polygon', ...
    tx REAL, ty REAL, tz REAL,    -- translate
    rx REAL, ry REAL, rz REAL,    -- rotate
    min_x REAL, min_y REAL, min_z REAL,
    max_x REAL, max_y REAL, max_z REAL,
    raw       TEXT,
    PRIMARY KEY (name, shape_idx)
);

-- [extract_tiles.py] Propriedades do bloco 'properties' do tileGeometry (ex. Surface, Translucent).
CREATE TABLE IF NOT EXISTS geometry_props (
    name  TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT
);

-- [extract_tiles.py] media/tileDepthTextureAssignments.txt
CREATE TABLE IF NOT EXISTS depth_assignments (
    name  TEXT PRIMARY KEY,
    depth TEXT                    -- textura de profundidade atribuída
);

-- [extract_depth.py] Mapa de profundidade por sprite, recortado de media/depthmaps/DEPTH_<tileset>.png
-- (folhas de 8 colunas de quadros 128x256). Dá volume aos objetos que não têm geometria.
CREATE TABLE IF NOT EXISTS depth_maps (
    name    TEXT PRIMARY KEY,     -- sprite
    png     TEXT NOT NULL,        -- relativo a acervo/data/ (ex. depth/<tileset>/<name>.png)
    sheet   TEXT NOT NULL,        -- arquivo DEPTH_*.png de origem
    col     INTEGER, row INTEGER, -- posição do quadro na folha
    nonzero INTEGER               -- pixels com profundidade (0 = quadro vazio)
);

-- Visão de conveniência: o objeto completo.
CREATE VIEW IF NOT EXISTS objects AS
SELECT t.name, t.tileset, t.idx, t.category, s.png, s.width, s.height, s.scale,
       (SELECT COUNT(*) FROM geometry g WHERE g.name = t.name) AS shapes,
       (SELECT d.png FROM depth_maps d WHERE d.name = t.name) AS depth_png
FROM tiles t LEFT JOIN sprites s ON s.name = t.name;
