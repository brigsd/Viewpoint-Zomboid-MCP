"""Testes do extrator de tiles do acervo, com fixtures sintéticas (nenhum arquivo do jogo no repositório).

Rodar (a partir de 05-Model-3D-Extractor-MCP/acervo):  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ACERVO = HERE.parent
sys.path.insert(0, str(ACERVO))

import build_acervo  # noqa: E402
import categorize  # noqa: E402
import extract_tiles  # noqa: E402

DEFS_TXT = """version = 1
tileset
{
    file = furniture_bedding_01
    size = 8,16
    id = 1
    // furniture_bedding_01_0
    tile
    {
        xy = 0,0
        CustomName = Bed
        bed =
        Surface = 29
    }
    // furniture_bedding_01_9
    tile
    {
        xy = 1,1
        CustomName = Bed
        bed =
    }
}
tileset
{
    file = appliances_refrigeration_01
    size = 4,2
    id = 2
    // appliances_refrigeration_01_5
    tile
    {
        xy = 1,1
        CustomName = Fridge
        container = fridge
        ContainerCapacity = 40
    }
}
tileset
{
    file = furniture_tables_high_01
    size = 8,2
    id = 3
    // furniture_tables_high_01_0
    tile
    {
        xy = 0,0
        CustomName = Table
        IsTable =
    }
}
tileset
{
    file = furniture_shelving_01
    size = 8,2
    id = 4
    // furniture_shelving_01_0
    tile
    {
        xy = 0,0
        CustomName = Shelves
        container = shelves
    }
}
tileset
{
    file = walls_exterior_house_01
    size = 8,2
    id = 5
    // walls_exterior_house_01_0
    tile
    {
        xy = 0,0
        WallN =
    }
}
tileset
{
    file = mystery_01
    size = 8,2
    id = 6
    // mystery_01_0
    tile
    {
        xy = 0,0
        Foo = bar
    }
}
"""

PATCH_TXT = """version = 1
tileset
{
    file = appliances_refrigeration_01
    size = 4,2
    id = 2
    // appliances_refrigeration_01_5
    tile
    {
        xy = 1,1
        ContainerCapacity = 60
        ContainerOpenSound = OpenFridge
    }
}
"""

GEOMETRY_TXT = """tileGeometry
{
    VERSION = 2,

    tileset
    {
        name = furniture_bedding_01,

        /* furniture_bedding_01_0 */
        tile
        {
            xy = 0x0,

            box
            {
                translate = 0x0x0,
                rotate = 0x0x0,
                min = -4500x0x-6000,
                max = 5000x7200x3700,
            }

            box
            {
                translate = 10x20x30,
                rotate = 0x900000x0,
                min = -4500x0x3700,
                max = 5000x9000x4600,
            }

            cylinder
            {
                translate = 560x4592x482,
                rotate = 2700000x0x0,
                radius1 = 2679,
                radius2 = 2679,
                height = 1938,
            }

            properties
            {
                Surface = 29,
                Translucent = true,
            }
        }

        /* furniture_bedding_01_9 */
        tile
        {
            xy = 1x1,

            polygon
            {
                translate = 78x0x4917,
                rotate = 0x0x0,
                plane = XY,
                points = -4534x6057 -471x3378 -4690x380,
            }
        }
    }

    tileset
    {
        name = appliances_refrigeration_01,

        /* appliances_refrigeration_01_8 */
        tile
        {
            xy = 0x1,

            properties
            {
                Translucent = true,
            }
        }
    }

    tileset
    {
        name = signs_one-off_02_on,

        /* signs_one-off_02_on_3 */
        tile
        {
            xy = 3x0,

            box
            {
                translate = 0x0x0,
                rotate = 0x0x0,
                min = -1x0x-1,
                max = 1x1x1,
            }
        }
    }
}
"""

DEPTH_TXT = """tileDepthTextureAssignments
{
    VERSION = 1,
    furniture_bedding_01_1 = furniture_bedding_01_0,
    ghost_tileset_7 = furniture_bedding_01_0,
}
"""


def tdef_bytes(tilesets):
    """Escreve um .tiles binário mínimo. tilesets: [(nome, colunas, linhas, [lista de props por célula])]."""
    out = bytearray(b"tdef")
    out += struct.pack("<ii", 1, len(tilesets))
    for name, cols, rows, cells in tilesets:
        out += f"{name}\n{name}.png\n".encode()
        out += struct.pack("<iiii", cols, rows, 1, len(cells))
        for props in cells:
            out += struct.pack("<i", len(props))
            for k, v in props:
                out += f"{k}\n{v}\n".encode()
    return bytes(out)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class TilesFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.game = Path(cls.tmp.name) / "game"
        media = cls.game / "media"
        media.mkdir(parents=True)
        write(media / "newtiledefinitions.tiles.txt", DEFS_TXT)
        write(media / "tiledefinitions_noiseworks.patch.tiles.txt", PATCH_TXT)
        # só binário (como tiledefinitions_overlays.tiles): 2x2 células, duas vazias
        (media / "tiledefinitions_overlays.tiles").write_bytes(
            tdef_bytes([("floors_overlay_street_01", 2, 2, [[("FloorOverlay", "")], [], [], [("FloorOverlay", "")]])]))
        write(media / "tileGeometry.txt", GEOMETRY_TXT)
        write(media / "tileDepthTextureAssignments.txt", DEPTH_TXT)
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript((ACERVO / "schema.sql").read_text(encoding="utf-8"))
        cls.counts = extract_tiles.extract(cls.conn, str(cls.game))

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()


class TestDefinitions(TilesFixture):
    def test_tiles_from_txt_and_bin(self):
        names = {r[0] for r in self.q("SELECT name FROM tiles")}
        self.assertIn("furniture_bedding_01_0", names)
        self.assertIn("furniture_bedding_01_9", names)
        # binário: células vazias não viram tile; índice = y*colunas + x -> células 0 e 3
        self.assertIn("floors_overlay_street_01_0", names)
        self.assertIn("floors_overlay_street_01_3", names)
        self.assertNotIn("floors_overlay_street_01_1", names)

    def test_index_rule_uses_declared_columns(self):
        # xy = 1,1 em tileset de 4 colunas -> índice 5
        self.assertEqual(self.q("SELECT idx FROM tiles WHERE name='appliances_refrigeration_01_5'"), [(5,)])
        self.assertEqual(self.q("SELECT idx, tileset FROM tiles WHERE name='furniture_bedding_01_9'"),
                         [(9, "furniture_bedding_01")])

    def test_patch_merges_properties(self):
        p = dict(self.q("SELECT key, value FROM tile_props WHERE name='appliances_refrigeration_01_5'"))
        self.assertEqual(p["container"], "fridge")                 # veio da base
        self.assertEqual(p["ContainerCapacity"], "60")             # sobrescrito pelo patch
        self.assertEqual(p["ContainerOpenSound"], "OpenFridge")    # acrescentado pelo patch
        src = self.q("SELECT source FROM tiles WHERE name='appliances_refrigeration_01_5'")[0][0]
        self.assertIn("newtiledefinitions.tiles.txt", src)
        self.assertIn("noiseworks.patch.tiles.txt", src)

    def test_empty_values_kept(self):
        self.assertEqual(self.q("SELECT value FROM tile_props WHERE name='furniture_bedding_01_0' AND key='bed'"), [("",)])

    def test_txt_and_bin_parsers_agree(self):
        with tempfile.TemporaryDirectory() as d:
            txt = Path(d) / "a.tiles.txt"
            binf = Path(d) / "a.tiles"
            write(txt, DEFS_TXT)
            cells = [[] for _ in range(16)]
            cells[0] = [("CustomName", "Bed"), ("bed", ""), ("Surface", "29")]
            cells[9] = [("CustomName", "Bed"), ("bed", "")]
            binf.write_bytes(tdef_bytes([("furniture_bedding_01", 8, 2, cells)]))
            a = [x for x in extract_tiles.parse_tiles_txt(str(txt)) if x[0] == "furniture_bedding_01"]
            b = list(extract_tiles.parse_tiles_bin(str(binf)))
            self.assertEqual([(t, i, p) for t, _, _, i, p in a], [(t, i, p) for t, _, _, i, p in b])


class TestGeometry(TilesFixture):
    def test_boxes_with_values_as_written(self):
        rows = self.q("SELECT shape_idx, shape, min_x, min_y, min_z, max_x, max_y, max_z, raw FROM geometry "
                      "WHERE name='furniture_bedding_01_0' ORDER BY shape_idx")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], (0, "box", -4500.0, 0.0, -6000.0, 5000.0, 7200.0, 3700.0, None))
        self.assertEqual(rows[1][1], "box")

    def test_translate_rotate(self):
        r = self.q("SELECT tx,ty,tz,rx,ry,rz FROM geometry WHERE name='furniture_bedding_01_0' AND shape_idx=1")[0]
        self.assertEqual(r, (10.0, 20.0, 30.0, 0.0, 900000.0, 0.0))

    def test_non_box_shapes_keep_raw(self):
        cyl = self.q("SELECT shape, tx, ty, tz, rx, raw FROM geometry WHERE name='furniture_bedding_01_0' AND shape_idx=2")[0]
        self.assertEqual(cyl[0], "cylinder")
        self.assertEqual((cyl[1], cyl[2], cyl[3], cyl[4]), (560.0, 4592.0, 482.0, 2700000.0))
        self.assertIn("radius1 = 2679", cyl[5])
        self.assertIn("height = 1938", cyl[5])
        poly = self.q("SELECT shape, raw FROM geometry WHERE name='furniture_bedding_01_9'")[0]
        self.assertEqual(poly[0], "polygon")
        self.assertIn("points = -4534x6057 -471x3378 -4690x380", poly[1])

    def test_geometry_props(self):
        p = dict(self.q("SELECT key, value FROM geometry_props WHERE name='furniture_bedding_01_0'"))
        self.assertEqual(p, {"Surface": "29", "Translucent": "true"})

    def test_grid_is_always_8_columns(self):
        # xy 0x1 num tileset de 4 colunas nas definições -> o tileGeometry usa 8 colunas: índice 8
        self.assertEqual(self.counts["geometry_name_vs_xy_mismatch"], 0)
        self.assertEqual(self.q("SELECT COUNT(*) FROM geometry_props WHERE name='appliances_refrigeration_01_8'"), [(1,)])

    def test_counts(self):
        c = self.counts
        self.assertEqual(c["geometry_version"], 2)
        self.assertEqual(c["geometry_tiles"], 4)
        self.assertEqual(c["geometry_tiles_with_shapes"], 3)
        self.assertEqual(c["geometry_shapes"], 5)
        self.assertEqual(c["geometry_shape_types"], {"box": 3, "cylinder": 1, "polygon": 1})

    def test_geometry_only_tiles_enter_the_catalog(self):
        r = self.q("SELECT tileset, idx, source FROM tiles WHERE name='signs_one-off_02_on_3'")
        self.assertEqual(r, [("signs_one-off_02_on", 3, "tileGeometry.txt")])


class TestDepth(TilesFixture):
    def test_assignments(self):
        self.assertEqual(self.q("SELECT depth FROM depth_assignments WHERE name='furniture_bedding_01_1'"),
                         [("furniture_bedding_01_0",)])
        self.assertEqual(self.counts["depth_assignments"], 2)

    def test_depth_only_name_is_cataloged(self):
        self.assertEqual(self.q("SELECT source FROM tiles WHERE name='ghost_tileset_7'"),
                         [("tileDepthTextureAssignments.txt",)])


class TestCategories(TilesFixture):
    def cat(self, name):
        return self.q("SELECT category FROM tiles WHERE name=?", name)[0][0]

    def test_examples(self):
        self.assertEqual(self.cat("furniture_bedding_01_0"), "moveis")
        self.assertEqual(self.cat("appliances_refrigeration_01_5"), "eletrodomesticos")
        self.assertEqual(self.cat("furniture_tables_high_01_0"), "moveis")
        self.assertEqual(self.cat("furniture_shelving_01_0"), "containers")
        self.assertEqual(self.cat("walls_exterior_house_01_0"), "construcao")
        self.assertEqual(self.cat("mystery_01_0"), "outros")
        self.assertEqual(self.cat("floors_overlay_street_01_0"), "decoracao")

    def test_every_category_valid(self):
        valid = set(categorize.CATEGORIES)
        got = {r[0] for r in self.q("SELECT DISTINCT category FROM tiles")}
        self.assertTrue(got <= valid, got - valid)

    def test_rules_directly(self):
        c = categorize.categorize
        self.assertEqual(c("lighting_indoor_01", {}), "iluminacao")
        self.assertEqual(c("fixtures_bathroom_01", {"CustomName": "Toilet"}), "banheiro")
        self.assertEqual(c("x_01", {"container": "crate"}), "containers")
        self.assertEqual(c("x_01", {"container": "stove"}), "eletrodomesticos")
        self.assertEqual(c("fixtures_doors_01", {}), "portas_janelas")
        self.assertEqual(c("vegetation_trees_01", {}), "vegetacao")
        self.assertEqual(c("zzz_01", {}), "outros")


class TestIdempotentAndOrchestrator(TilesFixture):
    def test_extract_twice_same_counts(self):
        again = extract_tiles.extract(self.conn, str(self.game))
        self.assertEqual(again["tiles"], self.counts["tiles"])
        self.assertEqual(self.q("SELECT COUNT(*) FROM tiles")[0][0], self.counts["tiles"])

    def test_accepts_media_dir_directly(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript((ACERVO / "schema.sql").read_text(encoding="utf-8"))
        res = extract_tiles.extract(conn, str(self.game / "media"))
        self.assertEqual(res["tiles"], self.counts["tiles"])

    def test_build_tolerates_failing_textures(self):
        fake = mock.MagicMock()
        fake.extract.side_effect = RuntimeError("boom")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, {"extract_textures": fake}):
            rc = build_acervo.main(["--game-dir", str(self.game), "--data-dir", d])
            self.assertEqual(rc, 0)
            conn = sqlite3.connect(Path(d) / "acervo.sqlite")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0], self.counts["tiles"])
            self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='build_only'").fetchone()[0], "all")
            conn.close()

    def test_build_tolerates_missing_textures(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, {"extract_textures": None}):
            rc = build_acervo.main(["--game-dir", str(self.game), "--data-dir", d])
            self.assertEqual(rc, 0)

    def test_build_only_textures_keeps_tiles(self):
        fake = mock.MagicMock()
        fake.extract.return_value = {"sprites": 0}
        with tempfile.TemporaryDirectory() as d:
            build_acervo.main(["--only", "tiles", "--game-dir", str(self.game), "--data-dir", d])
            with mock.patch.dict(sys.modules, {"extract_textures": fake}):
                build_acervo.main(["--only", "textures", "--game-dir", str(self.game), "--data-dir", d])
            conn = sqlite3.connect(Path(d) / "acervo.sqlite")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0], self.counts["tiles"])
            conn.close()


if __name__ == "__main__":
    unittest.main()
