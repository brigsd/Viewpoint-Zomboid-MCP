"""Testes da fila: transições, o laço de 3 rodadas, aprovação, esquemas e popular (acervo sintético, pasta temporária).
Rodar: python -m unittest discover -s 05-Model-3D-Extractor-MCP/porte3d/tests -t 05-Model-3D-Extractor-MCP -v
"""
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from porte3d import fila
from porte3d.tests import AcervoSintetico


def registro(id="geladeira_branca", **extra):
    o = {"id": id, "familia": "geladeira", "forma_de": None, "sprites": {"S": f"{id}_0"}, "categoria": "eletrodomesticos",
         "tileset": "t", "custom_name": "Fridge", "group_name": "White", "material": "metal", "prioridade": 400,
         "estado": "fila", "rodada": 0, "notas": [], "historico": [], "motivo": None, "comentario_usuario": None}
    o.update(extra)
    return o


def ficha(id="geladeira_branca", decisao="portar", **extra):
    f = {"versao": 1, "objeto": id, "sprite": f"{id}_0", "decisao": decisao, "motivo": "caixa simples com duas portas",
         "o_que_e": "geladeira de duas portas"}
    if decisao == "portar":
        f.update({"pecas": [{"nome": "corpo", "forma": "caixa", "origem": "jogo", "descricao": "o corpo"}],
                  "simetria": "nenhuma", "tras": "simetrico", "arte": "adesivo", "materiais": {"corpo": "metal"}})
    f.update(extra)
    return f


def receita(id="geladeira_branca", **extra):
    r = {"versao": 1, "id": id, "sprites": {"S": f"{id}_0"}, "arte": {"modo": "adesivo"},
         "pecas": [{"nome": "corpo", "forma": "caixa", "min": [-0.4, -0.4, 0], "max": [0.4, 0.4, 1.6]}]}
    r.update(extra)
    return r


def veredito(id="geladeira_branca", rodada=1, arte=9, realista=9, defeitos=None, **extra):
    v = {"versao": 1, "objeto": id, "rodada": rodada, "nota_arte": arte, "nota_realista": realista,
         "pecas": [{"nome": "corpo", "situacao": "ok"}], "defeitos": defeitos or [], "observacao": "ok"}
    v.update(extra)
    return v


def defeito(gravidade="media", parte="corpo", tipo="proporcao", nivel="ambos", vista="giro", onde="a porta de cima"):
    return {"parte": parte, "tipo": tipo, "nivel": nivel, "vista": vista, "onde": onde, "evidencia": "folha giro 090",
            "gravidade": gravidade}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._raiz = fila.RAIZ
        fila.RAIZ = self.tmp / "raiz"
        self.addCleanup(setattr, fila, "RAIZ", self._raiz)
        self.arqs = self.tmp / "entregas"
        self.arqs.mkdir()

    def arquivo(self, conteudo: dict, nome="entrega.json") -> Path:
        p = self.arqs / nome
        p.write_text(json.dumps(conteudo), encoding="utf-8")
        return p

    def semear(self, *regs):
        fila._gravar({"versao": 1, "objetos": {r["id"]: r for r in regs}})

    def estado(self, id="geladeira_branca"):
        return fila.obter(id)["estado"]


class TestTransicoes(Base):
    def setUp(self):
        super().setUp()
        self.semear(registro())

    def test_caminho_normal_e_historico(self):
        fila.mover("geladeira_branca", "em_inspecao", "começou")
        fila.mover("geladeira_branca", "em_modelagem")
        o = fila.obter("geladeira_branca")
        self.assertEqual(o["estado"], "em_modelagem")
        self.assertEqual([(h["de"], h["para"]) for h in o["historico"]],
                         [("fila", "em_inspecao"), ("em_inspecao", "em_modelagem")])
        self.assertEqual(o["historico"][0]["nota"], "começou")
        self.assertRegex(o["historico"][0]["quando"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")

    def test_transicao_invalida(self):
        with self.assertRaisesRegex(fila.TransicaoInvalida, "fila → aprovado"):
            fila.mover("geladeira_branca", "aprovado")
        self.assertEqual(self.estado(), "fila")
        self.assertEqual(fila.obter("geladeira_branca")["historico"], [])

    def test_estado_desconhecido_e_objeto_inexistente(self):
        with self.assertRaises(fila.FilaErro):
            fila.mover("geladeira_branca", "voando")
        with self.assertRaises(fila.ObjetoInexistente):
            fila.mover("nao_existe", "em_inspecao")
        with self.assertRaises(fila.ObjetoInexistente):
            fila.obter("nao_existe")

    def test_toda_a_tabela(self):
        """Cada par (de, para) da tabela passa e todo o resto é recusado."""
        for de in fila.ESTADOS:
            for para in fila.ESTADOS:
                self.semear(registro(estado=de))
                if para in fila.TRANSICOES[de]:
                    fila.mover("geladeira_branca", para)
                    self.assertEqual(self.estado(), para)
                else:
                    with self.assertRaises(fila.TransicaoInvalida, msg=f"{de} → {para}"):
                        fila.mover("geladeira_branca", para)

    def test_voltar_para_fila_so_com_reiniciar(self):
        self.semear(registro(estado="reprovado", rodada=3, motivo="x", notas=[{"rodada": 3, "arte": 5, "realista": 5}]))
        with self.assertRaises(fila.TransicaoInvalida):
            fila.mover("geladeira_branca", "fila")
        o = fila.reiniciar("geladeira_branca")
        self.assertEqual((o["estado"], o["rodada"], o["motivo"]), ("fila", 0, None))
        self.assertEqual(len(o["notas"]), 1)                 # o histórico fica
        self.assertEqual(o["historico"][-1]["nota"], "reiniciado")
        with self.assertRaisesRegex(fila.TransicaoInvalida, "já está na fila"):
            fila.reiniciar("geladeira_branca")

    def test_reiniciar_de_qualquer_estado(self):
        for e in fila.ESTADOS:
            if e == "fila":
                continue
            self.semear(registro(estado=e))
            self.assertEqual(fila.reiniciar("geladeira_branca")["estado"], "fila")

    def test_motivo_so_em_nao_portar_e_reprovado(self):
        fila.mover("geladeira_branca", "em_inspecao")
        o = fila.mover("geladeira_branca", "nao_portar", "é uma luminária de parede")
        self.assertEqual(o["motivo"], "é uma luminária de parede")
        self.semear(registro(estado="em_inspecao"))
        self.assertIsNone(fila.mover("geladeira_branca", "em_modelagem", "ok")["motivo"])

    def test_resumo_proximos_objetos(self):
        self.semear(registro("a", prioridade=401), registro("b", prioridade=405), registro("c", prioridade=405),
                    registro("d", estado="aprovado"))
        self.assertEqual([o["id"] for o in fila.proximos("fila", 2)], ["b", "c"])
        self.assertEqual([o["id"] for o in fila.proximos()], ["b", "c", "a"])
        r = fila.resumo()
        self.assertEqual((r["fila"], r["aprovado"], r["publicado"]), (3, 1, 0))
        self.assertEqual(set(r), set(fila.ESTADOS))
        self.assertEqual([o["id"] for o in fila.objetos("aprovado")], ["d"])
        self.assertEqual([o["id"] for o in fila.objetos()], ["a", "b", "c", "d"])


class TestArmazenamento(Base):
    def test_arquivo_ordenado_legivel_e_sem_sobras(self):
        self.semear(registro("b"), registro("a"))
        fila.mover("a", "em_inspecao")
        p = fila.caminho_fila()
        texto = p.read_bytes().decode("utf-8")
        self.assertNotIn("\r", texto)
        self.assertTrue(texto.endswith("}\n"))
        self.assertIn('\n "objetos": {\n  "a": {', texto)        # indentação 1
        dados = json.loads(texto)
        self.assertEqual(texto, json.dumps(dados, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        self.assertEqual(sorted(x.name for x in p.parent.iterdir()), ["fila.json"])   # sem .tmp nem .lock

    def test_carregar_sem_arquivo(self):
        self.assertEqual(fila.carregar(), {"versao": 1, "objetos": {}})
        self.assertFalse(fila.caminho_fila().exists())             # ler não cria nada

    def test_trava_serializa_escritas_concorrentes(self):
        self.semear(registro("a", prioridade=0))

        def soma():
            for _ in range(10):
                with fila._transacao() as d:
                    d["objetos"]["a"]["prioridade"] += 1

        ts = [threading.Thread(target=soma) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(fila.obter("a")["prioridade"], 40)

    def test_trava_esquecida_velha_e_ignorada(self):
        self.semear(registro())
        lock = fila.caminho_fila().with_name("fila.lock")
        lock.write_text("999")
        os.utime(lock, (1, 1))
        fila.mover("geladeira_branca", "em_inspecao")
        self.assertFalse(lock.exists())

    def test_trava_viva_barra(self):
        self.semear(registro())
        lock = fila.caminho_fila().with_name("fila.lock")
        lock.write_text("1")
        with self.assertRaisesRegex(fila.FilaErro, "travada"):
            with fila._trava(espera=0.2):
                pass
        lock.unlink()

    def test_erro_na_transacao_nao_grava(self):
        self.semear(registro())
        with self.assertRaises(RuntimeError):
            with fila._transacao() as d:
                d["objetos"]["geladeira_branca"]["estado"] = "publicado"
                raise RuntimeError
        self.assertEqual(self.estado(), "fila")
        self.assertFalse(fila.caminho_fila().with_name("fila.lock").exists())


class TestFicha(Base):
    def setUp(self):
        super().setUp()
        self.semear(registro(estado="em_inspecao"))

    def test_portar_vai_para_modelagem_e_guarda_a_ficha(self):
        o = fila.registrar_ficha("geladeira_branca", self.arquivo(ficha()))
        self.assertEqual(o["estado"], "em_modelagem")
        guardada = json.loads(fila.caminho_ficha("geladeira_branca").read_text(encoding="utf-8"))
        self.assertEqual(guardada["decisao"], "portar")

    def test_nao_portar_guarda_o_motivo(self):
        f = ficha(decisao="nao_portar", motivo="luminária de parede, não tem volume")
        o = fila.registrar_ficha("geladeira_branca", self.arquivo(f))
        self.assertEqual(o["estado"], "nao_portar")
        self.assertEqual(o["motivo"], "luminária de parede, não tem volume")

    def test_recusas(self):
        casos = {
            "objeto de outro": ficha(id="outra_coisa"),
            "portar sem peças": {k: v for k, v in ficha().items() if k != "pecas"},
            "decisão fora da lista": ficha(decisao="talvez"),
            "campo a mais": ficha(extra=1),
            "id fora do padrão": ficha(id="Geladeira Branca"),
        }
        for nome, f in casos.items():
            with self.subTest(nome), self.assertRaises(fila.ArquivoInvalido):
                fila.registrar_ficha("geladeira_branca", self.arquivo(f))
            self.assertEqual(self.estado(), "em_inspecao")
        self.assertFalse(fila.caminho_ficha("geladeira_branca").exists())

    def test_arquivo_ausente_ou_json_quebrado(self):
        with self.assertRaisesRegex(fila.ArquivoInvalido, "não encontrado"):
            fila.registrar_ficha("geladeira_branca", self.arqs / "nada.json")
        p = self.arqs / "ruim.json"
        p.write_text("{não é json", encoding="utf-8")
        with self.assertRaisesRegex(fila.ArquivoInvalido, "JSON inválido"):
            fila.registrar_ficha("geladeira_branca", p)

    def test_estado_errado(self):
        self.semear(registro(estado="fila"))
        with self.assertRaises(fila.TransicaoInvalida):
            fila.registrar_ficha("geladeira_branca", self.arquivo(ficha()))
        self.assertFalse(fila.caminho_ficha("geladeira_branca").exists())


class TestReceitaEVeredito(Base):
    def setUp(self):
        super().setUp()
        self.semear(registro(estado="em_modelagem"))

    def receita(self, **extra):
        return fila.registrar_receita("geladeira_branca", self.arquivo(receita(**extra)))

    def veredito(self, **kw):
        return fila.registrar_veredito("geladeira_branca", self.arquivo(veredito(**kw)))

    def test_receita_sobe_a_rodada_e_guarda_historico(self):
        o = self.receita()
        self.assertEqual((o["estado"], o["rodada"]), ("em_critica", 1))
        self.assertTrue(fila.caminho_receita("geladeira_branca").exists())
        hist = fila.caminho_receita("geladeira_branca").parent / "historico" / "geladeira_branca" / "rodada_1.json"
        self.assertEqual(json.loads(hist.read_text(encoding="utf-8"))["id"], "geladeira_branca")

    def test_receita_recusada(self):
        ruim = receita()
        ruim["pecas"][0]["max"][2] = -1               # min > max: regra que o esquema não pega
        for nome, r in {"id de outro": receita(id="outra"), "min > max": ruim, "sem peças": receita(pecas=[])}.items():
            with self.subTest(nome), self.assertRaises(fila.ArquivoInvalido):
                fila.registrar_receita("geladeira_branca", self.arquivo(r))
        o = fila.obter("geladeira_branca")
        self.assertEqual((o["estado"], o["rodada"]), ("em_modelagem", 0))
        self.assertFalse(fila.caminho_receita("geladeira_branca").exists())

    def test_receita_fora_da_modelagem(self):
        self.semear(registro(estado="em_critica", rodada=1))
        with self.assertRaises(fila.TransicaoInvalida):
            self.receita()

    def test_receita_pode_ser_o_proprio_arquivo_de_receitas(self):
        """O modelador pode gravar direto em receitas/<id>.json; registrar não pode quebrar com isso."""
        destino = fila.caminho_receita("geladeira_branca")
        destino.parent.mkdir(parents=True)
        destino.write_text(json.dumps(receita()), encoding="utf-8")
        self.assertEqual(fila.registrar_receita("geladeira_branca", destino)["rodada"], 1)
        self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["id"], "geladeira_branca")

    def test_aprovado_pelo_critico_vai_para_a_galeria(self):
        self.receita()
        o = self.veredito(arte=8, realista=8.5)
        self.assertEqual(o["estado"], "aguardando_aprovacao")
        self.assertEqual(o["notas"], [{"rodada": 1, "arte": 8, "realista": 8.5}])
        self.assertTrue(fila.caminho_veredito("geladeira_branca", 1).exists())
        self.assertIsNone(o["motivo"])

    def test_uma_nota_baixa_manda_para_retrabalho(self):
        self.receita()
        self.assertEqual(self.veredito(arte=9, realista=7.5)["estado"], "retrabalho")

    def test_laco_de_tres_rodadas_termina_em_reprovado(self):
        for rodada in (1, 2, 3):
            self.assertEqual(self.estado(), "em_modelagem")
            self.receita()
            self.assertEqual(fila.obter("geladeira_branca")["rodada"], rodada)
            ds = [defeito("leve", parte="pe", tipo="sobra"),
                  defeito("grave", parte="porta_cima", tipo="textura_deslocada", nivel="realista", vista="zoom",
                          onde="puxador, metade de baixo"),
                  defeito("media")]
            o = self.veredito(rodada=rodada, arte=6, realista=5, defeitos=ds)
            if rodada < 3:
                self.assertEqual(o["estado"], "retrabalho")
                self.assertIsNone(o["motivo"])
                fila.mover("geladeira_branca", "em_modelagem")
        self.assertEqual(o["estado"], "reprovado")
        self.assertEqual(o["rodada"], 3)
        self.assertEqual(o["motivo"], "porta_cima: textura_deslocada (realista, zoom) — puxador, metade de baixo")
        self.assertEqual([n["rodada"] for n in o["notas"]], [1, 2, 3])
        for r in (1, 2, 3):
            self.assertTrue(fila.caminho_veredito("geladeira_branca", r).exists())
        with self.assertRaises(fila.TransicaoInvalida):
            fila.mover("geladeira_branca", "em_modelagem")

    def test_motivo_do_reprovado_sem_defeitos(self):
        self.semear(registro(estado="em_critica", rodada=3))
        v = veredito(rodada=3, arte=7, realista=7, pecas=[{"nome": "corpo", "situacao": "ok"},
                                                          {"nome": "pe", "situacao": "ausente"}])
        o = fila.registrar_veredito("geladeira_branca", self.arquivo(v))
        self.assertEqual((o["estado"], o["motivo"]), ("reprovado", "pe: ausente"))
        self.semear(registro(estado="em_critica", rodada=3))
        o = fila.registrar_veredito("geladeira_branca", self.arquivo(veredito(rodada=3, arte=7, realista=7)))
        self.assertIn("sem defeito listado", o["motivo"])

    def test_gravidade_empata_na_ordem_da_lista(self):
        self.semear(registro(estado="em_critica", rodada=3))
        ds = [defeito("media", parte="a"), defeito("media", parte="b")]
        v = veredito(rodada=3, arte=5, realista=5, defeitos=ds)
        o = fila.registrar_veredito("geladeira_branca", self.arquivo(v))
        self.assertTrue(o["motivo"].startswith("a: "))

    def test_veredito_recusado(self):
        self.receita()
        casos = {
            "objeto de outro": veredito(id="outra"),
            "rodada errada": veredito(rodada=2),
            "nota acima de 10": veredito(arte=11),
            "sem observação": {k: v for k, v in veredito().items() if k != "observacao"},
            "gravidade desconhecida": veredito(defeitos=[defeito("pior")]),
            "tipo desconhecido": veredito(defeitos=[{**defeito(), "tipo": "feio"}]),
        }
        for nome, v in casos.items():
            with self.subTest(nome), self.assertRaises(fila.ArquivoInvalido):
                fila.registrar_veredito("geladeira_branca", self.arquivo(v))
        o = fila.obter("geladeira_branca")
        self.assertEqual((o["estado"], o["notas"]), ("em_critica", []))
        self.assertFalse(fila.caminho_veredito("geladeira_branca", 1).exists())

    def test_veredito_fora_da_critica(self):
        with self.assertRaises(fila.TransicaoInvalida):
            self.veredito()


class TestAprovacao(Base):
    def setUp(self):
        super().setUp()
        self.semear(registro(estado="aguardando_aprovacao", rodada=2, notas=[{"rodada": 2, "arte": 9, "realista": 8}]))

    def test_aprovar_e_publicar(self):
        o = fila.decidir("geladeira_branca", "aprovado", "ficou ótima")
        self.assertEqual((o["estado"], o["comentario_usuario"]), ("aprovado", "ficou ótima"))
        self.assertEqual(fila.mover("geladeira_branca", "publicado")["estado"], "publicado")

    def test_rejeitar_espera_e_volta_ao_retrabalho_com_rodada_zerada(self):
        o = fila.decidir("geladeira_branca", "rejeitado", "a porta está torta")
        self.assertEqual((o["estado"], o["rodada"]), ("rejeitado", 2))
        o = fila.mover("geladeira_branca", "retrabalho")
        self.assertEqual((o["estado"], o["rodada"]), ("retrabalho", 0))
        self.assertEqual(o["comentario_usuario"], "a porta está torta")
        self.assertEqual(len(o["notas"]), 1)                                   # o histórico fica
        self.assertEqual([h["para"] for h in o["historico"]], ["rejeitado", "retrabalho"])
        fila.mover("geladeira_branca", "em_modelagem")
        fila.registrar_receita("geladeira_branca", self.arquivo(receita()))
        self.assertEqual(fila.obter("geladeira_branca")["rodada"], 1)          # tem de novo 3 rodadas

    def test_decisoes_invalidas(self):
        with self.assertRaises(fila.FilaErro):
            fila.decidir("geladeira_branca", "talvez")
        self.semear(registro(estado="em_critica"))
        with self.assertRaises(fila.TransicaoInvalida):
            fila.decidir("geladeira_branca", "aprovado")


class TestFluxoCompleto(Base):
    def test_do_comeco_ao_publicado(self):
        self.semear(registro())
        fila.mover("geladeira_branca", "em_inspecao")
        fila.registrar_ficha("geladeira_branca", self.arquivo(ficha()))
        fila.registrar_receita("geladeira_branca", self.arquivo(receita()))
        fila.registrar_veredito("geladeira_branca", self.arquivo(veredito(arte=9, realista=9)))
        fila.decidir("geladeira_branca", "aprovado")
        fila.mover("geladeira_branca", "publicado")
        o = fila.obter("geladeira_branca")
        self.assertEqual([h["para"] for h in o["historico"]], [
            "em_inspecao", "em_modelagem", "em_critica", "aguardando_aprovacao", "aprovado", "publicado"])

    def test_nao_portar_do_comeco_ao_fim(self):
        self.semear(registro())
        fila.mover("geladeira_branca", "em_inspecao")
        fila.registrar_ficha("geladeira_branca", self.arquivo(ficha(decisao="nao_portar", motivo="só tem plano")))
        self.assertEqual(fila.resumo()["nao_portar"], 1)
        with self.assertRaises(fila.TransicaoInvalida):
            fila.mover("geladeira_branca", "em_modelagem")


class TestPopular(Base):
    """Acervo sintético: geladeiras em 3 cores e mesma forma, uma mini, sofás sem Facing, uma peça de vários tiles,
    objetos sem geometria, só em 1x ou sem vista S, e um de outra categoria."""

    def setUp(self):
        super().setUp()
        self.ac = AcervoSintetico(self.tmp / "acervo")
        self.addCleanup(self.ac.close)
        self.db = self.ac.db

    def objeto(self, tileset, idx0, custom, grupo, categoria="eletrodomesticos", dirs="SENW", mn=(-4000, 0, -4000),
               mx=(4000, 15000, 4000), geometria=True, grade=None, escala=2):
        """Cria os sprites de um objeto; `-` em `dirs` é um sprite sem Facing."""
        for k, d in enumerate(dirs):
            nome = f"{tileset}_{idx0 + k}"
            self.ac.sprite(nome, scale=escala)
            props = {"CustomName": custom, "GroupName": grupo, "Material": "Fridge"}
            if d != "-":
                props["Facing"] = d
            if grade:
                props["SpriteGridPos"] = grade
            self.ac.tile(nome, tileset, idx0 + k, **props)
            self.db.execute("update tiles set category=? where name=?", (categoria, nome))
            if geometria:
                self.ac.caixa(nome, 0, mn, mx)
        self.db.commit()

    def monta(self):
        self.objeto("app", 0, "Fridge", "White")
        self.objeto("app", 4, "Fridge", "Blue")                                 # mesma forma, outra cor
        self.objeto("app", 8, "Fridge", "Steel", mx=(4000, 15004, 4000))        # diferença < 1 cm: mesma forma
        self.objeto("app", 12, "Fridge", "Mini", mx=(4000, 9000, 4000))         # outra forma
        self.objeto("app", 16, "Fridge", "Large", grade="0,0")                  # vários tiles: fora
        self.objeto("moveis", 0, "Sofa", "Gray", categoria="moveis", dirs="-")  # sem Facing
        self.objeto("moveis", 1, "Sofa", "Red", categoria="moveis", dirs="-")
        self.objeto("moveis", 2, "Lamp", "Old", categoria="iluminacao", dirs="SENW")
        self.objeto("app", 20, "Fridge", "Ghost", geometria=False)              # sem geometria: fora
        self.objeto("app", 24, "Fridge", "Pequena", escala=1)                   # só 1x: fora
        self.objeto("app", 28, "Radio", "Ham", dirs="EW")                       # sem vista S: fora

    def test_agrupa_por_objeto_e_marca_variantes(self):
        self.monta()
        ids = fila.popular(["eletrodomesticos"], db=self.db)
        self.assertEqual(sorted(ids), ["fridge_blue", "fridge_mini", "fridge_steel", "fridge_white"])
        o = {i: fila.obter(i) for i in ids}
        self.assertEqual(o["fridge_white"]["sprites"], {"S": "app_0", "E": "app_1", "N": "app_2", "W": "app_3"})
        self.assertIsNone(o["fridge_white"]["forma_de"])
        self.assertEqual(o["fridge_blue"]["forma_de"], "fridge_white")
        self.assertEqual(o["fridge_steel"]["forma_de"], "fridge_white")          # arredondado a 1 cm
        self.assertIsNone(o["fridge_mini"]["forma_de"])
        r = o["fridge_white"]
        self.assertEqual((r["familia"], r["categoria"], r["tileset"], r["custom_name"], r["group_name"],
                          r["material"], r["estado"], r["rodada"]),
                         ("fridge", "eletrodomesticos", "app", "Fridge", "White", "metal", "fila", 0))
        self.assertEqual((r["notas"], r["motivo"], r["comentario_usuario"]), ([], None, None))
        self.assertEqual(r["historico"][0]["para"], "fila")
        self.assertEqual(r["prioridade"], 404)                                    # 400 (categoria) + 4 da família
        self.assertEqual(fila.popular.ignorados["sem_vista_S"], 1)

    def test_sprite_sem_facing_e_um_objeto_cada_e_categoria_filtra(self):
        self.monta()
        ids = fila.popular(["moveis", "eletrodomesticos"], db=self.db)
        self.assertIn("sofa_gray", ids)
        self.assertIn("sofa_red", ids)
        self.assertEqual(fila.obter("sofa_gray")["sprites"], {"S": "moveis_0"})
        self.assertEqual(fila.obter("sofa_red")["forma_de"], "sofa_gray")        # mesma geometria, outro GroupName
        self.assertEqual(fila.obter("sofa_gray")["prioridade"], 302)
        self.assertFalse(any(i.startswith("lamp") for i in ids))                  # iluminacao não foi pedida

    def test_segunda_chamada_nao_duplica_e_variante_liga_na_forma_existente(self):
        self.objeto("app", 0, "Fridge", "White")
        self.assertEqual(fila.popular(["eletrodomesticos"], db=self.db), ["fridge_white"])
        fila.mover("fridge_white", "em_inspecao")
        self.assertEqual(fila.popular(["eletrodomesticos"], db=self.db), [])
        self.objeto("app", 4, "Fridge", "Blue")
        self.assertEqual(fila.popular(["eletrodomesticos"], db=self.db), ["fridge_blue"])
        self.assertEqual(fila.obter("fridge_blue")["forma_de"], "fridge_white")
        self.assertEqual(fila.obter("fridge_white")["estado"], "em_inspecao")     # o que já estava na fila não mudou
        self.assertEqual(fila.popular.ignorados["ja_na_fila"], 1)

    def test_limite_corta_pela_prioridade_e_agrupa_a_forma_com_as_variantes(self):
        self.monta()
        ids = fila.popular("eletrodomesticos", limite=2, db=self.db)
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(fila.objetos()), 2)
        o = [fila.obter(i) for i in ids]
        self.assertTrue(all(x["prioridade"] == 404 for x in o))
        for x in o:                                  # nenhuma variante entra sem a forma-base
            self.assertTrue(x["forma_de"] is None or x["forma_de"] in ids)

    def test_limite_nao_deixa_variante_sem_base(self):
        """A variante tem prioridade maior que a base (outra categoria), então vem primeiro; a base entra junto."""
        self.objeto("a_app", 0, "Fridge", "Zebra", categoria="containers")
        self.objeto("b_app", 0, "Fridge", "Alfa")
        ids = fila.popular(["containers", "eletrodomesticos"], limite=1, db=self.db)
        self.assertEqual(ids, ["fridge_zebra", "fridge_alfa"])
        self.assertEqual(fila.obter("fridge_alfa")["forma_de"], "fridge_zebra")
        self.assertGreater(fila.obter("fridge_alfa")["prioridade"], fila.obter("fridge_zebra")["prioridade"])

    def test_ids_repetidos_ganham_o_tileset(self):
        self.objeto("app_a", 0, "Fridge", "White")
        self.objeto("app_b", 0, "Fridge", "White")
        ids = fila.popular(["eletrodomesticos"], db=self.db)
        self.assertEqual(sorted(ids), ["fridge_white", "fridge_white_app_b"])

    def test_modulos_repetidos_do_mesmo_grupo_viram_objetos_separados(self):
        """Duas séries S/E no mesmo (tileset, CustomName, GroupName) são dois balcões, não um."""
        self.objeto("bal", 0, "Counter", "Low", dirs="SE", categoria="cozinha")
        self.objeto("bal", 2, "Counter", "Low", dirs="SE", categoria="cozinha", mx=(4000, 9000, 4000))
        ids = fila.popular(["cozinha"], db=self.db)
        self.assertEqual(len(ids), 2)
        self.assertEqual(sorted(fila.obter(i)["sprites"]["S"] for i in ids), ["bal_0", "bal_2"])
        self.assertEqual(fila.obter(ids[0])["sprites"], {"S": "bal_0", "E": "bal_1"})

    def test_custom_name_vazio_do_jogo_usa_o_tileset(self):
        """Alguns tiles do jogo (rádios) trazem CustomName = 'CustomName': não é nome, e não pode virar família."""
        self.objeto("radios", 0, "CustomName", "ValuTech", dirs="S")
        self.objeto("radios", 1, "CustomName", "Premium", dirs="S")
        self.objeto("outros", 0, "CustomName", "ValuTech", dirs="S")      # outro tileset, mesma geometria: outra família
        ids = fila.popular(["eletrodomesticos"], db=self.db)
        self.assertEqual(sorted(ids), ["outros_0_valutech", "radios_0_valutech", "radios_1_premium"])
        self.assertEqual(fila.obter("radios_0_valutech")["familia"], "radios")
        self.assertIsNone(fila.obter("radios_0_valutech")["custom_name"])
        self.assertEqual(fila.obter("radios_1_premium")["forma_de"], "radios_0_valutech")
        self.assertIsNone(fila.obter("outros_0_valutech")["forma_de"])

    def test_categorias_vazias(self):
        with self.assertRaises(fila.FilaErro):
            fila.popular([], db=self.db)

    def test_prioridade_ordena_proximos(self):
        self.monta()
        fila.popular(["moveis", "eletrodomesticos"], db=self.db)
        p = fila.proximos("fila", 10)
        self.assertEqual(p[0]["id"], "fridge_blue")                              # 404, desempate por id
        self.assertEqual([o["prioridade"] for o in p], sorted((o["prioridade"] for o in p), reverse=True))
        self.assertEqual(p[-1]["categoria"], "moveis")


class TestLinhaDeComando(Base):
    def test_cli_ficha_status_e_erro(self):
        self.semear(registro(estado="em_inspecao"))
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            self.assertEqual(fila.main(["ficha", "geladeira_branca", str(self.arquivo(ficha()))]), 0)
            self.assertEqual(fila.main(["status"]), 0)
            self.assertEqual(fila.main(["mover", "geladeira_branca", "aprovado"]), 1)
            self.assertEqual(fila.main(["ver", "nada"]), 1)
        self.assertIn("em_modelagem", buf.getvalue())
        self.assertIn("erro: geladeira_branca: em_modelagem → aprovado", err.getvalue())


if __name__ == "__main__":
    unittest.main()
