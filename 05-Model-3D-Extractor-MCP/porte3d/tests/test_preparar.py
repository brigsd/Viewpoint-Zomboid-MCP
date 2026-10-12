"""Testes de porte3d.preparar com um acervo sintético (sem arquivos do jogo)."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from porte3d import acervo, preparar, receita
from porte3d.tests import AcervoSintetico

# duas caixas que se sobrepõem na tela: A fica na frente (x − y maior), B atrás e mais alta
A = {"nome": "a", "forma": "caixa", "min": [0.0, -0.5, 0.0], "max": [0.5, 0.0, 0.5], "material": "mat_a"}
B = {"nome": "b", "forma": "caixa", "min": [-0.5, 0.0, 0.0], "max": [0.0, 0.5, 1.0], "material": "mat_b"}


def _receita(pecas, sprites=None, **extra):
    r = {"versao": 1, "id": "objeto", "sprites": sprites or {"S": "obj_0"}, "pecas": pecas,
         "arte": {"modo": "adesivo"}, "material": "mat_a"}
    r.update(extra)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.ac = AcervoSintetico(self.tmp / "acervo")
        self.addCleanup(self.ac.close)
        self.db = self.ac.db

    def escrever(self, r) -> Path:
        p = self.tmp / "r.json"
        p.write_text(json.dumps(r), encoding="utf-8")
        return p


class TestMapaDePecas(unittest.TestCase):
    def setUp(self):
        self.pecas = receita.expandir(_receita([B, A]))["pecas"]       # B antes de A: a ordem não pode importar
        self.mapa = preparar.mapa_de_pecas(self.pecas)

    def test_pixel_fora_e_pixel_dentro(self):
        self.assertEqual(self.mapa[5, 5], -1)
        self.assertEqual(self.mapa[0, 64], -1)
        # topo da caixa B (z = 1, centro x = -0,25, y = 0,25): sx = 64, sy = 224 + 32·(-0,5) - 78,38
        self.assertEqual(self.mapa[int(224 - 16 - 78.38), 64], 0)
        # base da caixa A (z = 0): sx = 64, sy = 224 + 32·0,5 -> perto do chão, só A cobre
        self.assertEqual(self.mapa[int(224 + 16), 64], 1)

    def test_a_peca_mais_perto_da_camera_ganha(self):
        # em sx = 64, sy = 205 as duas caixas cobrem o pixel; A (índice 1) está na frente
        self.assertEqual(self.mapa[205, 64], 1)
        self.assertTrue((self.mapa == 0).any() and (self.mapa == 1).any())


class TestPreparar(Base):
    def frame_pintado(self):
        """Quadro em que cada pixel tem a cor do dono (A vermelho, B azul) e há um pixel isolado no pé do quadro."""
        mapa = preparar.mapa_de_pecas(receita.expandir(_receita([B, A]))["pecas"])
        q = np.zeros((256, 128, 4), np.uint8)
        q[mapa == 1] = (200, 30, 30, 255)
        q[mapa == 0] = (30, 30, 200, 255)
        return q

    def test_saidas_e_cores_estimadas(self):
        q = self.frame_pintado()
        self.ac.sprite("obj_0", q)
        pasta = preparar.preparar(self.escrever(_receita([B, A])), self.tmp / "saida", self.db)
        self.assertEqual(pasta, self.tmp / "saida" / "objeto")
        ent = pasta / "entrada"
        for f in ("frente.png", "tras.png", "frente_original.png", "tras_original.png", "receita.json"):
            self.assertTrue((ent / f).exists(), f)
        orig = np.asarray(Image.open(ent / "frente_original.png"))
        np.testing.assert_array_equal(orig, q)
        np.testing.assert_array_equal(np.asarray(Image.open(ent / "tras_original.png")), q)   # simétrico: o mesmo S
        frente = np.asarray(Image.open(ent / "frente.png"))
        self.assertEqual(frente.shape, (256, 128, 4))
        self.assertGreater((frente[..., 3] > 0).sum(), (q[..., 3] > 0).sum())               # com bleed cresce
        np.testing.assert_array_equal(np.asarray(Image.open(ent / "tras.png")), frente)
        out = json.loads((ent / "receita.json").read_text(encoding="utf-8"))
        self.assertEqual(out["cores"], {"mat_a": [200, 30, 30], "mat_b": [30, 30, 200]})
        self.assertEqual([p["nome"] for p in out["pecas"]], ["b", "a"])
        receita.validar(out)

    def test_cor_da_receita_nao_e_sobrescrita(self):
        self.ac.sprite("obj_0", self.frame_pintado())
        r = _receita([B, A], cores={"mat_a": [1, 2, 3]})
        pasta = preparar.preparar(self.escrever(r), self.tmp / "saida", self.db)
        out = json.loads((pasta / "entrada" / "receita.json").read_text(encoding="utf-8"))
        self.assertEqual(out["cores"], {"mat_a": [1, 2, 3], "mat_b": [30, 30, 200]})

    def test_mediana_ignora_pixels_fora_do_valor_tipico(self):
        q = self.frame_pintado()
        mapa = preparar.mapa_de_pecas(receita.expandir(_receita([B, A]))["pecas"])
        ys, xs = np.nonzero(mapa == 1)
        for k in range(5):                                  # poucos pixels de brilho no meio do vermelho
            q[ys[k * 3], xs[k * 3]] = (255, 255, 255, 255)
        self.ac.sprite("obj_0", q)
        pasta = preparar.preparar(self.escrever(_receita([B, A])), self.tmp / "saida", self.db)
        out = json.loads((pasta / "entrada" / "receita.json").read_text(encoding="utf-8"))
        self.assertEqual(out["cores"]["mat_a"], [200, 30, 30])

    def test_pixels_transparentes_nao_contam(self):
        q = self.frame_pintado()
        q[q[..., 2] == 200] = 0          # B some do desenho (transparente)
        self.ac.sprite("obj_0", q)
        pecas = receita.expandir(_receita([B, A]))["pecas"]
        cores = preparar.estimar_cores(pecas, q)
        self.assertEqual(cores["mat_a"], [200, 30, 30])
        self.assertEqual(cores["mat_b"], [200, 30, 30])      # sem pixels próprios: mediana do desenho todo

    def test_tras_n_usa_o_sprite_n(self):
        q = self.frame_pintado()
        n = np.zeros((256, 128, 4), np.uint8)
        n[150:170, 30:60] = (10, 200, 10, 255)
        self.ac.sprite("obj_0", q)
        self.ac.sprite("obj_2", n)
        r = _receita([B, A], sprites={"S": "obj_0", "N": "obj_2"}, tras="N")
        pasta = preparar.preparar(self.escrever(r), self.tmp / "saida", self.db)
        ent = pasta / "entrada"
        np.testing.assert_array_equal(np.asarray(Image.open(ent / "tras_original.png")), n)
        np.testing.assert_array_equal(np.asarray(Image.open(ent / "tras.png")), acervo.bleed(n))
        np.testing.assert_array_equal(np.asarray(Image.open(ent / "frente_original.png")), q)

    def test_sprite_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            preparar.preparar(self.escrever(_receita([A])), self.tmp / "saida", self.db)

    def test_receita_invalida(self):
        r = _receita([A])
        del r["arte"]
        with self.assertRaises(receita.ReceitaInvalida):
            preparar.preparar(self.escrever(r), self.tmp / "saida", self.db)

    def test_espelhos_e_material_padrao(self):
        # a peça espelhada herda o material; o material padrão da receita entra nas cores
        self.ac.sprite("obj_0", self.frame_pintado())
        a = {k: v for k, v in A.items() if k != "material"}
        a["espelhar"] = ["x"]
        pasta = preparar.preparar(self.escrever(_receita([a])), self.tmp / "saida", self.db)
        out = json.loads((pasta / "entrada" / "receita.json").read_text(encoding="utf-8"))
        self.assertEqual([p["nome"] for p in out["pecas"]], ["a", "a.x"])
        self.assertEqual(list(out["cores"]), ["mat_a"])


if __name__ == "__main__":
    unittest.main()
