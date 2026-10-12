"""Testes do extrator de profundidade, da prova de alinhamento, do visualizador e do relatorio de faltantes,
com dados sinteticos (nenhum dado do jogo no repo).

Rodar: python -m unittest discover -s 05-Model-3D-Extractor-MCP/acervo/tests
"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import align_check as ac  # noqa: E402
import extract_depth as ed  # noqa: E402
import report_missing as rm  # noqa: E402
import viewer  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
SCHEMA = (HERE / "schema.sql").read_text(encoding="utf-8")


def make_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def palette_sheet(w, h, frames):
    """Folha em modo P como as do jogo: indice 0 transparente, indice i>=1 -> cinza 256-i.

    frames = {(coluna, linha): indice_de_paleta} preenche o quadro inteiro com esse indice."""
    a = np.zeros((h, w), np.uint8)
    for (c, r), idx in frames.items():
        a[r * 256:(r + 1) * 256, c * 128:(c + 1) * 128] = idx
    im = Image.fromarray(a, "P")
    pal = [0, 0, 0] + [v for i in range(1, 256) for v in (256 - i,) * 3]
    im.putpalette(pal)
    im.info["transparency"] = 0
    return im


class DecodeTest(unittest.TestCase):
    def test_palette_mode(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "DEPTH_x.png"
            palette_sheet(128, 256, {(0, 0): 56}).save(p, transparency=0)
            g, m = ed.decode_sheet(p)
            self.assertTrue(m.all())
            self.assertEqual(set(np.unique(g)), {200})           # 256 - 56

    def test_palette_index_zero_is_transparent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "DEPTH_x.png"
            palette_sheet(256, 256, {(1, 0): 1}).save(p, transparency=0)
            g, m = ed.decode_sheet(p)
            self.assertFalse(m[:, :128].any())
            self.assertTrue(m[:, 128:].all())
            self.assertEqual(int(g[0, 130]), 255)                  # indice 1 = cinza 255

    def test_la_and_l_modes(self):
        with tempfile.TemporaryDirectory() as d:
            la = np.zeros((256, 128, 2), np.uint8)
            la[10:20, 5:15] = (77, 255)
            la[30, 30] = (99, 0)                                   # alpha 0 nao conta
            Image.fromarray(la, "LA").save(Path(d) / "a.png")
            g, m = ed.decode_sheet(Path(d) / "a.png")
            self.assertEqual(int(m.sum()), 100)
            self.assertEqual(int(g[15, 10]), 77)
            L = np.zeros((256, 128), np.uint8)
            L[5, 5] = 3
            Image.fromarray(L, "L").save(Path(d) / "b.png")
            g, m = ed.decode_sheet(Path(d) / "b.png")
            self.assertEqual(int(m.sum()), 1)


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.game = root / "game"
        dm = self.game / "media" / "depthmaps"
        dm.mkdir(parents=True)
        # 8 colunas x 2 linhas: quadros 0 (indice 40), 9 (linha 1, coluna 1; indice 200); o resto vazio
        palette_sheet(1024, 512, {(0, 0): 40, (1, 1): 200}).save(dm / "DEPTH_demo_set_01.png", transparency=0)
        L = np.zeros((256, 128), np.uint8)
        L[100:150, 10:60] = 90
        Image.fromarray(L, "L").save(dm / "DEPTH_billboard.png")
        Image.new("RGBA", (1024, 256), (10, 10, 10, 255)).save(dm / "SEAMS_01.png")   # nao e DEPTH_: ignorada
        self.data = root / "data"
        self.conn = make_db(self.data / "acervo.sqlite")
        self.conn.execute("INSERT INTO tiles(name, tileset, idx, source, category) VALUES "
                          "('demo_set_01_0','demo_set_01',0,'a.tiles','moveis')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def run_extract(self, **kw):
        return ed.extract(self.conn, self.game, self.data, workers=1, check_sample=0, **kw)

    def test_cuts_frames_and_fills_table(self):
        res = self.run_extract()
        self.assertEqual(res["sheets"], 2)
        self.assertEqual(res["depth_maps"], 3)
        self.assertEqual(res["empty_frames"], 16 - 2)
        rows = {r[0]: r for r in self.conn.execute("SELECT name, png, sheet, col, row, nonzero FROM depth_maps")}
        self.assertEqual(set(rows), {"demo_set_01_0", "demo_set_01_9", "billboard_0"})
        self.assertEqual(rows["demo_set_01_9"][1:], ("depth/demo_set_01/demo_set_01_9.png", "DEPTH_demo_set_01.png", 1, 1, 128 * 256))
        self.assertEqual(rows["billboard_0"][5], 50 * 50)
        im = Image.open(self.data / rows["demo_set_01_0"][1])
        self.assertEqual((im.size, im.mode), ((128, 256), "LA"))
        self.assertEqual(im.getpixel((3, 3)), (216, 255))          # indice 40 -> cinza 216, opaco
        self.assertEqual(Image.open(self.data / rows["demo_set_01_9"][1]).getpixel((0, 0)), (56, 255))   # indice 200
        self.assertEqual(res["tiles_with_own_depth"], 1)
        self.assertEqual(res["depth_without_tile"], 2)

    def test_empty_frames_skipped_and_rerun_idempotent(self):
        self.run_extract()
        res = self.run_extract()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM depth_maps").fetchone()[0], 3)
        self.assertEqual(res["depth_maps"], 3)
        self.assertEqual(len(list((self.data / "depth").rglob("*.png"))), 3)
        self.assertFalse((self.data / "depth" / "demo_set_01" / "demo_set_01_1.png").exists())

    def test_game_dir_untouched(self):
        before = sorted((p.name, p.stat().st_size) for p in self.game.rglob("*") if p.is_file())
        self.run_extract()
        self.assertEqual(before, sorted((p.name, p.stat().st_size) for p in self.game.rglob("*") if p.is_file()))

    def test_missing_dir(self):
        with self.assertRaises(FileNotFoundError):
            ed.extract(self.conn, self.data, self.data, workers=1, check_sample=0)

    def test_old_view_is_upgraded(self):
        self.conn.execute("DROP VIEW objects")
        self.conn.execute("CREATE VIEW objects AS SELECT name FROM tiles")
        self.run_extract()
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(objects)")}
        self.assertIn("depth_png", cols)
        self.assertEqual(self.conn.execute("SELECT depth_png FROM objects WHERE name='demo_set_01_0'").fetchone()[0],
                         "depth/demo_set_01/demo_set_01_0.png")


class EncodingTest(unittest.TestCase):
    def test_constants(self):
        self.assertAlmostEqual(ed.K_PX, 0.0064)
        self.assertAlmostEqual(ed.H_PX, 0.007838, places=6)

    def test_gray_formula(self):
        self.assertAlmostEqual(float(ed.gray_from_world(0, 0, 0)), 190.0)
        # mais perto da camera (+X, +Z ou +Y) = mais escuro
        self.assertLess(float(ed.gray_from_world(5000, 0, 5000)), float(ed.gray_from_world(0, 0, 0)))
        self.assertLess(float(ed.gray_from_world(0, 8000, 0)), float(ed.gray_from_world(0, 0, 0)))
        # canto de tras do chao fica mais claro (mais longe)
        self.assertGreater(float(ed.gray_from_world(-5000, 0, -5000)), 190)
        # exemplo medido: topo da caixa de 8000 de altura, canto da frente (5000, 8000, 5000)
        self.assertAlmostEqual(float(ed.gray_from_world(5000, 8000, 5000)), 190 - 64 - 41.8, delta=0.5)


class AlignTest(unittest.TestCase):
    def test_projection_points(self):
        p = ac.project(np.array([[0, 0, 0], [5000, 0, 5000], [5000, 0, -5000], [-5000, 0, 5000], [0, 10000, 0]], float))
        np.testing.assert_allclose(p[0], (64, 224))
        np.testing.assert_allclose(p[1], (64, 256))             # canto de baixo do losango
        np.testing.assert_allclose(p[2], (128, 224))            # X para a direita
        np.testing.assert_allclose(p[3], (0, 224))              # Z para a esquerda
        self.assertAlmostEqual(224 - p[4][1], 78.38, places=1)  # 1 tile de altura ~ 78,4 px

    def test_eight_mappings_one_chosen(self):
        ms = ac.candidate_mappings()
        self.assertEqual(len(ms), 8)
        self.assertEqual(sum(1 for m in ms if m == ac.CHOSEN), 1)

    def test_iou_and_silhouette(self):
        row = ("box", 0, 0, 0, 0, 0, 0, -5000, 0, -5000, 5000, 5000, 5000, None)
        s = ac.silhouette([row])
        self.assertTrue(s[224, 64])
        self.assertFalse(s[10, 10])
        self.assertAlmostEqual(ac.iou(s, s), 1.0)
        self.assertEqual(ac.iou(s, np.zeros_like(s)), 0.0)

    def test_rotation_and_cylinder_shapes(self):
        # caixa girada 90 graus em Y: o casco no chao continua um quadrado de mesmo tamanho
        a = ac.shape_geometry(("box", 0, 0, 0, 0, 900000, 0, -2000, 0, -1000, 2000, 1000, 1000, None))[0]
        self.assertAlmostEqual(float(a[:, 0].max() - a[:, 0].min()), 2000, delta=1)
        self.assertAlmostEqual(float(a[:, 2].max() - a[:, 2].min()), 4000, delta=1)
        # cilindro: eixo local Z girado 270 graus em X fica vertical, centrado em translate
        cyl = ("cylinder", 0, 500, 0, 2700000, 0, 0, None, None, None, None, None, None,
               "cylinder\n{\n radius1 = 1000\n radius2 = 1000\n height = 400\n}")
        P = ac.shape_geometry(cyl)[0]
        self.assertAlmostEqual(float(P[:, 1].min()), 300, delta=1)
        self.assertAlmostEqual(float(P[:, 1].max()), 700, delta=1)

    def test_measure_picks_chosen_mapping_and_detects_shift(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            conn = make_db(data / "acervo.sqlite")
            # caixa fora do centro em X e Z (sem simetria) para distinguir os mapeamentos
            conn.execute("INSERT INTO tiles VALUES ('box_01_0','box_01',0,'x','moveis')")
            conn.execute("INSERT INTO geometry(name,shape_idx,shape,tx,ty,tz,rx,ry,rz,min_x,min_y,min_z,max_x,max_y,max_z) "
                         "VALUES ('box_01_0',0,'box',0,0,0,0,0,0,-5000,0,-1000,2000,6000,3000)")
            row = ("box", 0, 0, 0, 0, 0, 0, -5000, 0, -1000, 2000, 6000, 3000, None)
            mask = ac.silhouette([row])
            rgba = np.zeros((256, 128, 4), np.uint8)
            rgba[mask] = (200, 100, 50, 255)
            (data / "sprites" / "box_01").mkdir(parents=True)
            Image.fromarray(rgba, "RGBA").save(data / "sprites" / "box_01" / "box_01_0.png")
            conn.execute("INSERT INTO sprites VALUES ('box_01_0','P','pg','sprites/box_01/box_01_0.png',128,256,0,0,128,256,2)")
            conn.commit()
            self.addCleanup(conn.close)
            m = ac.measure(conn, data, "box_01_0")
            self.assertAlmostEqual(m["iou_colour"], 1.0, places=3)
            self.assertEqual(m["best_shift_px"], (0, 0))
            best = m["mappings"][0]
            self.assertTrue(best["chosen"])
            others = [x["iou_colour"] for x in m["mappings"] if not x["chosen"]]
            self.assertLess(max(others), 0.9)
            # sprite deslocado 3 px para a direita: o melhor deslocamento (aplicado a geometria) e (3, 0)
            shifted = np.roll(rgba, 3, 1)
            Image.fromarray(shifted, "RGBA").save(data / "sprites" / "box_01" / "box_01_0.png")
            m2 = ac.measure(conn, data, "box_01_0", with_mappings=False)
            self.assertEqual(m2["best_shift_px"], (3, 0))
            conn.close()

    def test_render_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            conn = make_db(data / "acervo.sqlite")
            conn.execute("INSERT INTO tiles VALUES ('box_01_0','box_01',0,'x','moveis')")
            conn.execute("INSERT INTO geometry(name,shape_idx,shape,tx,ty,tz,rx,ry,rz,min_x,min_y,min_z,max_x,max_y,max_z) "
                         "VALUES ('box_01_0',0,'box',0,0,0,0,0,0,-5000,0,-5000,5000,6000,5000)")
            conn.commit()
            res = ac.run(conn, data, ["box_01_0", "nao_existe_9"], data / "align", quiet=True)
            self.assertEqual(len(res["objetos"]), 1)
            self.assertTrue((data / "align" / "box_01_0.png").is_file())
            self.assertTrue((data / "align" / "box_01_0_lado_a_lado.png").is_file())
            self.assertTrue(json.loads((data / "align" / "resultado.json").read_text(encoding="utf-8"))["objetos"])
            conn.close()


class ColourAlignmentTest(unittest.TestCase):
    def test_check_colour_alignment(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            conn = make_db(data / "acervo.sqlite")
            # sprite 2x: recorte 40x60 em (10,100) do quadro 128x256; mapa de profundidade = mesmo retangulo
            (data / "sprites" / "s_01").mkdir(parents=True)
            (data / "depth" / "s_01").mkdir(parents=True)
            Image.new("RGBA", (40, 60), (255, 0, 0, 255)).save(data / "sprites/s_01/s_01_0.png")
            la = np.zeros((256, 128, 2), np.uint8)
            la[100:160, 10:50] = (120, 255)
            Image.fromarray(la, "LA").save(data / "depth/s_01/s_01_0.png")
            conn.execute("INSERT INTO sprites VALUES ('s_01_0','P','pg','sprites/s_01/s_01_0.png',40,60,10,100,128,256,2)")
            conn.execute("INSERT INTO depth_maps VALUES ('s_01_0','depth/s_01/s_01_0.png','DEPTH_s_01.png',0,0,2400)")
            # sprite 1x: metade das medidas; vira o mesmo retangulo apos normalizar
            Image.new("RGBA", (20, 30), (0, 255, 0, 255)).save(data / "sprites/s_01/s_01_1.png")
            Image.fromarray(la, "LA").save(data / "depth/s_01/s_01_1.png")
            conn.execute("INSERT INTO sprites VALUES ('s_01_1','P','pg','sprites/s_01/s_01_1.png',20,30,5,50,64,128,1)")
            conn.execute("INSERT INTO depth_maps VALUES ('s_01_1','depth/s_01/s_01_1.png','DEPTH_s_01.png',1,0,2400)")
            conn.commit()
            r = ed.check_colour_alignment(conn, data, limit=10)
            self.assertEqual(r["n"], 2)
            self.assertEqual(r["iou_mediana"], 1.0)
            self.assertEqual(r["cobertura_mediana"], 1.0)
            self.assertEqual(r["melhor_deslocamento_zero"], 1.0)
            conn.close()


class ReportTest(unittest.TestCase):
    def test_classify_and_ranges(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            conn = make_db(data / "acervo.sqlite")
            tiles = [
                ("a_01_0", "a_01", 0, "a.tiles", "moveis"), ("a_01_1", "a_01", 1, "a.tiles", "moveis"),
                ("a_01_2", "a_01", 2, "a.tiles", "moveis"), ("a_01_9", "a_01", 9, "a.tiles", "moveis"),
                ("a_01_on_3", "a_01_on", 3, "tileGeometry.txt", "iluminacao"),
                ("b_02_on_1", "b_02_on", 1, "a.tiles", "iluminacao"),
                ("crafted_03_0", "crafted_03", 0, "a.tiles", "moveis"),
                ("g_01_5", "g_01", 5, "tileGeometry.txt", "outros"),
                ("a_01_7", "a_01", 7, "tileDepthTextureAssignments.txt", "moveis"),
            ]
            conn.executemany("INSERT INTO tiles VALUES (?,?,?,?,?)", tiles)
            # a_01 tem sprites 0 e 7... 1 e 2 estao no meio (lacuna), 9 esta alem do maximo
            for n in ("a_01_0", "a_01_8"):
                conn.execute("INSERT INTO sprites(name,pack,page,png) VALUES (?,?,?,?)", (n, "p", "pg", "x.png"))
            conn.commit()
            got = {r["name"]: r["reason"] for r in rm.classify(conn)}
            self.assertEqual(got["a_01_1"], "lacuna_no_pack")
            self.assertEqual(got["a_01_9"], "indice_alem_pack")
            self.assertEqual(got["a_01_on_3"], "lit_so_geometria")
            self.assertEqual(got["b_02_on_1"], "lit_definida")
            self.assertEqual(got["crafted_03_0"], "tileset_sem_sprite")
            self.assertEqual(got["g_01_5"], "sem_definicao")
            self.assertEqual(got["a_01_7"], "sem_definicao")
            self.assertNotIn("a_01_0", got)
            res = rm.write_report(conn, data)
            self.assertEqual(res["missing"], len(got))
            md = (data / "report_missing.md").read_text(encoding="utf-8")
            self.assertIn("crafted_03", md)
            self.assertTrue((data / "report_missing.csv").is_file())
            conn.close()
        self.assertEqual(rm.ranges([5, 1, 2, 3, 9, 10]), "1-3, 5, 9-10")


class ViewerTest(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            conn = make_db(data / "acervo.sqlite")
            conn.executemany("INSERT INTO tiles VALUES (?,?,?,?,?)", [
                ("bed_01_0", "bed_01", 0, "a.tiles", "moveis"), ("bed_01_1", "bed_01", 1, "a.tiles", "moveis"),
                ("books&misc_01_0", "books&misc_01", 0, "a.tiles", "decoracao"),
                ("lamp_01_on_0", "lamp_01_on", 0, "tileGeometry.txt", "iluminacao")])
            conn.execute("INSERT INTO sprites VALUES ('bed_01_0','P','pg','sprites/bed_01/bed_01_0.png',10,10,1,2,128,256,2)")
            conn.execute("INSERT INTO sprites VALUES ('books&misc_01_0','P','pg','sprites/books&misc_01/books&misc_01_0.png',10,10,1,2,128,256,2)")
            conn.execute("INSERT INTO geometry(name,shape_idx,shape,tx,ty,tz,rx,ry,rz,min_x,min_y,min_z,max_x,max_y,max_z) "
                         "VALUES ('bed_01_0',0,'box',0,0,0,0,0,0,-5000,0,-5000,5000,6000,5000)")
            conn.execute("INSERT INTO tile_props VALUES ('bed_01_0','CustomName','Bed')")
            conn.execute("INSERT INTO depth_maps VALUES ('bed_01_0','depth/bed_01/bed_01_0.png','DEPTH_bed_01.png',0,0,10)")
            conn.execute("INSERT INTO depth_assignments VALUES ('bed_01_1','bed_01_0')")
            conn.commit()
            res = viewer.build(data)
            self.assertEqual(res["tiles"], 4)
            self.assertEqual(res["with_png"], 2)
            self.assertEqual(res["with_geometry"], 1)
            self.assertEqual(res["with_depth"], 2)           # proprio + atribuido
            out = data / "viewer"
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('lang="pt-BR"', html)
            self.assertIn("Buscar por nome", html)
            txt = (out / "catalog.js").read_text(encoding="utf-8")
            self.assertTrue(txt.startswith("window.CAT="))
            cat = json.loads(txt[len("window.CAT="):-1])
            rows = {r[0]: r for r in cat["t"]}
            self.assertEqual(rows["bed_01_0"][4] & (viewer.F_PNG | viewer.F_GEO | viewer.F_DEP | viewer.F_DEF),
                             viewer.F_PNG | viewer.F_GEO | viewer.F_DEP | viewer.F_DEF)
            self.assertTrue(rows["bed_01_1"][4] & viewer.F_DEPA)
            self.assertFalse(rows["bed_01_1"][4] & viewer.F_PNG)
            self.assertTrue(rows["lamp_01_on_0"][4] & viewer.F_LIT)
            self.assertEqual(cat["falta"]["lamp_01_on_0"], "lit_so_geometria")
            self.assertEqual(cat["ov"], {})
            self.assertIn("Móveis", [c[1] for c in cat["cats"]])
            i = rows["bed_01_0"][1]
            chunk = (out / "d" / f"{i}.js").read_text(encoding="utf-8")
            self.assertIn('"CustomName"', chunk)
            self.assertIn('"bed_01_0"', chunk)
            conn.close()


if __name__ == "__main__":
    unittest.main()
