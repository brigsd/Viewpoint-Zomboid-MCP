"""Testes de porte3d.inspecao com um acervo sintético (sem arquivos do jogo)."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from porte3d import acervo, inspecao
from porte3d.tests import AcervoSintetico

# Unidades do jogo em 1/10000 de tile: (X, Y para cima, Z para o sul); receita: x = X, y = -Z, z = Y.
CAIXA_60 = ((-3000, 0, -3000), (3000, 10000, 3000))          # 0,6 x 0,6 x 1,0 m, centrada no tile


def quadro_de(pecas_mask: np.ndarray, cor=(150, 150, 150)) -> np.ndarray:
    q = np.zeros((256, 128, 4), np.uint8)
    q[pecas_mask] = (*cor, 255)
    return q


def ruido(mask: np.ndarray, semente: int) -> np.ndarray:
    """Quadro com a máscara e cores aleatórias (para o espelho não ser simétrico por acaso)."""
    rng = np.random.default_rng(semente)
    q = np.zeros((256, 128, 4), np.uint8)
    q[..., :3] = rng.integers(0, 255, (256, 128, 3))
    q[..., 3] = np.where(mask, 255, 0)
    return q


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pasta = Path(self._tmp.name)
        self.ac = AcervoSintetico(self.pasta / "acervo")
        self.addCleanup(self.ac.close)
        self.db = self.ac.db
        self.saida = self.pasta / "saida"

    def mascara(self, nome: str) -> np.ndarray:
        return inspecao.mascara_geometria(acervo.formas(self.db, nome))

    def insp(self, nome: str, **kw) -> dict:
        return inspecao.inspecionar(nome, saida=self.saida, db=self.db, **kw)

    def mesa(self, nome: str, pes: int):
        """Mesa 1 x 1 m de tampo, pés de 6 x 6 cm nos cantos (4 ou 3 pés)."""
        cantos = [(-4400, -4400), (3800, -4400), (3800, 3800), (-4400, 3800)]       # (X, Z) do canto de menor X e Z
        for i, (x, z) in enumerate(cantos[:pes]):
            self.ac.caixa(nome, i, (x, 0, z), (x + 600, 5800, z + 600))
        self.ac.caixa(nome, pes, (-5000, 5800, -5000), (5000, 7600, 5000))


class TestMascaraEMedidas(Base):
    def test_area_da_silhueta_bate_com_o_calculo(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        # hexágono: losango do topo (diagonais 64·(w+d) e 32·(w+d)) mais a varredura vertical da largura inteira
        w = 64 * 1.2
        esperado = w * 38.4 / 2 + w * 78.38 * 1.0
        area = int(self.mascara("s").sum())
        self.assertAlmostEqual(area, esperado, delta=esperado * 0.02)
        # o centro do desenho cai onde a fórmula do CONTRATO manda: base do tile em (64, 224)
        m = self.mascara("s")
        ys, xs = np.nonzero(m)
        self.assertAlmostEqual((xs.min() + xs.max() + 1) / 2, 64, delta=1)
        self.assertAlmostEqual(ys.max() + 1, 224 + 19.2, delta=1)           # ponta da frente da base: sy = 224 + 32·0,6

    def test_geometria_igual_ao_desenho(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        self.ac.sprite("s", quadro_de(self.mascara("s")))
        m = self.insp("s")
        self.assertEqual(m["contorno_0"], 1.0)
        self.assertEqual(m["cobertura"], 1.0)
        self.assertEqual(m["sobra"], 0.0)
        self.assertEqual(m["caixa"]["altura"], 1.0)
        self.assertEqual(m["caixa"]["largura"], 0.6)
        self.assertEqual(m["caixa"]["profundidade"], 0.6)
        self.assertEqual(m["tipos"], {"caixa": 1, "cilindro": 0, "prisma": 0})
        self.assertFalse(m["fino"])
        self.assertFalse(m["multi_tile"])

    def test_desenho_maior_que_a_geometria_baixa_a_cobertura(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        geo = self.mascara("s")
        extra = np.zeros_like(geo)
        extra[20:80, 10:70] = True                  # 3600 pixels de desenho longe da caixa
        q = quadro_de(geo | extra)
        self.ac.sprite("s", q)
        m = self.insp("s")
        n_geo, n_ext = int(geo.sum()), int(extra.sum())
        self.assertAlmostEqual(m["cobertura"], n_geo / (n_geo + n_ext), places=3)
        self.assertEqual(m["sobra"], 0.0)
        self.assertAlmostEqual(m["contorno_0"], n_geo / (n_geo + n_ext), places=3)
        self.assertTrue(any("cobre só" in s and "falta peça" in s for s in m["sugestao"]), m["sugestao"])

    def test_geometria_maior_que_o_desenho_aumenta_a_sobra(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        geo = self.mascara("s")
        meio = geo.copy()
        meio[:, 64:] = False                        # só a metade esquerda foi desenhada
        self.ac.sprite("s", quadro_de(meio))
        m = self.insp("s")
        self.assertEqual(m["cobertura"], 1.0)
        self.assertAlmostEqual(m["sobra"], 1 - meio.sum() / geo.sum(), places=3)
        self.assertLess(m["contorno_0"], 0.6)
        self.assertTrue(any("cai fora do desenho" in s for s in m["sugestao"]))
        self.assertTrue(any("contorno em 0°" in s for s in m["sugestao"]))

    def test_placa_de_sombra_nao_conta(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        self.ac.caixa("s", 1, (-5000, 0, -5000), (5000, 100, 5000))      # sombra no chão, descartada por acervo.formas
        self.ac.sprite("s", quadro_de(self.mascara("s")))
        m = self.insp("s")
        self.assertEqual(m["n_formas"], 1)
        self.assertEqual(m["n_formas_jogo"], 2)
        self.assertEqual(m["contorno_0"], 1.0)


class TestSimetria(Base):
    def test_mesa_de_4_pes_tem_par_em_tudo(self):
        self.mesa("m4", 4)
        self.ac.sprite("m4", quadro_de(self.mascara("m4")))
        m = self.insp("m4")
        self.assertEqual(m["n_formas"], 5)
        self.assertEqual(m["pecas_sem_par"], [])
        self.assertEqual(m["pecas_provavelmente_faltando"], [])
        self.assertEqual(m["n_pes"], 4)
        self.assertEqual(m["centro_simetria"], [0.0, 0.0])
        self.assertFalse(any("pé" in s for s in m["sugestao"]), m["sugestao"])

    def test_mesa_de_3_pes_aponta_o_pe_escondido(self):
        self.mesa("m3", 3)
        self.ac.sprite("m3", quadro_de(self.mascara("m3")))
        m = self.insp("m3")
        self.assertEqual(m["n_pes"], 3)
        sem = {p["peca"]: p["sem_par"] for p in m["pecas_sem_par"]}
        self.assertEqual(set(sem), {"forma_0", "forma_1", "forma_2"})          # os 3 pés, o tampo tem par consigo
        self.assertEqual(sorted(sem["forma_0"] + sem["forma_1"] + sem["forma_2"]), ["x", "xy", "y"])
        falta = m["pecas_provavelmente_faltando"]
        self.assertEqual(len(falta), 1)                                         # os 3 espelhos caem no mesmo pé
        self.assertEqual(falta[0]["votos"], 3)
        self.assertTrue(falta[0]["pe"])
        # o pé que falta é o do canto (X de -0,44 a -0,38, Z de 0,38 a 0,44 => y de -0,44 a -0,38)
        # cantos descritos: (-4400,-4400), (3800,-4400), (3800,3800) em (X, Z); falta (-4400, 3800)
        self.assertEqual(falta[0]["min"], [-0.44, -0.44, 0.0])
        self.assertEqual(falta[0]["max"], [-0.38, -0.38, 0.58])
        self.assertTrue(any("3 pés descritos" in s and "pé escondido" in s and "simetria" in s for s in m["sugestao"]),
                        m["sugestao"])

    def test_tolerancia_de_2_cm(self):
        # pé de trás 1,5 cm fora do lugar ainda conta como par; 3 cm fora, não
        for nome, desloc in (("perto", 150), ("longe", 300)):
            cantos = [(-4400, -4400), (3800, -4400), (3800, 3800), (-4400 + desloc, 3800)]
            for i, (x, z) in enumerate(cantos):
                self.ac.caixa(nome, i, (x, 0, z), (x + 600, 5800, z + 600))
            self.ac.caixa(nome, 4, (-5000, 5800, -5000), (5000, 7600, 5000))
            self.ac.sprite(nome, quadro_de(self.mascara(nome)))
        self.assertEqual(self.insp("perto")["pecas_sem_par"], [])
        self.assertTrue(self.insp("longe")["pecas_sem_par"])


class TestDirecoes(Base):
    def _quatro(self, mask_s: np.ndarray, q_e: np.ndarray, q_n: np.ndarray, q_w: np.ndarray | None = None):
        q_s = ruido(mask_s, 1)
        props = {"CustomName": "Caixote", "GroupName": "Teste"}
        for f, i, q in (("S", 0, q_s), ("E", 1, q_e), ("N", 2, q_n), ("W", 3, q_w)):
            if q is None:
                continue
            n = f"obj_{i}"
            self.ac.sprite(n, q)
            self.ac.tile(n, "obj", i, Facing=f, **props)
        self.ac.caixa("obj_0", 0, *CAIXA_60)
        return q_s

    def test_espelho_de_lado_e_traseira_real(self):
        mask = np.zeros((256, 128), bool)
        mask[100:200, 30:80] = True
        mask[100:120, 80:100] = True                      # assimétrico, para o espelho ser de verdade
        q_s = ruido(mask, 1)
        q_e = q_s[:, ::-1].copy()                          # E = S espelhado
        mask_n = np.zeros_like(mask)
        mask_n[90:210, 20:90] = True
        self._quatro(mask, q_e, ruido(mask_n, 3), None)
        # sobrescreve o quadro S com o mesmo usado para fazer E (o helper gerou outro com a mesma semente: igual)
        m = self.insp("obj_0")
        self.assertEqual(list(m["sprites"]), ["S", "E", "N"])
        self.assertEqual(m["espelhado_E_S"], 1.0)
        self.assertEqual(m["silhueta_espelho_E_S"], 1.0)
        self.assertTrue(m["E_e_espelho_de_S"])
        self.assertIsNone(m["espelhado_W_N"])               # sem W
        self.assertFalse(m["W_e_espelho_de_N"])
        self.assertTrue(m["tem_N"])
        self.assertIn("E é o espelho de S", m["sugestao"])
        self.assertIn("há desenho de trás real (N): usar tras = N", m["sugestao"])

    def test_lado_diferente_nao_e_espelho(self):
        mask = np.zeros((256, 128), bool)
        mask[100:200, 30:80] = True
        mask_e = np.zeros_like(mask)
        mask_e[60:120, 10:120] = True
        self._quatro(mask, ruido(mask_e, 5), ruido(mask, 6))
        m = self.insp("obj_0")
        self.assertLess(m["espelhado_E_S"], 0.6)
        self.assertFalse(m["E_e_espelho_de_S"])
        self.assertNotIn("E é o espelho de S", m["sugestao"])

    def test_traseira_que_e_a_frente_repetida(self):
        mask = np.zeros((256, 128), bool)
        mask[100:200, 30:80] = True
        q_s = ruido(mask, 1)
        self._quatro(mask, q_s[:, ::-1].copy(), q_s.copy())          # N é cópia exata de S
        m = self.insp("obj_0")
        self.assertEqual(m["N_igual_S"], 1.0)
        self.assertFalse(m["tem_N"])
        self.assertTrue(any("tras = simetrico" in s for s in m["sugestao"]))

    def test_sem_direcoes(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        self.ac.sprite("s", quadro_de(self.mascara("s")))
        m = self.insp("s")
        self.assertEqual(m["sprites"], {"S": "s"})
        self.assertIsNone(m["espelhado_E_S"])
        self.assertFalse(m["tem_N"])
        self.assertTrue(any("sem desenho de trás" in s for s in m["sugestao"]))


class TestMultiTileEFino(Base):
    def test_multi_tile(self):
        self.ac.caixa("s", 0, *CAIXA_60)
        self.ac.sprite("s", quadro_de(self.mascara("s")))
        self.ac.tile("s", "sofa", 0, SpriteGridPos="0,1", CustomName="Sofa", Facing="S")
        m = self.insp("s")
        self.assertTrue(m["multi_tile"])
        self.assertTrue(any("mais de um tile" in s for s in m["sugestao"]))
        self.ac.caixa("t", 0, *CAIXA_60)
        self.ac.sprite("t", quadro_de(self.mascara("t")))
        self.ac.tile("t", "sofa", 1, CustomName="Sofa", Facing="S")
        self.assertFalse(self.insp("t")["multi_tile"])

    def test_poligono_fino_e_candidato_a_nao_portar(self):
        # cortina: polígono vertical de 40 x 80 cm, vira prisma de 1 cm
        self.ac.poligono("c", 0, [(-2000, 0), (2000, 0), (2000, 8000), (-2000, 8000)])
        self.ac.sprite("c", quadro_de(self.mascara("c")))
        m = self.insp("c")
        self.assertTrue(m["fino"])
        self.assertEqual(m["tipos"]["prisma"], 1)
        self.assertLess(m["menor_medida_peca"], 0.015)
        self.assertTrue(any("fino/vazado" in s and "não portar" in s for s in m["sugestao"]), m["sugestao"])
        self.assertGreater(m["pixels_geometria"], 100)            # a peça de 1 cm não some na rasterização

    def test_caixa_de_1_cm_e_fina(self):
        self.ac.caixa("p", 0, (-3000, 0, -50), (3000, 8000, 50))      # 1 cm de espessura
        self.ac.sprite("p", quadro_de(self.mascara("p")))
        self.assertTrue(self.insp("p")["fino"])

    def test_objeto_de_parede(self):
        self.ac.caixa("l", 0, *CAIXA_60)
        self.ac.sprite("l", quadro_de(self.mascara("l")))
        self.ac.tile("l", "luz", 0, CustomName="Wall Lamp", Facing="S", MoveType="WallObject", attachedN="")
        m = self.insp("l")
        self.assertTrue(m["montado_na_parede"])
        self.assertTrue(any("objeto de parede" in s and "não portar" in s for s in m["sugestao"]))


class TestSemGeometriaEArquivos(Base):
    def test_sem_geometria(self):
        self.ac.sprite("nada")
        m = self.insp("nada")
        self.assertFalse(m["tem_geometria"])
        self.assertEqual(m["n_formas"], 0)
        self.assertIsNone(m["contorno_0"])
        self.assertIsNone(m["cobertura"])
        self.assertIsNone(m["caixa"])
        self.assertEqual(m["pecas_sem_par"], [])
        self.assertIn("sem geometria: candidato a não portar", m["sugestao"])
        for arq in ("medidas.json", "direcoes.png", "geometria.png", "cobertura.png"):
            self.assertTrue((self.saida / "nada" / arq).exists(), arq)
        self.assertFalse((self.saida / "nada" / "profundidade.png").exists())

    def test_arquivos_e_json(self):
        self.mesa("mesa_01", 3)
        self.ac.sprite("mesa_01", quadro_de(self.mascara("mesa_01")))
        m = self.insp("mesa_01", id="minha_mesa")
        pasta = self.saida / "minha_mesa"
        self.assertEqual(m["pasta"], str(pasta))
        for arq in ("medidas.json", "direcoes.png", "geometria.png", "cobertura.png"):
            self.assertTrue((pasta / arq).exists(), arq)
            if arq.endswith(".png"):
                with Image.open(pasta / arq) as im:
                    self.assertGreater(im.size[0], 300)
                    self.assertGreater(im.size[1], 700)
        lido = json.loads((pasta / "medidas.json").read_text(encoding="utf-8"))
        for chave in ("sprites", "tem_geometria", "n_formas", "tipos", "pecas", "multi_tile", "material", "caixa", "contorno_0",
                      "cobertura", "sobra", "espelhado_E_S", "espelhado_W_N", "tem_N", "pecas_sem_par", "fino",
                      "profundidade", "sugestao"):
            self.assertIn(chave, lido)
        self.assertEqual(lido["n_formas"], 4)
        # o id padrão é o slug do nome
        self.insp("mesa_01")
        self.assertTrue((self.saida / "mesa_01" / "medidas.json").exists())

    def test_profundidade(self):
        self.ac.caixa("d", 0, *CAIXA_60)
        geo = self.mascara("d")
        self.ac.sprite("d", quadro_de(geo))
        dep = np.zeros((256, 128, 2), np.uint8)
        dep[..., 0][geo] = 120
        dep[..., 1][geo] = 255
        dep[..., 0][:, 64:][geo[:, 64:]] = 200          # dois níveis de profundidade
        (self.ac.pasta / "depth").mkdir()
        Image.fromarray(dep, "LA").save(self.ac.pasta / "depth" / "d.png")
        self.db.execute("insert into depth_maps(name,png,sheet,col,row,nonzero) values (?,?,?,?,?,?)",
                        ("d", "depth/d.png", "DEPTH_x.png", 0, 0, int(geo.sum())))
        self.db.commit()
        m = self.insp("d")
        self.assertTrue(m["profundidade"]["existe"])
        self.assertEqual(m["profundidade"]["cobertura"], 1.0)
        self.assertEqual(m["profundidade"]["fora_do_desenho"], 0.0)
        self.assertTrue((self.saida / "d" / "profundidade.png").exists())

    def test_cli_resumo(self):
        self.mesa("mesa_01", 3)
        self.ac.sprite("mesa_01", quadro_de(self.mascara("mesa_01")))
        txt = inspecao.resumo(self.insp("mesa_01"))
        self.assertIn("sugestao:", txt)
        self.assertIn("pés descritos", txt)


if __name__ == "__main__":
    unittest.main()
