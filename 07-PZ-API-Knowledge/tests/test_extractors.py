"""Testes dos extratores contra uma arvore sintetica em tests/fixtures/game.

Rodar:  python -m unittest discover -s 07-PZ-API-Knowledge/tests -v
   ou:  python 07-PZ-API-Knowledge/tests/test_extractors.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import build_index  # noqa: E402
import extract_lua  # noqa: E402
import extract_scripts  # noqa: E402
import extract_translations  # noqa: E402

GAME = HERE / "fixtures" / "game"


def new_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    return conn


class LuaExtractorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = new_db()
        cls.res = extract_lua.extract(cls.conn, GAME)

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def test_counts(self):
        self.assertEqual(self.res["lua_files"], 2)
        self.assertGreater(self.res["usages"], 10)

    def test_global_and_method_calls(self):
        rows = self.q("SELECT file, line, snippet FROM usages WHERE symbol='getScriptManager'")
        self.assertEqual(rows, [("client/ISDemo.lua", 11, "local sm = getScriptManager()")])
        self.assertTrue(self.q("SELECT 1 FROM usages WHERE symbol='getCraftRecipe' AND owner IS NULL"))
        self.assertTrue(self.q("SELECT 1 FROM usages WHERE symbol='instanceItem'"))
        self.assertTrue(self.q("SELECT 1 FROM usages WHERE symbol='drawText'"))

    def test_owner_inference(self):
        self.assertTrue(
            self.q("SELECT 1 FROM usages WHERE symbol='loadFiles' AND owner='Translator'")
        )
        self.assertTrue(
            self.q("SELECT 1 FROM usages WHERE symbol='derive' AND owner='ISPanel'")
        )

    def test_comments_and_strings_ignored(self):
        for fake in ("getFake", "OnFake", "fakeCall", "OnString", "getBlockComment", "longCall"):
            self.assertFalse(self.q("SELECT 1 FROM usages WHERE symbol=?", fake), fake)

    def test_locals_stdlib_and_definitions_not_global_calls(self):
        # `cb` e parametro, localHelper2 nao e local mas e chamada global; print/table.insert ignorados
        self.assertFalse(self.q("SELECT 1 FROM usages WHERE symbol='cb'"))
        self.assertFalse(self.q("SELECT 1 FROM usages WHERE symbol IN ('print','insert')"))
        self.assertTrue(self.q("SELECT 1 FROM usages WHERE symbol='localHelper2'"))
        # `function ISDemo:render()` e definicao, nao uso
        self.assertFalse(self.q("SELECT 1 FROM usages WHERE symbol='render'"))

    def test_event_usages(self):
        rows = self.q(
            "SELECT file, line FROM usages WHERE symbol='OnServerStarted' AND owner='Events'"
        )
        self.assertEqual(rows, [("client/ISDemo.lua", 33)])
        self.assertEqual(
            len(self.q("SELECT 1 FROM usages WHERE symbol='OnTick' AND owner='Events'")), 2
        )
        self.assertTrue(self.q("SELECT 1 FROM usages WHERE symbol='OnDemoThing' AND owner='Events'"))
        # `Add`/`Remove` de Events.X.Add nao viram usos genericos
        self.assertFalse(self.q("SELECT 1 FROM usages WHERE symbol IN ('Add','Remove')"))
        # chamadas dentro do callback anonimo ainda contam
        self.assertTrue(self.q("SELECT 1 FROM usages WHERE symbol='doThing' AND owner='ISDemoHelper'"))

    def test_event_symbols(self):
        names = {r[0] for r in self.q("SELECT name FROM symbols WHERE kind='event' AND origin='lua'")}
        self.assertEqual(names, {"OnServerStarted", "OnTick", "OnDemoThing"})
        # AddEvent e a definicao: o arquivo/linha apontam para ela
        self.assertEqual(
            self.q("SELECT file, line FROM symbols WHERE kind='event' AND name='OnDemoThing'"),
            [("media/lua/shared/DemoShared.lua", 1)],
        )

    def test_lua_globals(self):
        rows = {
            (n, o): (sig, st, f, ln)
            for n, o, sig, st, f, ln in self.q(
                "SELECT name, owner, signature, is_static, file, line FROM symbols"
                " WHERE kind='lua_global'"
            )
        }
        self.assertEqual(rows[("ISDemo", None)][0], 'ISDemo = ISPanel:derive("ISDemo")')
        self.assertEqual(rows[("ISDemo", None)][2:], ("media/lua/client/ISDemo.lua", 2))
        self.assertIn(("ISDemoHelper", None), rows)
        self.assertEqual(rows[("render", "ISDemo")][:2], ("function ISDemo:render()", 0))
        self.assertEqual(rows[("doThing", "ISDemoHelper")][:2],
                         ("function ISDemoHelper.doThing(player, item)", 1))
        self.assertEqual(rows[("method", "DemoShared")][1], 0)
        self.assertEqual(rows[("value", "DemoShared")][0], "DemoShared.value = function(x, y)")
        self.assertEqual(rows[("globalFunc", None)][0], "function globalFunc(arg)")
        self.assertIn(("DemoShared", None), rows)
        # locais e definicoes aninhadas nao sao globais de topo
        self.assertNotIn(("localHelper", None), rows)
        self.assertNotIn(("onStart", None), rows)
        self.assertNotIn(("Inside", None), rows)

    def test_snippet_limit(self):
        long_line = "foo(" + "x" * 500 + ")"
        usages, _, _ = extract_lua.scan_file("a.lua", "media/lua/a.lua", long_line)
        self.assertEqual(len(usages[0][4]), 200)


class ScriptExtractorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = new_db()
        cls.res = extract_scripts.extract(cls.conn, GAME)

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def fields(self, block_type):
        return {r[0]: r[1:] for r in self.q(
            "SELECT field, count, example_value FROM script_fields WHERE block_type=?",
            block_type)}

    def test_blocks(self):
        rows = self.q("SELECT block_type, module, name, file, line FROM script_blocks"
                      " ORDER BY block_type, name")
        self.assertIn(("item", "Base", "DemoItem", "generated/items/demo.txt", 10), rows)
        self.assertIn(("item", "Base", "DemoFood", "generated/items/demo.txt", 20), rows)
        self.assertIn(("craftRecipe", "Base", "DemoRecipe", "generated/recipes/demo.txt", 3), rows)
        self.assertIn(("fluid", "Base", "DemoFluid", "generated/recipes/demo.txt", 25), rows)
        self.assertIn(("template vehicle", "Base", "DemoTemplate", "generated/recipes/demo.txt", 38), rows)
        self.assertFalse([r for r in rows if r[0] in ("imports", "module")])

    def test_item_fields(self):
        f = self.fields("item")
        self.assertEqual(f["ItemType"][0], 2)
        self.assertEqual(f["ItemType"][1], "base:normal")
        self.assertEqual(f["UseDelta"], (1, "0.1"))
        self.assertEqual(f["Icon"][0], 2)
        self.assertIn("DisplayCategory", f)
        self.assertEqual(f["Tags"][1], "base:a;base:b")

    def test_craft_recipe_fields(self):
        f = self.fields("craftRecipe")
        for name in ("timedAction", "time", "category", "inputs", "outputs"):
            self.assertIn(name, f)
        self.assertEqual(f["time"], (1, "50"))
        self.assertEqual(f["inputs.item"], (3, "item 2 [Base.Paperclip] mode:keep flags[Prop1;MayDegradeLight],"))
        self.assertEqual(f["outputs.item"][0], 1)
        self.assertEqual(f["inputs.item mode:keep"][0], 1)
        self.assertEqual(f["inputs.item mode:destroy"][0], 1)
        self.assertEqual(f["inputs.item flags[Prop1]"][0], 1)
        self.assertEqual(f["inputs.item flags[MayDegradeLight]"][0], 1)
        self.assertEqual(f["inputs.item tags[]"][0], 1)
        self.assertEqual(f["inputs.item mappers[]"][0], 1)
        self.assertEqual(f["outputs.item mapper:"][0], 1)
        self.assertIn("itemMapper", f)
        self.assertIn("itemMapper.default", f)
        # mapeamentos arbitrarios (`Base.A = Base.B`) nao poluem os campos
        self.assertFalse([k for k in f if k.startswith("itemMapper.Base")])

    def test_other_block_types(self):
        self.assertIn("DisplayName", self.fields("fluid"))
        self.assertIn("Properties.ThirstChange", self.fields("fluid"))
        # entradas simples de lista (`Beverage,`) nao viram campos
        self.assertNotIn("Categories.Beverage", self.fields("fluid"))
        self.assertIn("part.area", self.fields("template vehicle"))

    def test_example_location(self):
        row = self.q(
            "SELECT example_file, example_line FROM script_fields"
            " WHERE block_type='item' AND field='UseDelta'")
        self.assertEqual(row, [("generated/items/demo.txt", 16)])


class TranslationExtractorTest(unittest.TestCase):
    def test_only_en_and_ptbr(self):
        conn = new_db()
        res = extract_translations.extract(conn, GAME)
        langs = {r[0] for r in conn.execute("SELECT DISTINCT lang FROM translations")}
        self.assertEqual(langs, {"EN", "PTBR"})
        self.assertEqual(res["translations"], 5)
        row = conn.execute(
            "SELECT value, category, file FROM translations"
            " WHERE lang='EN' AND key='Base.Paperclip'").fetchone()
        self.assertEqual(row, ("Paperclip", "ItemName",
                               "media/lua/shared/Translate/EN/ItemName.json"))
        row = conn.execute(
            "SELECT value FROM translations WHERE lang='PTBR' AND key='Base.Paperclip'"
        ).fetchone()
        self.assertEqual(row[0], "Clipe de papel")
        self.assertEqual(
            conn.execute("SELECT category FROM translations WHERE key='UI_Demo'").fetchone()[0],
            "UI")


class BuildIndexTest(unittest.TestCase):
    def setUp(self):
        # hermetico: extract_java precisa do jar real do jogo e e testado a parte
        self._orig = build_index.EXTRACTORS
        build_index.EXTRACTORS = [e for e in self._orig if e[0] != "extract_java"]

    def tearDown(self):
        build_index.EXTRACTORS = self._orig

    def test_full_build_on_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x" / "pz_api.sqlite"
            r = build_index.build(GAME, out)
            self.assertTrue(out.exists())
            self.assertEqual(r["version"], "42.21")
            conn = sqlite3.connect(out)
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            for t in build_index.TABLES:
                self.assertEqual(meta[f"count_{t}"], str(r["counts"][t]))
            self.assertIn("built_at", meta)
            # FTS preenchida e consultavel
            hits = conn.execute(
                "SELECT name FROM symbols_fts WHERE symbols_fts MATCH 'OnDemoThing'").fetchall()
            self.assertEqual(hits, [("OnDemoThing",)])
            conn.close()
            # reconstruir apaga o banco anterior (sem duplicar linhas)
            r2 = build_index.build(GAME, out)
            self.assertEqual(r["counts"], r2["counts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
