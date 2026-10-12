"""Testes de porte3d.acervo com um acervo sintético (sem arquivos do jogo)."""
import tempfile
import unittest

import numpy as np

from porte3d import acervo, receita
from porte3d.tests import AcervoSintetico


def _receita_com(pecas: list[dict]) -> dict:
    return {"versao": 1, "id": "teste", "sprites": {"S": "x"}, "pecas": pecas, "arte": {"modo": "adesivo"}}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ac = AcervoSintetico(self._tmp.name)
        self.addCleanup(self.ac.close)
        self.db = self.ac.db

    def pecas(self, nome="s"):
        ign = []
        p = acervo.formas(self.db, nome, ign)
        receita.validar(_receita_com(p))        # toda saída de formas() tem que ser uma receita válida
        self.ign = ign
        return p

    def assertVec(self, a, b, tol=1e-4):
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, delta=tol)


class TestQuadroEBleed(Base):
    def test_abrir_e_quadro_com_recorte_no_lugar(self):
        q = np.zeros((256, 128, 4), np.uint8)
        q[100:140, 40:90] = (10, 20, 30, 255)
        self.ac.sprite("a", q)
        self.ac.sprite("um_x", q, scale=1)
        db = acervo.abrir(self.ac.db_path)
        self.addCleanup(db.close)
        out = acervo.quadro(db, "a")
        self.assertEqual(out.shape, (256, 128, 4))
        np.testing.assert_array_equal(out, q)
        self.assertIsNone(acervo.quadro(db, "um_x"))        # só escala 2
        self.assertIsNone(acervo.quadro(db, "nao_existe"))
        with self.assertRaises(FileNotFoundError):
            acervo.abrir(self.ac.pasta / "nada.sqlite")

    def test_bleed_espalha_cor_e_marca_opaco(self):
        q = np.zeros((256, 128, 4), np.uint8)
        q[100:104, 50:54] = (200, 100, 50, 255)
        out = acervo.bleed(q, 1)
        self.assertEqual(tuple(out[99, 49]), (200, 100, 50, 255))      # diagonal vizinha
        self.assertEqual(tuple(out[104, 54]), (200, 100, 50, 255))
        self.assertEqual(out[98, 49, 3], 0)                              # n = 1: só um pixel
        self.assertEqual(q[99, 49, 3], 0)                                # a entrada não muda
        out3 = acervo.bleed(q, 3)
        self.assertEqual(out3[97, 47, 3], 255)
        self.assertEqual(out3[96, 46, 3], 0)

    def test_bleed_nao_da_a_volta_no_quadro(self):
        q = np.zeros((256, 128, 4), np.uint8)
        q[255, 60] = (255, 0, 0, 255)           # pixel opaco na última linha
        q[100, 0] = (0, 255, 0, 255)            # e outro na primeira coluna
        out = acervo.bleed(q)                   # passes padrão
        self.assertEqual(out[0, :, 3].max(), 0)         # nada reaparece no topo
        self.assertEqual(out[:, 127, 3][90:110].max(), 0)  # nem na última coluna
        self.assertEqual(out[255, 60, 3], 255)
        self.assertEqual(out[250, 60, 3], 255)          # mas espalha para cima normalmente


class TestFormasBox(Base):
    def test_unidade_e_inversao_de_eixos(self):
        # jogo: X leste, Y cima, Z sul; receita: x = X, y = -Z, z = Y; 1/10000 de tile -> metro
        self.ac.caixa("s", 0, (1000, 0, 2000), (3000, 5000, 4000))
        p = self.pecas()
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["nome"], "forma_0")
        self.assertEqual(p[0]["forma"], "caixa")
        self.assertVec(p[0]["min"], [0.1, -0.4, 0.0])
        self.assertVec(p[0]["max"], [0.3, -0.2, 0.5])
        self.assertNotIn("rot", p[0])

    def test_translate(self):
        self.ac.caixa("s", 0, (1000, 0, 2000), (3000, 5000, 4000), t=(1000, 500, 2000))
        p = self.pecas()
        self.assertVec(p[0]["min"], [0.2, -0.6, 0.05])
        self.assertVec(p[0]["max"], [0.4, -0.4, 0.55])

    def test_rotacao_90_sentido_e_deslocamento(self):
        # caixa fora do centro girada +90 graus em torno do Y do jogo: o centro (3000,.,0) vai para Z = -3000 (y = +0,3)
        self.ac.caixa("s", 0, (2000, 0, -500), (4000, 1000, 500), r=(0, 900000, 0))
        p = self.pecas()
        self.assertVec(p[0]["min"], [-0.05, 0.2, 0.0])
        self.assertVec(p[0]["max"], [0.05, 0.4, 0.1])
        self.assertNotIn("rot", p[0])
        # -90 graus vai para o lado oposto
        self.ac.caixa("n", 0, (2000, 0, -500), (4000, 1000, 500), r=(0, -900000, 0))
        q = self.pecas("n")
        self.assertVec(q[0]["min"], [-0.05, -0.4, 0.0])
        self.assertVec(q[0]["max"], [0.05, -0.2, 0.1])

    def test_rotacao_quase_90_do_jogo_e_arredondada(self):
        # o arquivo tem -899802 (-89,98 graus): sem rot de ruido
        self.ac.caixa("s", 0, (-4433, 0, -3477), (4433, 15723, 3600), t=(1358, 0, 246), r=(0, -899802, 0))
        p = self.pecas()
        self.assertNotIn("rot", p[0])
        self.assertVec(p[0]["min"], [-0.2242, -0.4679, 0.0], 2e-3)
        self.assertVec(p[0]["max"], [0.4835, 0.4187, 1.5723], 2e-3)

    def test_rotacao_45_vira_rot_em_z_com_sinal_certo(self):
        self.ac.caixa("s", 0, (-1000, 0, -500), (1000, 1000, 500), r=(0, 450000, 0))
        p = self.pecas()
        self.assertVec(p[0]["min"], [-0.1, -0.05, 0.0])
        self.assertVec(p[0]["max"], [0.1, 0.05, 0.1])
        self.assertVec(p[0]["rot"], [0.0, 0.0, 45.0], 0.02)

    def test_rotacao_em_x_inclina_a_caixa(self):
        # +30 graus em torno do X do jogo (leste): o topo da caixa (Y) cai para o lado do Z (sul), ou seja y negativo
        self.ac.caixa("s", 0, (-500, 0, -500), (500, 2000, 500), r=(300000, 0, 0))
        p = self.pecas()
        self.assertVec(p[0]["rot"], [30.0, 0.0, 0.0], 0.02)
        # o centro (0, 0.1, 0) vira Rx(30)(0, 0.1, 0) = (0, 0.1 cos, 0.1 sin) em (Y, Z) do jogo -> y da receita = -0.1 sin
        centro_y = (p[0]["min"][1] + p[0]["max"][1]) / 2
        self.assertAlmostEqual(centro_y, -0.1 * np.sin(np.radians(30)), places=3)
        centro_z = (p[0]["min"][2] + p[0]["max"][2]) / 2
        self.assertAlmostEqual(centro_z, 0.1 * np.cos(np.radians(30)), places=3)

    def test_180_90_180_equivale_a_giro_em_y(self):
        self.ac.caixa("s", 0, (-1000, 0, -500), (1000, 1000, 500), r=(1800000, 900000, 1800000))
        p = self.pecas()
        self.assertEqual(p[0]["forma"], "caixa")
        self.assertNotIn("rot", p[0])
        for a, b in zip(p[0]["min"], p[0]["max"]):
            self.assertLess(a, b)

    def test_placa_de_sombra_e_descartada(self):
        self.ac.caixa("s", 0, (-5000, 0, -5000), (5000, 200, 5000))
        self.ac.caixa("s", 1, (-2000, 0, -2000), (2000, 8000, 2000))
        p = self.pecas()
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["nome"], "forma_0")
        self.assertAlmostEqual(p[0]["max"][2], 0.8)
        self.assertEqual([i for i, _ in self.ign], [0])
        self.assertIn("sombra", self.ign[0][1])

    def test_placa_sozinha_fica(self):
        # um tapete e so uma caixa fina no chao: nao pode sumir
        self.ac.caixa("s", 0, (-5000, 0, -5000), (5000, 200, 5000))
        self.assertEqual(len(self.pecas()), 1)

    def test_caixa_fina_pequena_nao_e_placa(self):
        self.ac.caixa("s", 0, (-1000, 0, -1000), (1000, 200, 1000))
        self.ac.caixa("s", 1, (-2000, 3000, -2000), (2000, 5000, 2000))
        self.assertEqual(len(self.pecas()), 2)

    def test_forma_desconhecida_e_ignorada_com_motivo(self):
        self.ac.caixa("s", 0, (-1000, 0, -1000), (1000, 5000, 1000))
        self.ac.outra("s", 1, "esfera", "esfera\n{\n}")
        p = self.pecas()
        self.assertEqual(len(p), 1)
        self.assertEqual(self.ign[0][0], 1)

    def test_sem_geometria(self):
        self.assertEqual(acervo.formas(self.db, "nada"), [])


class TestFormasCilindroEPoligono(Base):
    def test_cilindro_em_pe(self):
        # padrao do jogo: eixo = Z local, origem no centro; girado 270 graus em X fica de pe
        self.ac.cilindro("s", 0, 1000, 10000, t=(0, 5000, 0), r=(2700000, 0, 0))
        p = self.pecas()
        self.assertEqual(p[0]["forma"], "cilindro")
        self.assertEqual(p[0]["eixo"], "z")
        self.assertVec(p[0]["centro"], [0.0, 0.0, 0.0])       # centro da base: 0,5 m abaixo do meio
        self.assertAlmostEqual(p[0]["altura"], 1.0)
        self.assertAlmostEqual(p[0]["raio"], 0.1)
        self.assertNotIn("rot", p[0])

    def test_cilindro_sem_giro_deita_no_eixo_y_da_receita(self):
        self.ac.cilindro("s", 0, 500, 4000, t=(1000, 5000, 0))
        p = self.pecas()
        self.assertEqual(p[0]["eixo"], "y")
        self.assertVec(p[0]["centro"], [0.1, -0.2, 0.5])     # base no lado menor de y, meio em y = 0

    def test_cilindro_girado_em_y_vira_eixo_x(self):
        self.ac.cilindro("s", 0, 500, 4000, t=(0, 5000, 3000), r=(0, 900000, 0))
        p = self.pecas()
        self.assertEqual(p[0]["eixo"], "x")
        self.assertAlmostEqual(p[0]["centro"][1], -0.3)
        self.assertAlmostEqual(abs(p[0]["centro"][0]), 0.2)

    def test_cilindro_inclinado_leva_rot(self):
        self.ac.cilindro("s", 0, 500, 4000, t=(0, 5000, 0), r=(2700000, 0, 300000))
        p = self.pecas()
        self.assertIn("rot", p[0])

    def test_poligono_em_pe_vira_prisma_fino(self):
        self.ac.poligono("s", 0, [(-1000, 0), (1000, 0), (1000, 2000), (-1000, 2000)], t=(0, 0, 3000))
        p = self.pecas()
        self.assertEqual(p[0]["forma"], "prisma")
        self.assertEqual(p[0]["eixo"], "y")
        self.assertAlmostEqual(p[0]["de"], -0.305)
        self.assertAlmostEqual(p[0]["ate"], -0.295)
        self.assertEqual(sorted(map(tuple, p[0]["perfil"])), [(-0.1, 0.0), (-0.1, 0.2), (0.1, 0.0), (0.1, 0.2)])
        pf = p[0]["perfil"]
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pf, pf[1:] + pf[:1]))
        self.assertGreater(area, 0)         # anti-horario

    def test_poligono_deitado_vira_prisma_com_rot(self):
        # quadrado deitado a 0,8663 m de altura (plane = XZ, girado 270 graus em X)
        self.ac.poligono("s", 0, [(-5000, -5000), (5000, -5000), (5000, 5000), (-5000, 5000)], plano="XZ",
                         t=(0, 8663, 0), r=(2700000, 0, 0))
        p = self.pecas()
        self.assertEqual(p[0]["forma"], "prisma")
        self.assertEqual(p[0]["eixo"], "y")
        self.assertVec(p[0]["rot"], [-90.0, 0.0, 0.0], 0.02)
        zs = [z for _, z in p[0]["perfil"]]
        self.assertAlmostEqual((min(zs) + max(zs)) / 2, 0.8663, places=4)

    def test_poligono_degenerado_e_ignorado_com_motivo(self):
        self.ac.caixa("s", 0, (-1000, 0, -1000), (1000, 5000, 1000))
        self.ac.poligono("s", 1, [(0, 0), (1000, 0), (2000, 0)])
        p = self.pecas()
        self.assertEqual(len(p), 1)
        self.assertEqual(self.ign[0][0], 1)


class TestDirecoes(Base):
    def setUp(self):
        super().setUp()
        for i, f in enumerate("SENW"):
            self.ac.tile(f"ts_a_{i}", "ts_a", i, Facing=f, CustomName="Geladeira", GroupName="Cozinha")
            self.ac.sprite(f"ts_a_{i}")
        self.ac.tile("ts_a_4", "ts_a", 4, Facing="S", CustomName="Outra", GroupName="Cozinha")
        self.ac.sprite("ts_a_4")
        self.ac.tile("ts_a_5", "ts_a", 5, Facing="E", CustomName="Geladeira", GroupName="Cozinha", SpriteGridPos="1,0")
        self.ac.sprite("ts_a_5")
        self.ac.tile("ts_b_0", "ts_b", 0, Facing="N", CustomName="Geladeira", GroupName="Cozinha")
        self.ac.sprite("ts_b_0")
        self.ac.tile("solto_0", "solto", 0, CustomName="Vaso")
        self.ac.sprite("solto_0")

    def test_agrupa_pelas_quatro_direcoes(self):
        esperado = {"S": "ts_a_0", "E": "ts_a_1", "N": "ts_a_2", "W": "ts_a_3"}
        self.assertEqual(acervo.direcoes(self.db, "ts_a_0"), esperado)
        self.assertEqual(acervo.direcoes(self.db, "ts_a_2"), esperado)      # partindo de outra direcao
        self.assertEqual(list(acervo.direcoes(self.db, "ts_a_1")), ["S", "E", "N", "W"])

    def test_nao_mistura_nome_tileset_nem_grade(self):
        d = acervo.direcoes(self.db, "ts_a_0")
        self.assertNotIn("ts_a_4", d.values())
        self.assertNotIn("ts_a_5", d.values())
        self.assertNotIn("ts_b_0", d.values())

    def test_sem_facing(self):
        self.assertEqual(acervo.direcoes(self.db, "solto_0"), {"S": "solto_0"})
        self.assertEqual(acervo.direcoes(self.db, "nao_existe"), {"S": "nao_existe"})

    def test_so_algumas_direcoes(self):
        self.ac.tile("p_0", "p", 0, Facing="S", CustomName="Mesa")
        self.ac.tile("p_1", "p", 1, Facing="E", CustomName="Mesa")
        self.ac.sprite("p_0")
        self.ac.sprite("p_1")
        self.assertEqual(acervo.direcoes(self.db, "p_0"), {"S": "p_0", "E": "p_1"})

    def test_sprite_sem_escala_2_fica_de_fora(self):
        self.ac.tile("q_0", "q", 0, Facing="S", CustomName="M")
        self.ac.tile("q_1", "q", 1, Facing="E", CustomName="M")
        self.ac.sprite("q_0")
        self.ac.sprite("q_1", scale=1)
        self.assertEqual(acervo.direcoes(self.db, "q_0"), {"S": "q_0"})


class TestEspelhado(Base):
    def setUp(self):
        super().setUp()
        a = np.zeros((256, 128, 4), np.uint8)
        a[100:140, 20:60] = (200, 0, 0, 255)
        a[120:160, 70:90] = (0, 200, 0, 255)
        self.ac.sprite("a", a)
        self.ac.sprite("b", a[:, ::-1].copy())
        c = np.zeros((256, 128, 4), np.uint8)
        c[10:30, 5:25] = (0, 0, 200, 255)
        self.ac.sprite("c", c)

    def test_copia_espelhada(self):
        self.assertGreater(acervo.espelhado(self.db, "a", "b"), 0.99)

    def test_nao_simetrico_nem_parecido(self):
        self.assertLess(acervo.espelhado(self.db, "a", "a"), 0.7)      # o desenho e assimetrico
        self.assertLess(acervo.espelhado(self.db, "a", "c"), 0.2)

    def test_sem_quadro(self):
        self.assertEqual(acervo.espelhado(self.db, "a", "nao_existe"), 0.0)


class TestMaterial(Base):
    def mat(self, **props):
        n = f"m_{len(self.db.execute('select * from tiles').fetchall())}"
        self.ac.tile(n, "m", 0, **props)
        return acervo.material(self.db, n)

    def test_mapeamento(self):
        self.assertEqual(self.mat(Material="Wood"), "madeira")
        self.assertEqual(self.mat(Material="Wood_Solid"), "madeira")
        self.assertEqual(self.mat(Material="Fridge"), "metal")
        self.assertEqual(self.mat(Material="Electric"), "metal")
        self.assertEqual(self.mat(Material="MetalBars"), "metal")
        self.assertEqual(self.mat(Material="Metal_Solid"), "metal")
        self.assertEqual(self.mat(Material="SmallMetalPlates"), "metal")
        self.assertEqual(self.mat(Material="Fabric"), "tecido")
        self.assertEqual(self.mat(Material="Cloth"), "tecido")
        self.assertEqual(self.mat(Material="Upholstery"), "tecido")
        self.assertEqual(self.mat(Material="Glass"), "liso")
        self.assertEqual(self.mat(Material="Plastic"), "liso")

    def test_fixador_olha_o_proximo(self):
        self.assertEqual(self.mat(Material="Nails", Material2="Wood"), "madeira")
        self.assertEqual(self.mat(Material="Screws", Material2="Nails", Material3="Fabric"), "tecido")
        self.assertEqual(self.mat(Material="Nails", MaterialType="Wood_Solid"), "madeira")

    def test_so_fixador_ou_sem_material(self):
        self.assertEqual(self.mat(Material="Nails"), "liso")
        self.assertEqual(self.mat(), "liso")

    def test_primeiro_material_manda(self):
        self.assertEqual(self.mat(Material="Metal", Material2="Wood"), "metal")


class TestSugerirReceita(Base):
    def setUp(self):
        super().setUp()
        for i, f in enumerate("SENW"):
            self.ac.tile(f"Obj_Teste-01_{i}", "Obj_Teste-01", i, Facing=f, CustomName="Mesa", GroupName="G",
                         Material="Nails", Material2="Wood")
            self.ac.sprite(f"Obj_Teste-01_{i}")
        self.ac.caixa("Obj_Teste-01_0", 0, (-5000, 0, -5000), (5000, 200, 5000))
        self.ac.caixa("Obj_Teste-01_0", 1, (-4000, 0, -4000), (4000, 7000, 4000))
        self.ac.cilindro("Obj_Teste-01_0", 2, 800, 3000, t=(0, 8500, 0), r=(2700000, 0, 0))

    def test_receita_valida_com_direcoes_e_material(self):
        r = acervo.sugerir_receita(self.db, "Obj_Teste-01_0")
        receita.validar(r)
        receita.expandir(r)
        self.assertEqual(r["id"], "obj_teste_01_0")
        self.assertEqual(r["sprites"], {"S": "Obj_Teste-01_0", "E": "Obj_Teste-01_1",
                                        "N": "Obj_Teste-01_2", "W": "Obj_Teste-01_3"})
        self.assertEqual(r["tras"], "N")
        self.assertEqual(r["material"], "madeira")
        self.assertEqual(r["arte"], {"modo": "adesivo"})
        self.assertEqual(r["realista"], {"materiais": {"madeira": {"tipo": "madeira"}}})
        self.assertEqual([p["forma"] for p in r["pecas"]], ["caixa", "cilindro"])

    def test_sem_n_vira_simetrico(self):
        self.ac.tile("sol_0", "sol", 0, Facing="S", CustomName="X", Material="Metal")
        self.ac.sprite("sol_0")
        self.ac.caixa("sol_0", 0, (-1000, 0, -1000), (1000, 5000, 1000))
        r = acervo.sugerir_receita(self.db, "sol_0")
        self.assertEqual(r["tras"], "simetrico")
        self.assertEqual(r["material"], "metal")
        self.assertEqual(r["sprites"], {"S": "sol_0"})

    def test_sem_geometria_falha_com_receita_invalida(self):
        self.ac.tile("vazio_0", "vazio", 0)
        self.ac.sprite("vazio_0")
        with self.assertRaises(receita.ReceitaInvalida):      # a receita precisa de ao menos uma peca
            acervo.sugerir_receita(self.db, "vazio_0")


if __name__ == "__main__":
    unittest.main()
