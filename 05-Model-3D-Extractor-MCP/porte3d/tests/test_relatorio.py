"""Testes do relatório final de reprovados e não portados (fila em pasta temporária)."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from porte3d import fila, relatorio
from porte3d.tests.test_fila import defeito, receita, registro, veredito


class TestRelatorio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._raiz = fila.RAIZ
        fila.RAIZ = self.tmp / "raiz"
        self.addCleanup(setattr, fila, "RAIZ", self._raiz)

    def semear(self, *regs):
        fila._gravar({"versao": 1, "objetos": {r["id"]: r for r in regs}})

    def test_fila_vazia(self):
        t = relatorio.gerar()
        self.assertIn("0 objetos  |  fila vazia", t)
        self.assertIn("Reprovados (3 rodadas sem nota 8): 0", t)
        self.assertEqual(t.count("(nenhum)"), 2)

    def test_linhas_por_estado(self):
        self.semear(
            registro("mesa_dark", estado="reprovado", rodada=3, motivo="pe: ausencia (ambos, giro) — pé de trás",
                     notas=[{"rodada": 1, "arte": 5, "realista": 4}, {"rodada": 3, "arte": 7.5, "realista": 6}]),
            registro("fridge_mini", estado="reprovado", rodada=3, motivo="porta:   proporcao\n(arte, comparacao) — porta",
                     notas=[{"rodada": 3, "arte": 8, "realista": 7}]),
            registro("luminaria", estado="nao_portar", motivo="luminária de parede, só um plano"),
            registro("sem_motivo", estado="reprovado"),
            registro("a_fila"), registro("pronto", estado="aprovado"))
        t = relatorio.gerar()
        linhas = t.splitlines()
        self.assertEqual(linhas[1], "6 objetos  |  fila: 1, nao_portar: 1, reprovado: 3, aprovado: 1")
        mesa = "  mesa_dark · 7.5/6 · pe: ausencia (ambos, giro) — pé de trás"      # só a última nota
        self.assertIn(mesa, linhas)
        self.assertIn("  fridge_mini · 8/7 · porta: proporcao (arte, comparacao) — porta", linhas)   # espaços e quebra viram um
        self.assertIn("  luminaria · - · luminária de parede, só um plano", linhas)
        self.assertIn("  sem_motivo · - · sem motivo registrado", linhas)
        i_rep = linhas.index("Reprovados (3 rodadas sem nota 8): 3")
        i_nao = linhas.index("Não portados (decisão do inspetor): 1")
        self.assertLess(i_rep, linhas.index(mesa))
        self.assertLess(linhas.index(mesa), i_nao)
        self.assertNotIn("a_fila", t)
        self.assertNotIn("pronto", t)
        self.assertNotIn("\n\n\n", t)

    def test_motivo_longo_e_cortado(self):
        self.semear(registro("x", estado="reprovado", motivo="a" * 400))
        linha = [x for x in relatorio.gerar().splitlines() if x.startswith("  x ·")][0]
        self.assertLessEqual(len(linha), len("  x · - · ") + relatorio.MAX_MOTIVO)
        self.assertTrue(linha.endswith("…"))

    def test_markdown_e_arquivo(self):
        self.semear(registro("mesa", estado="reprovado", motivo="a | b", notas=[{"rodada": 3, "arte": 6, "realista": 5}]),
                    registro("lum", estado="nao_portar", motivo="plano"))
        md = relatorio.gerar("md")
        self.assertTrue(md.startswith("# Porte 3D"))
        self.assertIn("| mesa | 6/5 | a / b |", md)
        self.assertIn("| lum | - | plano |", md)
        destino = self.tmp / "sub" / "lista.md"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(relatorio.main(["--md", str(destino)]), 0)
        self.assertEqual(destino.read_bytes().decode("utf-8"), md)
        self.assertNotIn(b"\r", destino.read_bytes())

    def test_depois_do_laco_o_relatorio_bate_com_a_fila(self):
        """Ponta a ponta com o veredito real: o motivo do relatório é o do defeito mais grave."""
        self.semear(registro(estado="em_modelagem"))
        p = self.tmp / "e.json"
        for r in (1, 2, 3):
            p.write_text(json.dumps(receita()), encoding="utf-8")
            fila.registrar_receita("geladeira_branca", p)
            ds = [defeito("grave", parte="porta", tipo="buraco", onde="dobradiça")]
            p.write_text(json.dumps(veredito(rodada=r, arte=6, realista=6 + r / 10, defeitos=ds)), encoding="utf-8")
            fila.registrar_veredito("geladeira_branca", p)
            if r < 3:
                fila.mover("geladeira_branca", "em_modelagem")
        self.assertIn("  geladeira_branca · 6/6.3 · porta: buraco (ambos, giro) — dobradiça",
                      relatorio.gerar().splitlines())


if __name__ == "__main__":
    unittest.main()
