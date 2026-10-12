"""Testes da composição das texturas (sem Blender: buffers sintéticos).
Rodar: python -m unittest discover -s 05-Model-3D-Extractor-MCP/porte3d/tests -t 05-Model-3D-Extractor-MCP -v
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from porte3d import texturas as tx


def quadro_cor(rgb):
    q = np.zeros((256, 128, 4), np.uint8)
    q[..., :3] = rgb
    q[..., 3] = 255
    return q


class TestProjecao(unittest.TestCase):
    def test_pontos_conhecidos(self):
        p = np.array([[0, 0, 0], [0, 0, 1], [0.5, -0.5, 0], [0.5, 0.5, 0]], float)
        sx, sy = tx.projetar(p)
        np.testing.assert_allclose(sx, [64, 64, 64, 128])
        np.testing.assert_allclose(sy, [224, 224 - 78.38, 256, 224])

    def test_giro_180_troca_os_lados(self):
        p = np.array([[0.5, -0.5, 0.2]])
        a = tx.projetar(p, 180)
        b = tx.projetar(-p * [1, 1, -1])
        np.testing.assert_allclose(a, b, atol=1e-9)

    def test_face_dominante(self):
        n = np.array([[0.9, 0.1, 0], [0, -1, 0], [0.1, 0.2, -0.9]])
        self.assertEqual([tx.FACES[i] for i in tx.face_de(n)], ["+x", "-y", "-z"])

    def test_uv_lateral_de_cima_para_baixo(self):
        lo, hi = np.array([0, 0, 0.0]), np.array([1, 0.2, 2.0])
        u, v, comp = tx.uv_da_face(np.array([[0.25, 0.0, 2.0], [0.75, 0.0, 0.0]]), lo, hi, "-y")
        np.testing.assert_allclose(u, [0.25, 0.75])
        np.testing.assert_allclose(v, [0.0, 1.0])
        self.assertEqual(comp, 1.0)


class TestAdesivo(unittest.TestCase):
    def buf(self):
        # 1 linha x 3 texels: vê só da frente / só de trás / ninguém vê
        pos = np.array([[[0, -0.2, 0.1], [0, 0.2, 0.1], [0, 0.2, 0.2]]], float)
        return {"posicao": pos, "normal": np.array([[[0, -1, 0], [0, 1, 0], [0, 1, 0]]], float),
                "peca": np.array([[0, 0, 0]], np.int16),
                "vis_0": np.array([[1.0, 0, 0]]), "vis_180": np.array([[0, 1.0, 0]])}

    def test_escolhe_a_vista_que_enxerga_e_preenche_o_resto(self):
        b = self.buf()
        out, ok = tx.adesivo(b, [(quadro_cor((200, 0, 0)), 0.0, b["vis_0"]), (quadro_cor((0, 0, 200)), 180.0, b["vis_180"])])
        self.assertEqual(ok.tolist(), [[True, True, False]])
        np.testing.assert_allclose(out[0, 0], [200, 0, 0])
        np.testing.assert_allclose(out[0, 1], [0, 0, 200])
        out = tx.preencher(out, ok, b)
        np.testing.assert_allclose(out[0, 2], [0, 0, 200])     # mesma peça e mesma face (+y) que o texel 1

    def test_pixel_transparente_nao_conta(self):
        b = self.buf()
        q = quadro_cor((200, 0, 0))
        q[..., 3] = 0
        _, ok = tx.adesivo(b, [(q, 0.0, b["vis_0"])])
        self.assertFalse(ok.any())


class TestKit(unittest.TestCase):
    def test_recorte_aplicado_com_luz_da_face(self):
        r = {"pecas": [{"nome": "b", "origem": "b", "forma": "caixa", "min": [-0.3, -0.3, 0], "max": [0.3, 0.3, 0.6]}],
             "arte": {"modo": "kit", "recortes": {"lado": {"peca": "b", "face": "-y", "recorte": [0, 0, 1, 1]}},
                      "faces": {"b": {"lados": "lado"}}}}
        b = {"posicao": np.array([[[0, -0.3, 0.3], [0.3, 0, 0.3]]]), "normal": np.array([[[0, -1, 0], [1, 0, 0]]], float),
             "peca": np.array([[0, 0]], np.int16)}
        out = np.zeros((1, 2, 3), np.float32)
        ok = np.zeros((1, 2), bool)
        out, ok = tx.kit(b, r, quadro_cor((100, 100, 100)), out, ok)
        self.assertTrue(ok.all())
        np.testing.assert_allclose(out[0, 0], [100, 100, 100])
        np.testing.assert_allclose(out[0, 1], [100 * tx.LUZ["+x"]] * 3, rtol=1e-5)


class TestObj(unittest.TestCase):
    def test_um_material_so(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "malha.obj").write_text("mtllib malha.mtl\no m\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nusemtl p000_a\nf 1/1 2/1 3/1\nusemtl p001_b\nf 1/1 3/1 2/1\n")
            tx.gravar_obj(d, "x", "arte")
            obj = (d / "x_arte.obj").read_text()
            self.assertEqual(obj.count("usemtl"), 1)
            self.assertTrue(obj.startswith("mtllib x_arte.mtl"))
            self.assertIn("map_Kd arte.png", (d / "x_arte.mtl").read_text())


if __name__ == "__main__":
    unittest.main()
