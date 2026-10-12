"""Testes do extrator de texturas com .pack sintetico (nenhum dado do jogo no repo).

Rodar: python -m unittest discover -s 05-Model-3D-Extractor-MCP/acervo/tests
"""
import io
import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

import extract_textures as et  # noqa: E402


def _s(text: str) -> bytes:
    b = text.encode("utf-8")
    return struct.pack("<i", len(b)) + b


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_pack(path: Path, pages, version=1):
    """pages = [(nome_pagina, atlas_img, [(nome, x, y, w, h, ox, oy, fw, fh), ...])]"""
    out = bytearray()
    if version >= 1:
        out += b"PZPK" + struct.pack("<i", version)
    out += struct.pack("<i", len(pages))
    for name, img, entries in pages:
        out += _s(name) + struct.pack("<ii", len(entries), 1)
        for nm, *vals in entries:
            out += _s(nm) + struct.pack("<8i", *vals)
        png = _png(img)
        if version >= 1:
            out += struct.pack("<i", len(png)) + png
        else:
            out += png + struct.pack("<I", 0xDEADBEEF)
    path.write_bytes(bytes(out))


def atlas():
    """Atlas 16x8: metade esquerda vermelha opaca, direita azul meio transparente."""
    im = Image.new("RGBA", (16, 8), (0, 0, 0, 0))
    im.paste((255, 0, 0, 255), (0, 0, 8, 8))
    im.paste((0, 0, 255, 128), (8, 0, 16, 8))
    return im


class ExtractTexturesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.game = root / "game"
        self.tp = self.game / "media" / "texturepacks"
        self.tp.mkdir(parents=True)
        self.data = root / "data"
        # 2x: red (8x8 em 2,3 de quadro 16x32), blue (so no 2x)
        write_pack(self.tp / "Tiles2x.pack", [
            ("Tiles2x0", atlas(), [
                ("demo_set_01_0", 0, 0, 8, 8, 2, 3, 16, 32),
                ("demo_set_01_1", 8, 0, 8, 8, 1, 4, 16, 32),
                ("vazio_01_0", 0, 0, 0, 0, 0, 0, 16, 32),
            ]),
        ])
        # 1x (formato versao 0): repete demo_set_01_0 (deve perder) + sprite so-1x
        write_pack(self.tp / "Tiles1x.pack", [
            ("Tiles1x0", atlas(), [
                ("demo_set_01_0", 0, 0, 4, 4, 1, 1, 8, 16),
                ("only1x_02_7", 8, 0, 4, 4, 0, 2, 8, 16),
            ]),
            ("Tiles1x1", atlas(), [("only1x_02_8", 0, 0, 2, 2, 0, 0, 8, 16)]),
        ], version=0)
        # pack de UI: deve ser so contado
        write_pack(self.tp / "UI.pack", [("UI0", atlas(), [("Item_X", 0, 0, 8, 8, 0, 0, 8, 8)])], version=0)
        self.conn = et._init_db(self.data)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def run_extract(self, **kw):
        return et.extract(self.conn, self.game, self.data, workers=1, max_gb=0.001, **kw)

    def test_scan_both_versions(self):
        v1, pages1 = et.scan_pack(self.tp / "Tiles2x.pack")
        v0, pages0 = et.scan_pack(self.tp / "Tiles1x.pack")
        self.assertEqual((v1, v0), (1, 0))
        self.assertEqual(len(pages1), 1)
        self.assertEqual(len(pages0), 2)
        self.assertEqual(pages1[0]["entries"][1], ("demo_set_01_1", 8, 0, 8, 8, 1, 4, 16, 32))
        self.assertEqual(pages0[1]["entries"][0][0], "only1x_02_8")

    def test_extract_prefers_2x_and_records_metadata(self):
        res = self.run_extract()
        self.assertEqual(res["sprites"], 4)            # 2 do 2x + 2 so-1x; vazio descartado
        self.assertEqual(res["written"], 4)
        self.assertEqual(res["empty_dropped"], 1)
        self.assertEqual(res["duplicates_dropped"], 1)
        self.assertEqual(res["by_scale"], {2: 2, 1: 2})
        self.assertEqual(res["ignored_packs"], {"UI.pack": 1})

        row = self.conn.execute(
            "SELECT pack, page, png, width, height, offset_x, offset_y, frame_w, frame_h, scale "
            "FROM sprites WHERE name='demo_set_01_0'").fetchone()
        self.assertEqual(row, ("Tiles2x.pack", "Tiles2x0", "sprites/demo_set_01/demo_set_01_0.png",
                               8, 8, 2, 3, 16, 32, 2))
        im = Image.open(self.data / row[2])
        self.assertEqual(im.size, (8, 8))
        self.assertEqual(im.convert("RGBA").getpixel((4, 4)), (255, 0, 0, 255))

        blue = Image.open(self.data / "sprites/demo_set_01/demo_set_01_1.png").convert("RGBA")
        self.assertEqual(blue.getpixel((0, 0)), (0, 0, 255, 128))

        one = self.conn.execute("SELECT scale, width, page FROM sprites WHERE name='only1x_02_8'").fetchone()
        self.assertEqual(one, (1, 2, "Tiles1x1"))
        self.assertTrue((self.data / "sprites/only1x_02/only1x_02_7.png").is_file())
        self.assertIsNone(self.conn.execute("SELECT 1 FROM sprites WHERE name='Item_X'").fetchone())

    def test_rerun_skips_existing(self):
        self.run_extract()
        res = self.run_extract()
        self.assertEqual(res["written"], 0)
        self.assertEqual(res["skipped_existing"], 4)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sprites").fetchone()[0], 4)

    def test_only_filter(self):
        res = self.run_extract(only=["Tiles1x.pack"])
        self.assertEqual(res["sprites"], 3)
        self.assertEqual(res["by_scale"], {1: 3})

    def test_game_dir_untouched_and_schema_created(self):
        before = sorted((p.name, p.stat().st_size) for p in self.tp.iterdir())
        self.run_extract()
        self.assertEqual(before, sorted((p.name, p.stat().st_size) for p in self.tp.iterdir()))
        self.assertEqual(sorted(p.name for p in self.game.rglob("*") if p.is_dir()), ["media", "texturepacks"])
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"sprites", "tiles", "geometry", "meta"} <= tables)

    def test_size_limit_aborts(self):
        with self.assertRaises(OSError):
            et.extract(self.conn, self.game, self.data, workers=1, max_gb=1e-9)

    def test_missing_texturepacks(self):
        with self.assertRaises(FileNotFoundError):
            et.extract(self.conn, self.data, self.data, workers=1)

    def test_tileset_and_safe_names(self):
        self.assertEqual(et.tileset_of("furniture_bedding_01_0"), "furniture_bedding_01")
        self.assertEqual(et.tileset_of("blood_floor_large_01"), "blood_floor_large")
        self.assertEqual(et.tileset_of("Radio"), "Radio")
        self.assertEqual(et.sprite_relpath("a/b:c_1_2"), "sprites/a_b_c_1/a_b_c_1_2.png")


if __name__ == "__main__":
    unittest.main()
