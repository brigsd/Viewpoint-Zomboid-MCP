"""
Testes do servidor MCP pz-live contra um servidor ZombieBuddy falso.

Rodar (a partir de 06-PZ-Lab-Headless/mcp):
    python -m unittest discover -s tests -v
Não precisa do jogo, do pzlab real nem de pytest. Os testes de snippets Lua só rodam se `lupa` estiver
instalado (opcional) — caso contrário são pulados.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from fake_zb_server import FakeZB  # noqa: E402
import server  # noqa: E402

SAMPLE_LOG = textwrap.dedent("""\
    LOG  : General     f:0, t:1700000000001> Loading mod MyMod
    LOG  : General     f:0, t:1700000000002> MyMod loaded
    WARN : General     f:0, t:1700000000003> some harmless warning
    ERROR: General     f:0, t:1700000000100> ExceptionLogger.logException> Exception thrown
    \tjava.lang.RuntimeException: attempted index: foo of non-table: null at KahluaThread.tableget line:1689.
    \tat se.krka.kahlua.vm.KahluaThread.tableget(KahluaThread.java:1689)
    ERROR: General     f:0, t:1700000000101> LuaManager$GlobalObject.require> require("x") failed
    -----------------------------------------
    STACK TRACE
    -----------------------------------------
    function: doThing -- file: MyMod_Main.lua line # 12 | MyMod
    function: other -- file: C:\\Zomboid\\mods\\MyMod\\42\\media\\lua\\server\\MyMod_Main.lua line # 30 | MyMod
    LOG  : General     f:0, t:1700000000200> tick
    ERROR: General     f:0, t:1700000000300> ExceptionLogger.logException> Exception thrown
    \tjava.lang.RuntimeException: attempted index: foo of non-table: null at KahluaThread.tableget line:1690.
    \tat se.krka.kahlua.vm.KahluaThread.tableget(KahluaThread.java:1689)
    ERROR: General     f:0, t:1700000000301> LuaManager$GlobalObject.require> require("x") failed
    -----------------------------------------
    STACK TRACE
    -----------------------------------------
    function: doThing -- file: MyMod_Main.lua line # 12 | MyMod
    ERROR: Script      f:0, t:1700000000400> ScriptManager.ParseScript> error parsing item MyMod.Broken in media/scripts/mymod_items.txt
    WARN : General     f:0, t:1700000000500> Exception while loading texture pack
    Exception in thread "main" java.lang.IllegalStateException: unprefixed boom
    \tat zombie.Foo.bar(Foo.java:12)
    LOG  : General     f:0, t:1700000000600> end
    """)


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeZB().start()
        cls.tmp = Path(tempfile.mkdtemp(prefix="pzlive_test_"))
        cls.log = cls.tmp / "server.log"
        cls.log.write_text(SAMPLE_LOG, encoding="utf-8")
        cls.mods = cls.tmp / "mods"
        cls.mods.mkdir()
        cls.env = mock.patch.dict(os.environ, {
            server.ENV_HTTP_BASE: cls.fake.base,
            server.ENV_LOG_FILE: str(cls.log),
            server.ENV_MODS_DIR: str(cls.mods),
        })
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.fake.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.fake.requests.clear()
        self.fake.reload_calls.clear()


class TestLuaExec(BaseCase):
    def test_expression_gets_auto_return_and_defaults(self):
        r = server.lua_exec("1 + 1")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"], 2)
        req = self.fake.last_lua()
        self.assertEqual(req["body"], "return 1 + 1")
        q = req["query"]
        self.assertEqual(q["depth"], ["5"])          # padrão pedido pelo coordenador
        self.assertEqual(q["sandbox"], ["true"])      # padrão do /lua
        self.assertEqual(q["chunkname"], ["pz_live_exec"])
        self.assertTrue(req["headers"]["Content-Type"].startswith("text/plain"))

    def test_depth_param_is_sent_and_deep_tables_are_truncated_by_server(self):
        r = server.lua_exec("return DEEP", depth=1)
        self.assertEqual(self.fake.last_lua()["query"]["depth"], ["1"])
        self.assertEqual(r["result"], {"a": "[table]"})
        r = server.lua_exec("return DEEP", depth=6)
        self.assertEqual(self.fake.last_lua()["query"]["depth"], ["6"])
        self.assertEqual(r["result"]["a"]["b"]["c"]["d"]["e"], {"f": 1})

    def test_depth_is_clamped(self):
        server.lua_exec("return 1", depth=99)
        self.assertEqual(self.fake.last_lua()["query"]["depth"], ["12"])
        server.lua_exec("return 1", depth=0)
        self.assertEqual(self.fake.last_lua()["query"]["depth"], ["1"])

    def test_sandbox_param(self):
        server.lua_exec("return 1", sandbox=False)
        self.assertEqual(self.fake.last_lua()["query"]["sandbox"], ["false"])
        server.lua_exec("return 1", sandbox=True)
        self.assertEqual(self.fake.last_lua()["query"]["sandbox"], ["true"])

    def test_multiline_code_is_not_wrapped(self):
        server.lua_exec("local a = 1\nreturn a")
        self.assertEqual(self.fake.last_lua()["body"], "local a = 1\nreturn a")

    def test_assignment_not_wrapped(self):
        server.lua_exec("x = 5")
        self.assertEqual(self.fake.last_lua()["body"], "x = 5")

    def test_auto_return_disabled(self):
        server.lua_exec("1 + 1", auto_return=False)
        self.assertEqual(self.fake.last_lua()["body"], "1 + 1")

    def test_compile_failure_of_wrapped_expr_falls_back_to_raw(self):
        r = server.lua_exec("FALLBACK_STMT")
        self.assertTrue(r["ok"], r)
        bodies = [x["body"] for x in self.fake.requests if x["path"] == "/lua"]
        self.assertEqual(bodies, ["return FALLBACK_STMT", "FALLBACK_STMT"])

    def test_runtime_error_is_structured_and_not_retried(self):
        r = server.lua_exec("error('boom')")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "lua")
        self.assertIn("boom", r["error"])
        self.assertIn("Known_Main.lua line # 3", r["detail"]["stack"])
        self.assertEqual(r["detail"]["file"], "pz_live_exec")
        self.assertEqual(r["detail"]["line"], 3)
        self.assertEqual(len([x for x in self.fake.requests if x["path"] == "/lua"]), 1)

    def test_syntax_error_is_compile_kind(self):
        r = server.lua_exec("local SYNTAX_ERR\nfoo bar")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "compile")
        self.assertIn("hint", r)

    def test_attempted_index_hint(self):
        r = server.lua_exec("local ATTEMPT_INDEX = 1\nreturn ATTEMPT_INDEX.x")
        self.assertFalse(r["ok"])
        self.assertIn("hint", r)

    def test_java_exception(self):
        r = server.lua_exec("local x = JAVAEX\nreturn x")
        self.assertEqual(r["error_kind"], "java")
        self.assertEqual(r["detail"]["java_exception"]["className"], "java.lang.NullPointerException")
        self.assertIn("a.B.m(X.java:10)", r["detail"]["stack"])

    def test_timeout_task_error(self):
        r = server.lua_exec("local x = TIMEOUT_TASK\nreturn x")
        self.assertEqual(r["error_kind"], "timeout")
        self.assertIn("lua_task_timeout", r["hint"])

    def test_error_globals_header_and_payload(self):
        r = server.lua_exec("local WITH_GLOBALS\nreturn 1", error_globals=["current_test", "other"])
        self.assertEqual(self.fake.last_lua()["headers"]["X-ZombieBuddy-Error-Globals"], "current_test,other")
        self.assertEqual(r["detail"]["error_globals"], {"current_test": "t1"})

    def test_client_timeout_does_not_hang(self):
        t0 = __import__("time").time()
        r = server.lua_exec("local SLEEP\nreturn 1", timeout_ms=500)
        self.assertLess(__import__("time").time() - t0, 2.4)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "timeout")

    def test_empty_code(self):
        self.assertFalse(server.lua_exec("   ")["ok"])


class TestServerDown(unittest.TestCase):
    def test_connection_refused_with_override_env(self):
        with mock.patch.dict(os.environ, {server.ENV_HTTP_BASE: "http://127.0.0.1:1"}):
            r = server.lua_exec("1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "server_down")
        self.assertIn("hint", r)

    def test_hint_says_start_server_when_pzlab_reports_stopped(self):
        fake_pzlab = types.SimpleNamespace(
            status=lambda: {"running": False, "http_ok": False},
            http_base=lambda: "http://127.0.0.1:1",
            log_path=lambda: "nonexistent.log")
        env = {k: v for k, v in os.environ.items() if k != server.ENV_HTTP_BASE}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(server, "pzlab", fake_pzlab):
            r = server.lua_exec("1")
            self.assertEqual(r["error_kind"], "server_down")
            self.assertIn("lab_start", r["hint"])
            fake_pzlab.status = lambda: {"running": True, "http_ok": False}
            r = server.lua_exec("1")
            self.assertIn("boot", r["hint"])

    def test_works_without_pzlab(self):
        env = dict(os.environ)
        env[server.ENV_HTTP_BASE] = "http://127.0.0.1:1"   # nunca bater no servidor real (porta 8642)
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(server, "pzlab", None):
            r = server.lab_start()
            self.assertFalse(r["ok"])
            self.assertEqual(r["error_kind"], "config")
            self.assertFalse(server.lab_status()["ok"])
            self.assertFalse(server.lua_exec("1")["ok"])


class TestLifecycle(unittest.TestCase):
    def test_wrappers_pass_args_and_flag_ok(self):
        calls = []

        def start(mods=None, timeout_s=300):
            calls.append(("start", mods, timeout_s))
            return {"pid": 1, "host": "127.0.0.1", "port": 8642, "mods": mods}

        fake_pzlab = types.SimpleNamespace(
            start=start,
            stop=lambda timeout_s=60: {"stopped": True},
            restart=lambda mods=None, timeout_s=300: {"pid": 2, "mods": mods},
            status=lambda: {"running": False, "http_ok": False},
            http_base=lambda: "http://127.0.0.1:8642")
        with mock.patch.object(server, "pzlab", fake_pzlab):
            r = server.lab_start(["m1"], timeout_s=900)
            self.assertTrue(r["ok"])
            self.assertEqual(r["pid"], 1)
            self.assertEqual(calls, [("start", ["m1"], 900)])
            self.assertTrue(server.lab_stop()["ok"])
            self.assertEqual(server.lab_restart(["a"])["pid"], 2)
            st = server.lab_status()
            self.assertTrue(st["ok"])
            self.assertIn("lab_start", st["hint"])

    def test_exception_in_pzlab_becomes_error_dict(self):
        def boom(**kw):
            raise RuntimeError("java not found")
        fake_pzlab = types.SimpleNamespace(start=boom)
        with mock.patch.object(server, "pzlab", fake_pzlab):
            r = server.lab_start()
        self.assertFalse(r["ok"])
        self.assertIn("java not found", r["error"])
        self.assertIn("hint", r)


class TestLogTools(BaseCase):
    def test_log_tail_file(self):
        r = server.log_tail(lines=3)
        self.assertTrue(r["ok"])
        self.assertEqual(r["source"], "file")
        self.assertEqual(r["count"], 3)
        self.assertTrue(r["text"].splitlines()[-1].endswith("end"))

    def test_log_tail_grep(self):
        r = server.log_tail(lines=10, grep="stack trace")
        self.assertEqual(r["count"], 2)
        r = server.log_tail(grep=r"line # \d+", regex=True)
        self.assertEqual(r["count"], 3)
        self.assertFalse(server.log_tail(grep="(", regex=True)["ok"])

    def test_log_tail_console_endpoint(self):
        r = server.log_tail(lines=5, source="console")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["count"], 5)
        self.assertEqual(self.fake.requests[-1]["query"]["lines"], ["5"])

    def test_log_tail_falls_back_to_http_when_file_missing(self):
        with mock.patch.dict(os.environ, {server.ENV_LOG_FILE: str(self.tmp / "nope.log")}):
            r = server.log_tail(lines=4)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["source"], "console(/log)")

    def test_lua_errors_grouping(self):
        r = server.lua_errors()
        self.assertTrue(r["ok"], r)
        groups = r["groups"]
        by_cat = {}
        for g in groups:
            by_cat.setdefault(g["category"], []).append(g)
        # dois eventos "attempted index" (linhas de erro iguais salvo números) -> 1 grupo, count 2
        idx = [g for g in groups if "attempted index" in g["message"]]
        self.assertEqual(len(idx), 1, [g["message"] for g in groups])
        self.assertEqual(idx[0]["count"], 2)
        self.assertEqual(idx[0]["category"], "lua")
        # require failed + STACK TRACE com arquivo/linha/mod
        req = [g for g in groups if "require" in g["message"]]
        self.assertEqual(len(req), 1)
        self.assertEqual(req[0]["count"], 2)
        locs = req[0]["locations"]
        self.assertEqual((locs[0]["file"], locs[0]["line"], locs[0]["mod"]), ("MyMod_Main.lua", 12, "MyMod"))
        self.assertIn("MyMod", req[0]["mods"])
        self.assertTrue(any(l["line"] == 30 for l in locs))
        # erro de script
        self.assertEqual(len(by_cat["script"]), 1)
        self.assertIn("mymod_items.txt", by_cat["script"][0]["message"])
        # WARN com "Exception" entra; WARN inofensivo não
        msgs = " ".join(g["message"] for g in groups)
        self.assertNotIn("harmless", msgs)
        self.assertIn("texture pack", msgs)
        # stack sem prefixo (Java)
        self.assertTrue(any("unprefixed boom" in g["sample"] for g in groups))
        self.assertEqual(r["unique_errors"], len(groups))
        self.assertGreaterEqual(r["total_events"], 6)

    def test_lua_errors_ignore_and_warnings(self):
        r = server.lua_errors(ignore=["error parsing", "texture pack"])
        self.assertFalse(any(g["category"] == "script" for g in r["groups"]))
        r2 = server.lua_errors(include_warnings=True)
        self.assertTrue(any("harmless" in g["message"] for g in r2["groups"]))

    def test_lua_errors_clean_log(self):
        clean = self.tmp / "clean.log"
        clean.write_text("LOG  : General     f:0, t:1> all good\nLOG  : x f:0, t:2> done\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {server.ENV_LOG_FILE: str(clean)}):
            r = server.lua_errors()
        self.assertTrue(r["ok"])
        self.assertEqual(r["total_events"], 0)
        self.assertEqual(r["groups"], [])

    def test_lua_errors_since_start_false_reads_older_logs(self):
        d = self.tmp / "logs"
        d.mkdir(exist_ok=True)
        (d / "old.log").write_text("ERROR: General f:0, t:1> OldThing.run> Exception thrown\n", encoding="utf-8")
        cur = d / "new.log"
        cur.write_text("LOG  : General f:0, t:2> fresh\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {server.ENV_LOG_FILE: str(cur)}):
            self.assertEqual(server.lua_errors(since_start=True)["total_events"], 0)
            self.assertEqual(server.lua_errors(since_start=False)["total_events"], 1)

    def test_latest_log_text_pointer_is_followed(self):
        ptr = self.tmp / "latest.log"
        ptr.write_text(str(self.log), encoding="utf-8")
        with mock.patch.dict(os.environ, {server.ENV_LOG_FILE: str(ptr)}):
            r = server.log_tail(lines=2)
        self.assertEqual(r["source"], "file")
        self.assertTrue(r["text"].endswith("end"))


class TestInspect(BaseCase):
    def test_inspect_table_and_filter(self):
        r = server.lua_inspect("SandboxVars")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["info"]["lua_type"], "table")
        body = self.fake.last_lua()["body"]
        self.assertIn("SandboxVars", body)
        self.assertEqual(self.fake.last_lua()["query"]["depth"], ["4"])
        r = server.lua_inspect("SandboxVars", filter="a")
        self.assertEqual([e["key"] for e in r["info"]["entries"]], ["a"])

    def test_inspect_java_object_filter_and_cap(self):
        r = server.lua_inspect("JAVAOBJ", filter="zombie")
        self.assertEqual(r["info"]["java_type"], "zombie.Fake")
        self.assertEqual(r["info"]["methods"], ["int getZombieCount()"])
        self.assertEqual(list(r["info"]["fields"]), ["zombieCount"])
        r = server.lua_inspect("JAVAOBJ", max_items=1)
        self.assertEqual(r["omitted"]["methods"], 2)

    def test_private_flag_in_code(self):
        server.lua_inspect("x", include_private=True)
        self.assertIn("local __private = true", self.fake.last_lua()["body"])

    def test_error_propagates(self):
        r = server.lua_inspect("error('x')")
        self.assertFalse(r["ok"])


class TestReload(BaseCase):
    def test_reload_by_suffix(self):
        r = server.reload_lua("media/lua/server/Known_Main.lua")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["status"], "reloaded")
        self.assertTrue(r["loaded_before"])
        self.assertEqual(self.fake.reload_calls, ["C:/Zomboid/mods/known/42/media/lua/server/Known_Main.lua"])
        self.assertTrue(r["new_errors"]["checked"])

    def test_reload_windows_path_falls_back_to_media_suffix(self):
        r = server.reload_lua(r"D:\other\place\mods\known\42\media\lua\server\Known_Main.lua")
        self.assertEqual(r["status"], "reloaded")
        self.assertEqual(r["matched_by"], "media/lua/server/Known_Main.lua")

    def test_reload_ambiguous(self):
        r = server.reload_lua("Dup.lua")
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(len(r["matches"]), 2)
        self.assertEqual(self.fake.reload_calls, [])
        r = server.reload_lua("mods/other/42/media/lua/shared/Dup.lua")
        self.assertEqual(r["status"], "reloaded")

    def test_reload_not_found_and_local_fallback(self):
        r = server.reload_lua("media/lua/server/Nothing.lua")
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "not_found")
        f = self.tmp / "Fresh.lua"
        f.write_text("print('x')", encoding="utf-8")
        r = server.reload_lua(str(f))
        self.assertEqual(r["status"], "reloaded")
        self.assertFalse(r["loaded_before"])
        self.assertIn("warning", r)

    def test_reload_falls_back_to_rerun_when_api_missing(self):
        f = self.tmp / "Rerun.lua"
        f.write_text("MyGlobal = 1\nprint('rerun')\n", encoding="utf-8")
        self.fake.reload_api_missing = True
        try:
            r = server.reload_lua(str(f))
        finally:
            self.fake.reload_api_missing = False
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["method"], "rerun_content")
        self.assertEqual(r["engine_attempt"]["status"], "api_missing")
        req = self.fake.last_lua()
        self.assertEqual(req["query"]["sandbox"], ["false"])
        self.assertEqual(req["query"]["chunkname"], ["Rerun.lua"])
        self.assertEqual(req["body"], "MyGlobal = 1\nprint('rerun')\n")
        self.assertTrue(r["new_errors"]["checked"])

    def test_reload_falls_back_to_rerun_when_engine_errors(self):
        f = self.tmp / "BROKEN_reload.lua"
        f.write_text("x = 1\n", encoding="utf-8")
        r = server.reload_lua(str(f))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["method"], "rerun_content")
        self.assertEqual(r["engine_attempt"]["status"], "error")

    def test_reload_method_engine_does_not_rerun(self):
        f = self.tmp / "Rerun2.lua"
        f.write_text("x = 1\n", encoding="utf-8")
        self.fake.reload_api_missing = True
        try:
            r = server.reload_lua(str(f), method="engine")
        finally:
            self.fake.reload_api_missing = False
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "api_missing")
        self.assertEqual(len([x for x in self.fake.requests if x["path"] == "/lua"]), 1)

    def test_reload_method_rerun_and_missing_local(self):
        f = self.tmp / "Rerun3.lua"
        f.write_text("x = 1\n", encoding="utf-8")
        r = server.reload_lua(str(f), method="rerun")
        self.assertTrue(r["ok"])
        self.assertEqual(self.fake.last_lua()["query"]["sandbox"], ["false"])
        self.assertFalse(server.reload_lua("nope/missing.lua", method="rerun")["ok"])
        self.assertFalse(server.reload_lua("a.lua", method="bogus")["ok"])

    def test_reload_api_missing_without_local_file(self):
        self.fake.reload_api_missing = True
        try:
            r = server.reload_lua("media/lua/server/Known_Main.lua")
        finally:
            self.fake.reload_api_missing = False
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "api_missing")

    def test_reload_rejects_non_lua(self):
        r = server.reload_lua("media/scripts/items.txt")
        self.assertFalse(r["ok"])
        self.assertIn("lab_restart", r["hint"])

    def test_reload_reports_new_log_errors(self):
        log = self.tmp / "grow.log"
        log.write_text("LOG  : General f:0, t:1> before\n", encoding="utf-8")
        orig_post = server._lua_post

        def post_and_log(*a, **kw):
            with open(log, "a", encoding="utf-8") as fh:
                fh.write("ERROR: General f:0, t:2> Foo> attempted index: x of non-table: null\n")
            return orig_post(*a, **kw)

        with mock.patch.dict(os.environ, {server.ENV_LOG_FILE: str(log)}), \
                mock.patch.object(server, "_lua_post", post_and_log):
            r = server.reload_lua("media/lua/server/Known_Main.lua")
        self.assertFalse(r["ok"])
        self.assertEqual(r["new_errors"]["total_events"], 1)
        self.assertEqual(r["status"], "reloaded")

    def test_reload_when_down(self):
        with mock.patch.dict(os.environ, {server.ENV_HTTP_BASE: "http://127.0.0.1:1"}):
            r = server.reload_lua("media/lua/server/Known_Main.lua")
        self.assertEqual(r["error_kind"], "server_down")


class TestRunLuaTest(BaseCase):
    def _write(self, name, body):
        p = self.tmp / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_pass_sends_file_as_body_with_chunkname_and_depth(self):
        p = self._write("t_pass.lua", "-- TESTRESULT_PASS\nreturn {}\n")
        r = server.run_lua_test(str(p))
        self.assertTrue(r["ok"], r)
        self.assertIs(r["test_passed"], True)
        req = self.fake.last_lua()
        self.assertIn("TESTRESULT_PASS", req["body"])
        self.assertEqual(req["query"]["chunkname"], ["t_pass.lua"])
        self.assertEqual(req["query"]["depth"], ["6"])
        self.assertEqual(req["query"]["sandbox"], ["true"])
        self.assertEqual(r["count_failed"], 0)

    def test_depth_and_sandbox_params(self):
        p = self._write("t_pass2.lua", "-- TESTRESULT_PASS\n")
        server.run_lua_test(str(p), depth=3, sandbox=False)
        q = self.fake.last_lua()["query"]
        self.assertEqual(q["depth"], ["3"])
        self.assertEqual(q["sandbox"], ["false"])

    def test_fail_convention(self):
        p = self._write("t_fail.lua", "-- TESTRESULT_FAIL\n")
        r = server.run_lua_test(str(p))
        self.assertFalse(r["ok"])
        self.assertIs(r["test_passed"], False)
        self.assertEqual(r["error_kind"], "test_failed")
        self.assertEqual(r["result"]["failures"], ["expected 1 got 2"])

    def test_no_convention(self):
        p = self._write("t_plain.lua", "-- TESTRESULT_PLAIN\n")
        r = server.run_lua_test(str(p))
        self.assertTrue(r["ok"])
        self.assertIsNone(r["test_passed"])
        self.assertEqual(r["result"], {"value": 42})

    def test_smoke_shape_soft_failures_are_warnings(self):
        p = self._write("t_smoke.lua", "-- TESTRESULT_SMOKE\n")
        r = server.run_lua_test(str(p))
        self.assertTrue(r["ok"], r)
        self.assertIs(r["test_passed"], True)
        self.assertEqual(r["test_name"], "smoke_zblabtest")
        self.assertIn("2/3 passed", r["summary"])
        self.assertIn("[SOFT] optional tag", r["report"])
        self.assertEqual(r["failed_checks"], [])
        self.assertEqual([c["name"] for c in r["warnings"]], ["optional tag"])
        self.assertEqual(r["count_softFailed"] if "count_softFailed" in r else 1, 1)

    def test_smoke_shape_hard_failure_lists_failed_checks(self):
        p = self._write("t_smoke_fail.lua", "-- TESTRESULT_SMOKE_FAIL\n")
        r = server.run_lua_test(str(p))
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "test_failed")
        self.assertEqual([c["name"] for c in r["failed_checks"]], ["recipe parsed"])
        self.assertEqual(r["failed_checks"][0]["detail"], "recipe missing")
        self.assertEqual([c["name"] for c in r["warnings"]], ["optional tag"])
        self.assertEqual(r["error"], r["summary"])
        self.assertEqual(r["count_failed"], 1)

    def test_shallow_depth_still_gives_summary_and_hint(self):
        p = self._write("t_smoke_shallow.lua", "-- TESTRESULT_SMOKE_FAIL\n")
        r = server.run_lua_test(str(p), depth=1)
        self.assertFalse(r["ok"])
        self.assertIn("recipe parsed", r["report"])
        self.assertIn("hint", r)
        self.assertNotIn("failed_checks", r)

    def test_runtime_error(self):
        p = self._write("t_err.lua", "error('x')\n")
        r = server.run_lua_test(str(p))
        self.assertFalse(r["ok"])
        self.assertIs(r["test_passed"], False)
        self.assertEqual(r["error_kind"], "lua")
        self.assertEqual(r["detail"]["file"], "t_err.lua")

    def test_missing_file(self):
        r = server.run_lua_test("does/not/exist.lua")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "usage")

    def test_resolves_relative_to_tests_dir(self):
        fake_pzlab = types.SimpleNamespace(LAB_ROOT=self.tmp, MODS_DIR=self.mods,
                                           log_path=lambda: str(self.log), http_base=lambda: self.fake.base)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "tests" / "rel.lua").write_text("-- TESTRESULT_PASS\n", encoding="utf-8")
        with mock.patch.object(server, "pzlab", fake_pzlab):
            r = server.run_lua_test("rel.lua", check_log=False)
        self.assertTrue(r["ok"], r)


class TestMods(BaseCase):
    def test_scaffold_and_list(self):
        r = server.scaffold_mod("TestMod", "Test Mod", "uma descrição\ncom quebra")
        self.assertTrue(r["ok"], r)
        root = self.mods / "TestMod"
        info = (root / "common" / "mod.info").read_text(encoding="utf-8")
        self.assertIn("id=TestMod", info)
        self.assertIn("name=Test Mod", info)
        self.assertIn("description=uma descrição com quebra", info)
        self.assertIn("versionMin=42.21", info)
        for d in ("client", "server", "shared"):
            self.assertTrue((root / "42" / "media" / "lua" / d).is_dir())
        self.assertTrue((root / "42" / "media" / "scripts").is_dir())
        self.assertTrue((root / "42" / "media" / "lua" / "shared" / "Translate" / "EN").is_dir())
        self.assertTrue((root / "42" / "media" / "lua" / "server" / "TestMod_Main.lua").is_file())

        lst = server.list_dev_mods()
        self.assertTrue(lst["ok"])
        m = [x for x in lst["mods"] if x["id"] == "TestMod"][0]
        self.assertEqual((m["name"], m["versionMin"]), ("Test Mod", "42.21"))
        self.assertNotIn("warnings", m)

    def test_scaffold_refuses_overwrite_and_bad_ids(self):
        self.assertTrue(server.scaffold_mod("Once", "Once")["ok"])
        marker = self.mods / "Once" / "common" / "mod.info"
        before = marker.read_text(encoding="utf-8")
        r = server.scaffold_mod("Once", "Changed")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_kind"], "exists")
        self.assertEqual(marker.read_text(encoding="utf-8"), before)
        for bad in ("../evil", "a b", "", "x/y", "..", "a\\b"):
            self.assertFalse(server.scaffold_mod(bad, "n")["ok"], bad)
        self.assertFalse((self.tmp / "evil").exists())

    def test_list_dev_mods_warnings_and_fallback_layout(self):
        legacy = self.mods / "LegacyMod"
        (legacy / "42").mkdir(parents=True)
        (legacy / "42" / "mod.info").write_text("name=Legacy\nid=Other\nversionMin=42.21\n", encoding="utf-8")
        m = [x for x in server.list_dev_mods()["mods"] if x["dir"] == "LegacyMod"][0]
        self.assertEqual(m["id"], "Other")
        self.assertEqual(m["versionMin"], "42.21")
        self.assertEqual(len(m["warnings"]), 2)

    def test_list_without_dir(self):
        with mock.patch.dict(os.environ, {server.ENV_MODS_DIR: str(self.tmp / "none")}):
            r = server.list_dev_mods()
        self.assertTrue(r["ok"])
        self.assertEqual(r["mods"], [])


REAL_FORMAT = textwrap.dedent("""    [ZB] [!] class x.PreMain: error invoking premain(): java.lang.reflect.InvocationTargetException
    LOG  : General      f:0 st:303.971.099> [ZB] Watches transformer installed (experimental)
    ERROR: General      f:0 st:303.972.321> NetChecksum$Checksummer.addFile> Exception thrown
    	java.lang.NullPointerException at Objects.requireNonNull(null:-1). Message: absPath:null
    	Stack trace:
    		zombie.scripting.ScriptManager.Load(ScriptManager.java:1526)
    ERROR: General      f:0 st:303.972.941 at FluidContainerScript.load           > Sanitizing container name 'Fuel Pump', name may not contain whitespaces.
    ERROR: General      f:0 st:303.990.000 at ItemScript.load      > Unknown property 'Foo' in item MyMod.Bar
    WARN : Script       f:0 st:303.973.921 at ModelScript.check    > no such model "null" for Base.BareHands
    """)


class TestRealFormat(unittest.TestCase):
    def test_default_noise_filter_and_zb_errors(self):
        r = server.analyze_log(REAL_FORMAT, default_noise_filter=True)
        msgs = [g["message"] for g in r["groups"]]
        self.assertEqual(len(msgs), 2, msgs)
        self.assertTrue(msgs[0].startswith("[ZB] [!]"))
        self.assertIn("Unknown property", msgs[1])
        self.assertEqual(sum(r["ignored_noise"].values()), 2)
        r = server.analyze_log(REAL_FORMAT, default_noise_filter=False)
        self.assertEqual(len(r["groups"]), 4)
        npe = [g for g in r["groups"] if "Exception thrown" in g["message"] or "NullPointer" in g["message"]][0]
        self.assertEqual(npe["category"], "java")   # ScriptManager só aparece no stack, não vira "script"


class TestAnalyzeUnit(unittest.TestCase):
    def test_location_extraction_variants(self):
        locs = server._extract_locations(
            "at media/lua/client/Foo.lua:45\n"
            "Bar.lua line:9\n"
            r"C:\x\mods\Zed\42\media\lua\server\Z.lua:7" "\n")
        pairs = {(l["file"].replace("\\", "/").split("/")[-1], l["line"]) for l in locs}
        self.assertEqual(pairs, {("Foo.lua", 45), ("Bar.lua", 9), ("Z.lua", 7)})
        self.assertTrue(any(l.get("mod") == "Zed" for l in locs))

    def test_builtin_tools_registered(self):
        names = set()
        import asyncio
        tools = asyncio.run(server.mcp.list_tools())
        if hasattr(tools, "tools"):
            tools = tools.tools
        names = {t.name for t in tools}
        self.assertTrue({"lab_start", "lab_stop", "lab_restart", "lab_status", "lua_exec", "lua_inspect",
                         "log_tail", "lua_errors", "reload_lua", "run_lua_test", "list_dev_mods",
                         "scaffold_mod"} <= names, names)


try:
    import lupa  # type: ignore
    HAVE_LUPA = True
except Exception:  # pragma: no cover
    HAVE_LUPA = False


@unittest.skipUnless(HAVE_LUPA, "lupa não instalado: snippets Lua não executados")
class TestLuaSnippetsRealLua(unittest.TestCase):
    """Executa os snippets Lua gerados (inspect/reload) em um Lua 5.x real com stubs das APIs do PZ."""

    def _runtime(self):
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        return lua

    def test_reload_snippet(self):
        lua = self._runtime()
        lua.execute("""
            reloaded = {}
            _loaded = {"C:/Z/mods/known/42/media/lua/server/Known_Main.lua",
                       "C:/Z/mods/a/42/media/lua/shared/Dup.lua", "C:/Z/mods/b/42/media/lua/shared/Dup.lua"}
            function getLoadedLuaCount() return #_loaded end
            function getLoadedLua(i) return _loaded[i + 1] end
            function reloadLuaFile(p) table.insert(reloaded, p) end
        """)
        def run(path, fallback=""):
            wants = server._reload_wants(path)
            code = (server._RELOAD_LUA.replace("{WANTS}", "{" + ", ".join(server._lua_str(w) for w in wants) + "}")
                    .replace("{FALLBACK}", server._lua_str(fallback)))
            return lua.execute("return (function()\n" + code + "\nend)()")
        res = run("media/lua/server/Known_Main.lua")
        self.assertEqual(res["status"], "reloaded")
        self.assertTrue(res["loaded_before"])
        res = run(r"D:\x\mods\known\42\media\lua\server\KNOWN_main.lua")
        self.assertEqual(res["status"], "reloaded")
        self.assertEqual(run("Dup.lua")["status"], "ambiguous")
        self.assertEqual(run("nada.lua")["status"], "not_found")
        self.assertEqual(run("nada.lua", "C:/abs/nada.lua")["status"], "reloaded")
        self.assertEqual(lua.eval("#reloaded"), 3)
        lua.execute("saved = reloadLuaFile; reloadLuaFile = nil")
        self.assertEqual(run("media/lua/server/Known_Main.lua")["status"], "api_missing")

    def test_inspect_snippet(self):
        lua = self._runtime()
        lua.execute("""
            function zbinspect(o, priv) return {type="java.Fake", fields={a=1}, methods={"int m()"}} end
            function zbmethod(f) return {kind="lua"} end
            SandboxVars = {Zombies = 3, Name = "x", nested = {}}
        """)
        def run(expr, private=False):
            code = (server._INSPECT_LUA.replace("{PRIVATE}", "true" if private else "false")
                    .replace("{EXPR}", expr))
            return lua.execute("return (function()\n" + code + "\nend)()")
        t = run("SandboxVars")
        self.assertEqual(t["lua_type"], "table")
        keys = [t["entries"][i]["key"] for i in range(1, 4)]
        self.assertEqual(keys, ["Name", "Zombies", "nested"])
        self.assertEqual(run("nil")["lua_type"], "nil")
        self.assertEqual(run("42")["value"], 42)
        self.assertEqual(run("function() end")["callable"]["kind"], "lua")
        lua.execute("""JO = setmetatable({}, {__index = function() end})""")
        self.assertEqual(run("SandboxVars.Zombies + 1")["value"], 4)
        # expressão com comentário no fim não deve quebrar o parêntese
        self.assertEqual(run("SandboxVars.Zombies -- comentário")["value"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
