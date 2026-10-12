"""Testes de folhas.py com uma pasta de trabalho sintetica (E = 2, formas simples desenhadas com PIL)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from porte3d import folhas

E = 2
ANGS = range(0, 360, 45)


def _quadro(retang, cor=(200, 120, 60), esc=1, fundo=None):
    """Imagem RGBA (128*esc x 256*esc) transparente com um retangulo (em px do jogo) preenchido."""
    im = Image.new("RGBA", (128 * esc, 256 * esc), fundo or (0, 0, 0, 0))
    x0, y0, x1, y1 = retang
    ImageDraw.Draw(im).rectangle([x0 * esc, y0 * esc, x1 * esc - 1, y1 * esc - 1], fill=cor + (255,))
    return im


def _pasta(tmp: Path, retang_modelo=(40, 100, 80, 200), retang_jogo=(40, 100, 80, 200), com_realista=True,
           cor_modelo=(200, 120, 60)) -> Path:
    p = tmp / "objeto"
    (p / "entrada").mkdir(parents=True)
    (p / "vistas").mkdir()
    _quadro(retang_jogo).save(p / "entrada" / "frente_original.png")
    _quadro(retang_jogo, cor=(60, 120, 200)).save(p / "entrada" / "tras.png")
    niveis = ["arte", "fio", "fio_sobre_arte"] + (["realista"] if com_realista else [])
    for nivel in niveis:
        for a in ANGS:
            # cada angulo desloca 1 px, para os quadros do gif serem diferentes
            r = (retang_modelo[0], retang_modelo[1], retang_modelo[2] + a // 45, retang_modelo[3])
            _quadro(r, cor=cor_modelo, esc=E).save(p / "vistas" / f"{nivel}_{a:03d}.png")
    (p / "pecas.json").write_text(json.dumps([
        {"indice": 0, "nome": "tampo", "cor_fio": [255, 0, 0]},
        {"indice": 1, "nome": "perna", "cor_fio": [0, 0, 255]}]), encoding="utf-8")
    return p


class TestFolhas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gera_todos_os_arquivos(self):
        p = _pasta(self.tmp)
        folhas.gerar(p)
        for nome in ("comparacao.png", "giro_arte.png", "giro_realista.png", "fio.png", "sobreposicao.png",
                     "zoom.png", "giro_arte.gif", "giro_realista.gif", "medidas.json"):
            self.assertTrue((p / "folhas" / nome).is_file(), nome)
        self.assertTrue((p / "medidas.json").is_file())

    def test_tamanhos_sensatos(self):
        p = _pasta(self.tmp)
        folhas.gerar(p)
        for nome in ("comparacao.png", "giro_arte.png", "fio.png", "sobreposicao.png", "zoom.png"):
            with Image.open(p / "folhas" / nome) as im:
                w, h = im.size
            self.assertTrue(100 < w < 6000 and 50 < h < 6000, (nome, w, h))
        # recortado: bem menor que o quadro inteiro 256x512 por tile
        with Image.open(p / "folhas" / "giro_arte.png") as im:
            w, h = im.size
        self.assertLess(w, 4 * 256)
        self.assertLess(h, 2 * 512 + 100)

    def test_gif_oito_quadros_250ms(self):
        p = _pasta(self.tmp)
        folhas.gerar(p)
        with Image.open(p / "folhas" / "giro_arte.gif") as g:
            self.assertEqual(g.n_frames, 8)
            self.assertEqual(g.info["duration"], 250)

    def test_silhuetas_identicas_dao_iou_1(self):
        # a vista a 0 graus tem o mesmo retangulo do jogo; cor igual -> diferenca 0
        p = _pasta(self.tmp)
        m = folhas.gerar(p)
        self.assertEqual(m["contorno_0"], 1.0)
        self.assertEqual(m["cor_0"], 0.0)
        self.assertEqual(json.loads((p / "folhas" / "medidas.json").read_text()), m)

    def test_deslocado_pela_metade(self):
        # jogo 40..80, modelo 60..100: intersecao 20, uniao 60 -> 1/3
        p = _pasta(self.tmp, retang_modelo=(60, 100, 100, 200))
        m = folhas.gerar(p)
        self.assertEqual(m["contorno_0"], 0.333)

    def test_diferenca_de_cor(self):
        # mesmo contorno, canal R do modelo 10 acima do jogo: media |dif| = (10+0+0)/3 = 3.3
        p = _pasta(self.tmp, cor_modelo=(210, 120, 60))
        m = folhas.gerar(p)
        self.assertEqual(m["contorno_0"], 1.0)
        self.assertEqual(m["cor_0"], 3.3)

    def test_sem_realista_nao_quebra(self):
        p = _pasta(self.tmp, com_realista=False)
        m = folhas.gerar(p)
        self.assertEqual(m["contorno_0"], 1.0)
        self.assertTrue((p / "folhas" / "comparacao.png").is_file())
        self.assertTrue((p / "folhas" / "giro_realista.png").is_file())   # folha so com o aviso
        self.assertFalse((p / "folhas" / "giro_realista.gif").exists())
        self.assertTrue((p / "folhas" / "zoom.png").is_file())

    def test_sem_nada_alem_do_jogo(self):
        p = _pasta(self.tmp)
        shutil.rmtree(p / "vistas")
        (p / "vistas").mkdir()
        (p / "pecas.json").unlink()
        m = folhas.gerar(p)
        self.assertIsNone(m["contorno_0"])
        self.assertTrue((p / "folhas" / "fio.png").is_file())


if __name__ == "__main__":
    unittest.main()
