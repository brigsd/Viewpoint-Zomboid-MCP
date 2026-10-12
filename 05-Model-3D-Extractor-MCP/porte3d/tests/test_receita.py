"""Testes da receita: validação e espelhamentos.
Rodar: python -m unittest discover -s 05-Model-3D-Extractor-MCP/porte3d/tests -t 05-Model-3D-Extractor-MCP -v
"""
import copy
import unittest
from pathlib import Path

from porte3d import receita

MESA = Path(__file__).resolve().parents[1] / "receitas" / "mesa_fancy_dark.json"


def minima(**extra):
    r = {"versao": 1, "id": "teste", "sprites": {"S": "a_0"}, "arte": {"modo": "adesivo"},
         "pecas": [{"nome": "bloco", "forma": "caixa", "min": [-0.5, -0.4, 0], "max": [0.4, 0.3, 1.5]}]}
    r.update(extra)
    return r


class TestValidar(unittest.TestCase):
    def test_mesa_valida_e_expande(self):
        r = receita.expandir(receita.carregar(MESA))
        nomes = [p["nome"] for p in r["pecas"]]
        self.assertEqual(len(nomes), 17)
        self.assertIn("pe.xy", nomes)
        self.assertEqual(len(set(nomes)), 17)

    def test_minima(self):
        receita.validar(minima())

    def test_min_maior_que_max(self):
        r = minima()
        r["pecas"][0]["max"][2] = -1
        with self.assertRaisesRegex(receita.ReceitaInvalida, "min precisa"):
            receita.validar(r)

    def test_nome_repetido(self):
        r = minima()
        r["pecas"].append(copy.deepcopy(r["pecas"][0]))
        with self.assertRaisesRegex(receita.ReceitaInvalida, "repetida"):
            receita.validar(r)

    def test_tras_n_sem_sprite(self):
        with self.assertRaisesRegex(receita.ReceitaInvalida, "sprite N"):
            receita.validar(minima(tras="N"))

    def test_kit_com_recorte_inexistente(self):
        r = minima(arte={"modo": "kit", "recortes": {"a": {"peca": "bloco", "face": "-y", "recorte": [0, 0, 1, 1]}},
                         "faces": {"bloco": {"lados": "b"}}})
        with self.assertRaisesRegex(receita.ReceitaInvalida, "recorte b"):
            receita.validar(r)

    def test_esquema_recusa_campo_estranho(self):
        with self.assertRaises(receita.ReceitaInvalida):
            receita.validar(minima(cor_errada=1))

    def test_prisma_precisa_de_eixo(self):
        r = minima()
        r["pecas"] = [{"nome": "p", "forma": "prisma", "perfil": [[0, 0], [1, 0], [0, 1]], "de": 0, "ate": 1}]
        with self.assertRaises(receita.ReceitaInvalida):
            receita.validar(r)


class TestEspelhar(unittest.TestCase):
    def test_caixa_e_afinar(self):
        r = minima()
        r["pecas"] = [{"nome": "pe", "forma": "caixa", "min": [0.3, -0.4, 0], "max": [0.4, -0.3, 0.7],
                       "afinar": {"quanto": 0.01, "lados": ["-x", "+y"]}, "espelhar": ["x", "y"]}]
        p = {q["nome"]: q for q in receita.expandir(r)["pecas"]}
        self.assertEqual(set(p), {"pe", "pe.x", "pe.y", "pe.xy"})
        self.assertEqual(p["pe.x"]["min"][0], -0.4)
        self.assertEqual(p["pe.x"]["max"][0], -0.3)
        self.assertEqual(sorted(p["pe.x"]["afinar"]["lados"]), ["+x", "+y"])
        self.assertEqual(sorted(p["pe.xy"]["afinar"]["lados"]), ["+x", "-y"])
        self.assertEqual(p["pe.xy"]["min"][:2], [-0.4, 0.3])
        self.assertEqual(p["pe.xy"]["origem"], "pe")

    def test_prisma(self):
        r = minima()
        r["pecas"] = [{"nome": "c", "forma": "prisma", "perfil": [[0.3, 0.5], [0.2, 0.5], [0.3, 0.4]],
                       "eixo": "y", "de": -0.4, "ate": -0.38, "espelhar": ["x", "y"]}]
        p = {q["nome"]: q for q in receita.expandir(r)["pecas"]}
        self.assertEqual(sorted(a for a, _ in p["c.x"]["perfil"]), [-0.3, -0.3, -0.2])
        self.assertEqual((p["c.y"]["de"], p["c.y"]["ate"]), (0.38, 0.4))

    def test_cilindro_e_rot(self):
        r = minima()
        r["pecas"] = [{"nome": "c", "forma": "cilindro", "centro": [0.2, 0.1, 0], "raio": 0.05, "altura": 0.3,
                       "rot": [10, 20, 30], "espelhar": ["x"]}]
        p = {q["nome"]: q for q in receita.expandir(r)["pecas"]}
        self.assertEqual(p["c.x"]["centro"], [-0.2, 0.1, 0])
        self.assertEqual(p["c.x"]["rot"], [10, -20, -30])
        self.assertEqual(p["c"]["eixo"], "z")

    def test_veio_padrao_e_o_maior_lado(self):
        p = receita.expandir(minima())["pecas"][0]
        self.assertEqual(p["veio"], "z")
        self.assertEqual(p["material"], "madeira")


if __name__ == "__main__":
    unittest.main()
