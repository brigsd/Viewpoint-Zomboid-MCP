"""Testes de porte3d.galeria com uma fila falsa em memória e uma pasta de trabalho temporária."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from porte3d import galeria


class FilaFalsa:
    def __init__(self, registros):
        self.reg = {r["id"]: dict(r) for r in registros}
        self.chamadas = []

    def objetos(self, estado=None):
        return [dict(r) for r in self.reg.values() if estado is None or r["estado"] == estado]

    def obter(self, id):
        r = self.reg.get(id)
        return dict(r) if r else None

    def decidir(self, id, decisao, comentario=None):
        self.chamadas.append((id, decisao, comentario))
        self.reg[id]["estado"] = decisao
        self.reg[id]["comentario_usuario"] = comentario
        return dict(self.reg[id])


def registro(id, estado="aguardando_aprovacao", **kw):
    r = {"id": id, "familia": id, "sprites": {"S": f"{id}_0"}, "categoria": "Furniture", "custom_name": "Mesa",
         "group_name": "Fancy", "estado": estado, "rodada": 2, "notas": [{"rodada": 2, "arte": 8.5, "realista": 7.5}],
         "historico": [], "motivo": None, "comentario_usuario": None}
    r.update(kw)
    return r


def veredito(id, rodada, na, nr, defeitos=()):
    return {"versao": 1, "objeto": id, "rodada": rodada, "nota_arte": na, "nota_realista": nr, "pecas": [],
            "defeitos": list(defeitos), "observacao": ""}


def defeito(parte="pe_tras", tipo="proporcao", onde="metade de baixo", grav="media", nivel="ambos"):
    return {"parte": parte, "tipo": tipo, "nivel": nivel, "vista": "giro", "onde": onde, "evidencia": "x", "gravidade": grav}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.raiz = self.tmp / "porte3d"
        self.ver = self.tmp / "vereditos"
        self.fic = self.tmp / "fichas"
        self.fic.mkdir()

    def pasta(self, id, com_imagens=True):
        p = self.raiz / id
        (p / "folhas").mkdir(parents=True)
        (p / "entrada").mkdir()
        if com_imagens:
            for rel in ("entrada/frente_original.png", "folhas/giro_arte.gif", "folhas/giro_realista.gif",
                        "folhas/comparacao.png", "folhas/fio.png", "folhas/sobreposicao.png", "folhas/zoom.png"):
                (p / rel).write_bytes(b"x")

    def escrever_veredito(self, id, v):
        d = self.ver / id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"rodada_{v['rodada']}.json").write_text(json.dumps(v), encoding="utf-8")

    def gerar(self, fila, estados=("aguardando_aprovacao",), saida=None):
        return galeria.gerar(saida or self.raiz / "galeria", estados, fila=fila, raiz=self.raiz,
                             vereditos=self.ver, fichas=self.fic)


class TestGerar(Base):
    def test_um_cartao_por_objeto_aguardando(self):
        fila = FilaFalsa([registro("mesa_a"), registro("mesa_b"), registro("mesa_c", estado="aprovado")])
        for i in ("mesa_a", "mesa_b", "mesa_c"):
            self.pasta(i)
        html = self.gerar(fila).read_text(encoding="utf-8")
        self.assertEqual(html.count('<article class="cartao"'), 2)
        self.assertIn('data-id="mesa_a"', html)
        self.assertIn('data-id="mesa_b"', html)
        self.assertNotIn('data-id="mesa_c"', html)
        self.assertEqual(html.count('data-decisao="aprovado"'), 2)
        self.assertEqual(html.count('data-decisao="rejeitado"'), 2)
        self.assertIn('lang="pt-BR"', html)

    def test_imagens_e_links_relativos(self):
        fila = FilaFalsa([registro("mesa_a")])
        self.pasta("mesa_a")
        html = self.gerar(fila).read_text(encoding="utf-8")
        self.assertIn('src="../mesa_a/entrada/frente_original.png"', html)
        self.assertIn('src="../mesa_a/folhas/giro_arte.gif"', html)
        self.assertIn('src="../mesa_a/folhas/giro_realista.gif"', html)
        for n in ("comparacao", "fio", "sobreposicao", "zoom"):
            self.assertIn(f'href="../mesa_a/folhas/{n}.png"', html)

    def test_imagem_que_falta_vira_aviso(self):
        fila = FilaFalsa([registro("mesa_a")])
        self.pasta("mesa_a", com_imagens=False)
        (self.raiz / "mesa_a" / "entrada" / "frente_original.png").write_bytes(b"x")
        html = self.gerar(fila).read_text(encoding="utf-8")
        self.assertEqual(html.count('class="semimg"'), 2)
        self.assertEqual(html.count("<img"), 1)
        self.assertNotIn("folhas/zoom.png", html)           # sem folhas, sem links

    def test_sem_nenhuma_imagem_some_o_bloco(self):
        fila = FilaFalsa([registro("lamp", estado="nao_portar", notas=[], motivo="só luz")])
        self.pasta("lamp", com_imagens=False)
        html = self.gerar(fila, estados=galeria.ESTADOS_TODOS).read_text(encoding="utf-8")
        self.assertNotIn('<div class="imagens">', html)
        self.assertNotIn('<div class="notas">', html)
        self.assertIn("só luz", html)

    def test_notas_defeitos_e_ficha(self):
        fila = FilaFalsa([registro("mesa_a")])
        self.pasta("mesa_a")
        self.escrever_veredito("mesa_a", veredito("mesa_a", 1, 3, 3, [defeito(onde="ANTIGO")]))
        self.escrever_veredito("mesa_a", veredito("mesa_a", 2, 9, 7.5, [
            defeito("tampo", "emenda", "borda da frente", "leve"),
            defeito("pe_tras", "proporcao", "metade de baixo", "grave")]))
        (self.fic / "mesa_a.json").write_text(json.dumps({"o_que_e": "mesa quadrada de madeira escura"}), encoding="utf-8")
        html = self.gerar(fila).read_text(encoding="utf-8")
        self.assertIn("<span>9</span><small>arte</small>", html)
        self.assertIn("<span>7.5</span><small>realista</small>", html)
        self.assertIn("metade de baixo", html)
        self.assertIn("borda da frente", html)
        self.assertNotIn("ANTIGO", html)                         # só a última rodada
        self.assertLess(html.index("metade de baixo"), html.index("borda da frente"))   # grave antes de leve
        self.assertIn("mesa quadrada de madeira escura", html)
        self.assertIn("Rodada 2", html)

    def test_sem_veredito_usa_notas_da_fila(self):
        fila = FilaFalsa([registro("mesa_a", notas=[{"rodada": 1, "arte": 4, "realista": 5}, {"rodada": 2, "arte": 8, "realista": 8.5}])])
        self.pasta("mesa_a")
        html = self.gerar(fila).read_text(encoding="utf-8")
        self.assertIn("<span>8.5</span><small>realista</small>", html)
        self.assertIn("Sem veredito", html)

    def test_escapa_texto(self):
        ruim = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
        fila = FilaFalsa([registro("mesa_a", custom_name=ruim, group_name=ruim)])
        self.pasta("mesa_a")
        self.escrever_veredito("mesa_a", veredito("mesa_a", 2, 8, 8, [defeito(parte=ruim, onde=ruim)]))
        (self.fic / "mesa_a.json").write_text(json.dumps({"o_que_e": ruim}), encoding="utf-8")
        html = self.gerar(fila).read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_escapa_comentario_e_motivo_nas_outras_abas(self):
        ruim = "<b onmouseover=x>oi</b>"
        fila = FilaFalsa([registro("mesa_a", estado="rejeitado", comentario_usuario=ruim),
                          registro("lamp", estado="nao_portar", motivo=ruim)])
        for i in ("mesa_a", "lamp"):
            self.pasta(i)
        html = self.gerar(fila, estados=galeria.ESTADOS_TODOS).read_text(encoding="utf-8")
        self.assertNotIn("<b onmouseover", html)
        self.assertEqual(html.count("&lt;b onmouseover=x&gt;"), 2)
        self.assertIn('data-aba="rejeitados"', html)
        self.assertIn('data-aba="reprovados"', html)
        # cartões fora da aba "aguardando" não têm botões de decisão
        self.assertNotIn("data-decisao", html.split("<main>")[1].split("</main>")[0])

    def test_sem_objetos_nao_quebra(self):
        html = self.gerar(FilaFalsa([])).read_text(encoding="utf-8")
        self.assertEqual(html.count('<article class="cartao"'), 0)

    def test_saida_em_outra_pasta_ajusta_caminho_relativo(self):
        fila = FilaFalsa([registro("mesa_a")])
        self.pasta("mesa_a")
        html = self.gerar(fila, saida=self.raiz / "a" / "b").read_text(encoding="utf-8")
        self.assertIn('src="../../mesa_a/folhas/giro_arte.gif"', html)


class TestServidor(Base):
    def setUp(self):
        super().setUp()
        self.fila = FilaFalsa([registro("mesa_a"), registro("mesa_b"), registro("lamp", estado="nao_portar")])
        self.pasta("mesa_a")
        self.gerar(self.fila)
        self.srv = galeria.criar_servidor(0, fila=self.fila, raiz=self.raiz)
        self.porta = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        self.addCleanup(self._parar)

    def _parar(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(5)

    def req(self, metodo, caminho, corpo=None, headers=None, bruto=False):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=5)
        h = {"Content-Type": "application/json"} if metodo == "POST" else {}
        h.update(headers or {})
        if corpo is not None and not bruto:
            corpo = json.dumps(corpo)
        c.request(metodo, caminho, body=corpo, headers=h)
        r = c.getresponse()
        dados = r.read()
        c.close()
        return r.status, dados

    def post(self, corpo, **kw):
        st, d = self.req("POST", "/decidir", corpo, **kw)
        return st, json.loads(d)

    def test_so_127_0_0_1(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_serve_pagina_e_imagem(self):
        st, d = self.req("GET", "/galeria/index.html")
        self.assertEqual(st, 200)
        self.assertIn(b'data-id="mesa_a"', d)
        st, d = self.req("GET", "/mesa_a/folhas/giro_arte.gif")
        self.assertEqual((st, d), (200, b"x"))
        self.assertEqual(self.req("GET", "/../fila.py")[0], 404)

    def test_estado(self):
        st, d = self.req("GET", "/estado")
        j = json.loads(d)
        self.assertEqual(st, 200)
        self.assertEqual(j["aguardando"], 2)
        self.assertEqual(j["estados"], {"aguardando_aprovacao": 2, "nao_portar": 1})
        self.assertEqual(j["abas"]["reprovados"], 1)

    def test_aprovar_chama_decidir(self):
        st, j = self.post({"id": "mesa_a", "decisao": "aprovado"})
        self.assertEqual(st, 200)
        self.assertEqual(self.fila.chamadas, [("mesa_a", "aprovado", None)])
        self.assertEqual(j["objeto"]["estado"], "aprovado")
        self.assertEqual(j["aguardando"], 1)

    def test_refazer_com_comentario(self):
        st, j = self.post({"id": "mesa_b", "decisao": "rejeitado", "comentario": "  pé torto  "})
        self.assertEqual(st, 200)
        self.assertEqual(self.fila.chamadas, [("mesa_b", "rejeitado", "pé torto")])
        self.assertEqual(j["objeto"]["comentario_usuario"], "pé torto")

    def test_recusa_entrada_ruim(self):
        ruins = [
            {"id": "mesa_a", "decisao": "publicado"},
            {"id": "mesa_a", "decisao": "APROVADO"},
            {"id": "../mesa_a", "decisao": "aprovado"},
            {"id": "Mesa A", "decisao": "aprovado"},
            {"id": 7, "decisao": "aprovado"},
            {"decisao": "aprovado"},
            {"id": "mesa_a"},
            {"id": "mesa_a", "decisao": "aprovado", "comentario": 5},
            {"id": "mesa_a", "decisao": "aprovado", "comentario": "x" * 1001},
            {"id": "mesa_a", "decisao": "aprovado", "estado": "publicado"},
            ["mesa_a"],
        ]
        for r in ruins:
            st, j = self.post(r)
            self.assertEqual(st, 400, r)
            self.assertIn("erro", j)
        st, j = self.post("{não é json", bruto=True)
        self.assertEqual(st, 400)
        self.assertEqual(self.fila.chamadas, [])

    def test_objeto_inexistente_e_estado_errado(self):
        self.assertEqual(self.post({"id": "nao_existe", "decisao": "aprovado"})[0], 404)
        self.assertEqual(self.post({"id": "lamp", "decisao": "aprovado"})[0], 409)
        self.assertEqual(self.fila.chamadas, [])
        self.post({"id": "mesa_a", "decisao": "aprovado"})
        self.assertEqual(self.post({"id": "mesa_a", "decisao": "rejeitado"})[0], 409)   # já decidido
        self.assertEqual(len(self.fila.chamadas), 1)

    def test_recusa_origem_de_fora_e_tipo_errado(self):
        ok = {"id": "mesa_a", "decisao": "aprovado"}
        self.assertEqual(self.post(ok, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.post(ok, headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.post(ok, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.fila.chamadas, [])
        self.assertEqual(self.post(ok, headers={"Origin": f"http://127.0.0.1:{self.porta}"})[0], 200)

    def test_corpo_grande_demais(self):
        self.assertEqual(self.post({"id": "mesa_a", "decisao": "aprovado", "comentario": "x" * 50000})[0], 413)
        self.assertEqual(self.fila.chamadas, [])

    def test_nenhum_outro_endpoint_de_escrita(self):
        self.assertEqual(self.req("POST", "/outra", {"a": 1})[0], 404)
        self.assertEqual(self.req("PUT", "/decidir", {"a": 1})[0], 405)
        self.assertEqual(self.req("DELETE", "/mesa_a/folhas/zoom.png")[0], 405)
        self.assertTrue((self.raiz / "mesa_a" / "folhas" / "zoom.png").exists())


if __name__ == "__main__":
    unittest.main()
