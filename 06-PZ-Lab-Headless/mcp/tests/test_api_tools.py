"""
Testes das ferramentas de consulta da API (api_search, api_class, api_event, script_fields,
vanilla_examples, api_exists) contra um banco de fixture sintético.

Rodar (a partir de 06-PZ-Lab-Headless/mcp):  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import api_index  # noqa: E402
import server  # noqa: E402
from api_fixture import build_fixture_db  # noqa: E402


class ApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="pz_api_test_"))
        cls.db = build_fixture_db(cls.tmp / "pz_api.sqlite")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        p = mock.patch.dict(os.environ, {"PZ_API_DB": str(self.db)})
        p.start()
        self.addCleanup(p.stop)

    def assertMeta(self, r):
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["meta"]["game_version"], "42.21.0-fixture")
        self.assertEqual(r["meta"]["built_at"], "2026-10-11T12:00:00Z")


class TestSearch(ApiBase):
    def test_found_exact_first_with_call_forms(self):
        r = server.api_search("getCraftRecipe")
        self.assertMeta(r)
        self.assertTrue(r["found"])
        first = r["results"][0]
        self.assertEqual((first["name"], first["owner"], first["kind"]), ("getCraftRecipe", "ScriptManager", "method"))
        self.assertEqual(first["call"], "obj:getCraftRecipe")
        self.assertIn("CraftRecipe getCraftRecipe(String)", first["signature"])

    def test_exact_ranks_before_others(self):
        r = api_index.api_search("ScriptManager")
        self.assertEqual(r["results"][0]["kind"], "class")
        self.assertEqual(r["results"][0]["name"], "ScriptManager")
        self.assertGreater(r["count"], 1)  # membros do ScriptManager (via owner) vêm depois

    def test_call_forms_static_global_event(self):
        self.assertEqual(api_index.api_search("loadFiles")["results"][0]["call"], "Translator.loadFiles")
        self.assertEqual(api_index.api_search("getScriptManager")["results"][0]["call"], "getScriptManager()")
        self.assertEqual(api_index.api_search("OnServerStarted", kind="event")["results"][0]["call"],
                         "Events.OnServerStarted")

    def test_qualified_query(self):
        r = api_index.api_search("ScriptManager:getCraftRecipe")
        self.assertEqual(r["results"][0]["name"], "getCraftRecipe")
        r = api_index.api_search("Events.OnServerStarted")
        self.assertEqual(r["results"][0]["kind"], "event")

    def test_kind_filter(self):
        r = api_index.api_search("ScriptManager", kind="class")
        self.assertEqual({x["kind"] for x in r["results"]}, {"class"})
        r = api_index.api_search("instance", kind="method")
        self.assertFalse(r["found"])
        r = api_index.api_search("instance", kind="field")
        self.assertEqual(r["results"][0]["call"], "ScriptManager.instance")

    def test_bad_kind_and_empty(self):
        self.assertFalse(api_index.api_search("x", kind="nope")["ok"])
        self.assertEqual(api_index.api_search("  ")["error_kind"], "usage")

    def test_prefix_and_not_found_with_suggestions(self):
        r = api_index.api_search("getCraftRecepi")
        self.assertMeta(r)
        self.assertFalse(r["found"])
        self.assertIn("getCraftRecipe", [s["name"] for s in r["suggestions"]])
        self.assertIn("hint", r)
        r = api_index.api_search("getCraft")  # prefixo
        self.assertTrue(r["found"])

    def test_like_fallback_when_fts_empty(self):
        db = build_fixture_db(self.tmp / "nofts.sqlite", populate_fts=False)
        with mock.patch.dict(os.environ, {"PZ_API_DB": str(db)}):
            r = api_index.api_search("raftRec")  # nem exato, nem FTS: só LIKE
        self.assertTrue(r["found"])
        self.assertEqual(r["mode"], "like")
        self.assertIn("getCraftRecipe", [x["name"] for x in r["results"]])

    def test_limit(self):
        r = api_index.api_search("Script", limit=1)
        self.assertEqual(r["count"], 1)
        self.assertTrue(r["truncated"])

    def test_read_only(self):
        before = self.db.read_bytes()
        api_index.api_search("getItem")
        self.assertEqual(before, self.db.read_bytes())
        conn = api_index._connect_ro(self.db)
        try:
            with self.assertRaises(sqlite3.Error):
                conn.execute("DELETE FROM symbols")
        finally:
            conn.close()


class TestClass(ApiBase):
    def test_short_and_fqn(self):
        for name in ("ScriptManager", "zombie.scripting.ScriptManager", "scriptmanager"):
            r = server.api_class(name)
            self.assertMeta(r)
            self.assertTrue(r["found"], name)
            self.assertEqual(r["java_class"], "zombie.scripting.ScriptManager")

    def test_static_vs_instance(self):
        r = api_index.api_class("ItemContainer")
        self.assertEqual([m["name"] for m in r["static_methods"]], ["new"])
        self.assertEqual(r["static_methods"][0]["call"], "ItemContainer.new")
        self.assertEqual([m["name"] for m in r["instance_methods"]], ["getItems"])
        self.assertEqual(r["instance_methods"][0]["call"], "obj:getItems")
        r = api_index.api_class("ScriptManager")
        self.assertEqual([f["name"] for f in r["static_fields"]], ["instance"])
        self.assertEqual(r["instance_fields"], [])
        self.assertEqual(r["counts"]["instance_methods"], 2)

    def test_filter_and_limit(self):
        r = api_index.api_class("ScriptManager", filter="craft")
        self.assertEqual([m["name"] for m in r["instance_methods"]], ["getCraftRecipe"])
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["total_members"], 3)
        r = api_index.api_class("ScriptManager", limit=1)
        self.assertEqual(r["shown"], 1)
        self.assertTrue(r["truncated"])

    def test_not_found_suggestions(self):
        r = api_index.api_class("ScriptManagr")
        self.assertMeta(r)
        self.assertFalse(r["found"])
        self.assertIn("ScriptManager", [s["name"] for s in r["suggestions"]])

    def test_lua_global_is_not_a_java_class(self):
        r = api_index.api_class("ISInventoryPage")
        self.assertFalse(r["found"])
        self.assertEqual(r["also_found_as"][0]["kind"], "lua_global")


class TestEvent(ApiBase):
    def test_found_with_usages_and_callback(self):
        r = server.api_event("Events.OnPlayerUpdate")
        self.assertMeta(r)
        self.assertTrue(r["exists"])
        self.assertEqual(r["usage_count"], 3)  # a linha com owner NULL não é uso de Events
        self.assertEqual(r["usages"][0]["location"].count(":"), 1)
        self.assertEqual(r["callback"]["args"], ["player"])  # maioria
        self.assertEqual(r["callback"]["variants"][1]["args"], ["p"])

    def test_zero_args_and_named_handler(self):
        r = api_index.api_event("OnServerStarted")
        self.assertEqual(r["callback"]["args"], [])
        self.assertEqual(r["callback"]["named_handlers"], ["onStart"])
        self.assertEqual(r["signature"], "OnServerStarted()")

    def test_no_inference_possible(self):
        r = api_index.api_event("OnFillInventoryObjectContextMenu")
        self.assertTrue(r["exists"])
        self.assertIsNone(r["callback"])

    def test_usages_capped_at_10(self):
        db = build_fixture_db(self.tmp / "many.sqlite")
        c = sqlite3.connect(str(db))
        c.executemany("INSERT INTO usages VALUES ('OnServerStarted','Events',?,?,?)",
                      [(f"server/F{i}.lua", i, "Events.OnServerStarted.Add(function() end)") for i in range(30)])
        c.commit()
        c.close()
        with mock.patch.dict(os.environ, {"PZ_API_DB": str(db)}):
            r = api_index.api_event("OnServerStarted")
        self.assertEqual(len(r["usages"]), 10)
        self.assertEqual(r["usage_count"], 32)

    def test_not_found(self):
        r = api_index.api_event("OnServerStart")
        self.assertMeta(r)
        self.assertFalse(r["exists"])
        self.assertIn("OnServerStarted", [s["name"] for s in r["suggestions"]])


class TestScriptFields(ApiBase):
    def test_list_block_types(self):
        r = server.script_fields()
        self.assertMeta(r)
        self.assertEqual({t["block_type"] for t in r["block_types"]}, {"item", "craftRecipe"})

    def test_fields_of_block(self):
        r = server.script_fields("item")
        self.assertMeta(r)
        self.assertEqual(r["block_count"], 2)
        self.assertEqual(r["fields"][0]["field"], "Weight")  # ordenado por contagem
        by = {f["field"]: f for f in r["fields"]}
        self.assertEqual(by["UseDelta"]["example_value"], "0.1")
        self.assertEqual(by["ItemType"]["example_location"], "items/weapons.txt:5")

    def test_case_insensitive_block_and_detail(self):
        r = api_index.script_fields("CRAFTRECIPE", "timedAction")
        self.assertEqual(r["block_type"], "craftRecipe")
        self.assertEqual(r["detail"]["count"], 250)

    def test_nested_field(self):
        r = api_index.script_fields("craftRecipe", "inputs.item")
        self.assertEqual(r["detail"]["example_value"], "item 1 [Base.Hammer] flags[Prop1],")
        r = api_index.script_fields("craftRecipe", "inputs")
        self.assertEqual(r["detail"]["field"], "inputs")
        self.assertEqual({c["field"] for c in r["children"]}, {"inputs.item", "inputs.fluid"})

    def test_unknown_field_and_block(self):
        r = api_index.script_fields("item", "UseDeltaa")
        self.assertFalse(r["field_found"])
        self.assertIn("UseDelta", r["suggestions"])
        r = api_index.script_fields("item", "timedAction")
        self.assertEqual(r["found_in_other_blocks"][0]["block_type"], "craftRecipe")
        r = api_index.script_fields("itemm")
        self.assertFalse(r["found"])
        self.assertIn("item", r["suggestions"])
        self.assertTrue(r["block_types"])
        r = api_index.script_fields("craftRecipe", "inputs.tool")
        self.assertEqual(r["parent"]["field"], "inputs")


class TestVanillaExamples(ApiBase):
    def test_plain_symbol(self):
        r = server.vanilla_examples("getCraftRecipe")
        self.assertMeta(r)
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["examples"][0]["location"], "shared/Craft.lua:7")
        self.assertIn("getCraftRecipe", r["examples"][0]["snippet"])
        self.assertEqual(r["definitions"][0]["owner"], "ScriptManager")

    def test_qualified_filters_other_owner(self):
        r = api_index.vanilla_examples("ScriptManager:getCraftRecipe")
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["excluded_other_owner"], 1)
        self.assertEqual(r["examples"][0]["owner"], "ScriptManager")  # dono certo primeiro

    def test_event_form_and_limit(self):
        r = api_index.vanilla_examples("Events.OnPlayerUpdate", limit=2)
        self.assertEqual(r["shown"], 2)
        self.assertEqual(r["total"], 4)  # 3 com owner 'Events' + 1 sem owner (inferência incerta)
        self.assertEqual({e["owner"] for e in r["examples"]}, {"Events"})

    def test_not_found_and_unused_symbol(self):
        r = api_index.vanilla_examples("getCraftRecepi")
        self.assertFalse(r["found"])
        self.assertEqual(r["examples"], [])
        r = api_index.vanilla_examples("getItems")  # existe no índice, sem uso
        self.assertFalse(r["found"])
        self.assertTrue(r["definitions"])
        self.assertIn("existe no índice", r["hint"])


class TestExists(ApiBase):
    def test_exists_plain_and_qualified(self):
        r = server.api_exists("getScriptManager")
        self.assertMeta(r)
        self.assertTrue(r["exists"])
        self.assertEqual(r["matches"][0]["call"], "getScriptManager()")
        r = api_index.api_exists("Translator.loadFiles")
        self.assertTrue(r["exists"])
        self.assertEqual(r["matches"][0]["call"], "Translator.loadFiles")
        self.assertTrue(api_index.api_exists("getCraftRecipe", owner="ScriptManager")["exists"])
        self.assertTrue(api_index.api_exists("Events.OnServerStarted")["exists"])
        self.assertTrue(api_index.api_exists("ItemContainer.new")["exists"])

    def test_not_exists_owner_has_no_member(self):
        r = api_index.api_exists("Languages.instance")
        self.assertMeta(r)
        self.assertFalse(r["exists"])
        self.assertFalse(r["owner_exists"])
        self.assertEqual(r["matches"], [])
        r = api_index.api_exists("ScriptManager.getCraftRecipes")
        self.assertFalse(r["exists"])
        self.assertTrue(r["owner_exists"])
        self.assertIn("getCraftRecipe", [s["name"] for s in r["suggestions"]])

    def test_owner_mismatch_and_case(self):
        self.assertFalse(api_index.api_exists("getCraftRecipe", owner="CraftRecipe")["exists"])
        r = api_index.api_exists("getscriptmanager")
        self.assertFalse(r["exists"])
        self.assertEqual(r["case_mismatch"][0]["name"], "getScriptManager")

    def test_events_namespace(self):
        r = api_index.api_exists("Events.OnNothing")
        self.assertFalse(r["exists"])
        r = api_index.api_exists("Events.OnServerStart")
        self.assertIn("OnServerStarted", [s["name"] for s in r["suggestions"]])
        self.assertFalse(api_index.api_exists("OnServerStarted", owner="ScriptManager")["exists"])


class TestDbMissingAndOverride(unittest.TestCase):
    CALLS = [
        lambda: server.api_search("x"), lambda: server.api_class("x"), lambda: server.api_event("x"),
        lambda: server.script_fields("item"), lambda: server.vanilla_examples("x"), lambda: server.api_exists("x"),
    ]

    def test_db_missing(self):
        missing = Path(tempfile.gettempdir()) / "pz_api_definitely_missing.sqlite"
        with mock.patch.dict(os.environ, {"PZ_API_DB": str(missing)}):
            for call in self.CALLS:
                r = call()
                self.assertFalse(r["ok"])
                self.assertEqual(r["error_kind"], "index_missing")
                self.assertIn("python 07-PZ-API-Knowledge/build_index.py", r["hint"])
        self.assertFalse(missing.exists())  # somente leitura: nunca cria o arquivo

    def test_default_path_without_env(self):
        with mock.patch.dict(os.environ, clear=False) as env:
            env.pop("PZ_API_DB", None)
            p = api_index.db_path()
        self.assertEqual(p.parts[-3:], ("07-PZ-API-Knowledge", "data", "pz_api.sqlite"))

    def test_env_override_switches_database(self):
        tmp = Path(tempfile.mkdtemp(prefix="pz_api_ovr_"))
        try:
            a = build_fixture_db(tmp / "a.sqlite")
            b = build_fixture_db(tmp / "b.sqlite")
            c = sqlite3.connect(str(b))
            c.execute("UPDATE meta SET value='42.99-other' WHERE key='game_version'")
            c.commit()
            c.close()
            with mock.patch.dict(os.environ, {"PZ_API_DB": str(a)}):
                self.assertEqual(api_index.api_exists("getItem")["meta"]["game_version"], "42.21.0-fixture")
            with mock.patch.dict(os.environ, {"PZ_API_DB": str(b)}):
                self.assertEqual(api_index.api_exists("getItem")["meta"]["game_version"], "42.99-other")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_corrupt_db(self):
        tmp = Path(tempfile.mkdtemp(prefix="pz_api_bad_"))
        try:
            bad = tmp / "bad.sqlite"
            bad.write_bytes(b"not a sqlite file" * 100)
            with mock.patch.dict(os.environ, {"PZ_API_DB": str(bad)}):
                r = server.api_search("x")
            self.assertFalse(r["ok"])
            self.assertEqual(r["error_kind"], "index_error")
            self.assertIn("build_index.py", r["hint"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_meta_is_tolerated(self):
        tmp = Path(tempfile.mkdtemp(prefix="pz_api_nometa_"))
        try:
            db = build_fixture_db(tmp / "n.sqlite", with_meta=False)
            with mock.patch.dict(os.environ, {"PZ_API_DB": str(db)}):
                r = server.api_exists("getItem")
            self.assertTrue(r["ok"])
            self.assertIsNone(r["meta"]["game_version"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
