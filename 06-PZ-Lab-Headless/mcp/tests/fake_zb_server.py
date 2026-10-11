"""
Servidor HTTP falso que imita a API experimental do ZombieBuddy (HttpServer.java).

Endpoints (conforme o código Java):
  GET  /            texto de ajuda
  GET  /status      "ok\\n"
  GET  /version     "ZombieBuddy vX\\n"
  GET  /log?lines=N últimas N linhas (texto puro)
  POST /lua?chunkname=&depth=&sandbox=&thread=  corpo = Lua; 200 JSON | 500 JSON de erro | 400 | 405

Não executa Lua de verdade: reconhece "gatilhos" no código (ver _handle_lua). Serve para testar o
encanamento do servidor MCP (parâmetros, headers, parsing de erro, timeouts), não a semântica Lua.
Uso: ``python fake_zb_server.py [porta]`` para subir à mão.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_LOADED_LUA = [
    "C:/Zomboid/mods/known/42/media/lua/server/Known_Main.lua",
    "C:/Zomboid/mods/known/42/media/lua/shared/Dup.lua",
    "C:/Zomboid/mods/other/42/media/lua/shared/Dup.lua",
    "C:/Game/media/lua/server/vanilla.lua",
    "C:/Zomboid/mods/known/42/media/lua/server/BROKEN_reload.lua",
]


def _safe_eval(expr: str):
    """Avalia aritmética simples; levanta ValueError se não for."""
    tree = ast.parse(expr, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.USub, ast.Mod, ast.Pow)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError("not arithmetic")
    return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, {})


def limit_depth(obj, depth: int, _level: int = 0):
    """Imita LuaJson.toJson(value, maxDepth): tabelas além de `depth` viram "[table]"."""
    if isinstance(obj, (dict, list)):
        if _level >= depth:
            return "[table]"
        if isinstance(obj, dict):
            return {k: limit_depth(v, depth, _level + 1) for k, v in obj.items()}
        return [limit_depth(v, depth, _level + 1) for v in obj]
    return obj


def smoke_result(hard_fail: bool) -> dict:
    checks = [
        {"name": "item exists", "ok": True, "soft": False, "detail": ""},
        {"name": "recipe parsed", "ok": not hard_fail, "soft": False, "detail": "recipe missing" if hard_fail else ""},
        {"name": "optional tag", "ok": False, "soft": True, "detail": "tag absent"},
    ]
    failed = 1 if hard_fail else 0
    return {"ok": not hard_fail, "test": "smoke_zblabtest", "total": 3, "passed": 2 - failed,
            "failed": failed, "softFailed": 1,
            "summary": f"smoke_zblabtest: {2 - failed}/3 passed, {failed} failed, 1 soft",
            "report": "[OK] item exists\n[FAIL] recipe parsed\n[SOFT] optional tag\n",
            "checks": checks}


class FakeZB:
    def __init__(self, port: int = 0):
        self.requests: list[dict] = []
        self.console_log = "".join(f"LOG  : General     f:0, t:{1700000000000 + i}> console line {i}\n"
                                   for i in range(1, 51))
        self.loaded_lua = list(DEFAULT_LOADED_LUA)
        self.reload_calls: list[str] = []
        self.reload_api_missing = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # silêncio
                pass

            def _send(self, code: int, text: str, ctype: str = "text/plain; charset=UTF-8"):
                data = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _json(self, code: int, obj):
                self._send(code, json.dumps(obj) if not isinstance(obj, str) else obj,
                           "application/json; charset=UTF-8")

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                fake.requests.append({"method": "GET", "path": u.path, "query": q, "headers": dict(self.headers), "body": ""})
                if u.path == "/":
                    self._send(200, "ZombieBuddy HTTP Server\n\nEndpoints:\n  /status\n  /version\n  /lua\n  /log\n")
                elif u.path == "/status":
                    self._send(200, "ok\n")
                elif u.path == "/version":
                    self._send(200, "ZombieBuddy v0-fake\n")
                elif u.path == "/log":
                    n = int(q.get("lines", ["100"])[0])
                    lines = fake.console_log.splitlines()[-n:]
                    self._send(200, "\n".join(lines) + "\n")
                elif u.path == "/lua":
                    self._send(405, "Method not allowed. Use POST.\n")
                else:
                    self._send(404, "not found\n")

            def do_POST(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode("utf-8") if n else ""
                fake.requests.append({"method": "POST", "path": u.path, "query": q,
                                      "headers": dict(self.headers), "body": body})
                if u.path != "/lua":
                    self._send(404, "not found\n")
                    return
                if not body:
                    self._send(400, "Empty request body\n")
                    return
                fake._handle_lua(self, q, body)

        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):  # clientes que desistem (timeout) são esperados
                pass

        self.httpd = QuietServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    # ----------------------------------------------------------------- #
    def start(self) -> "FakeZB":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def last_lua(self) -> dict:
        return [r for r in self.requests if r["path"] == "/lua"][-1]

    # ----------------------------------------------------------------- #
    @staticmethod
    def _lua_runtime_error(msg: str) -> dict:
        return {"err_code": 1, "luaReturn": {
            "errorString": msg,
            "luaStackTrace": "function: boom -- file: Known_Main.lua line # 3 | known\n",
            "errorObject": None,
            "javaException": None,
            "kahluaErrors": [msg]}}

    def _handle_lua(self, h, q, body: str) -> None:
        stripped = body.strip()
        chunk = q.get("chunkname", ["http_exec"])[0]

        if "SLEEP" in body:
            time.sleep(2.5)
            return h._json(200, "null")
        if stripped.startswith("return FALLBACK_STMT"):
            return h._json(500, {"err_code": 1, "luaReturn": {
                "errorString": "[string \"http_exec\"]:1: unexpected symbol near 'return'", "kahluaErrors": None}})
        if "FALLBACK_STMT" in body:
            return h._json(200, "null")
        if "SYNTAX_ERR" in body:
            return h._json(500, {"err_code": 1, "luaReturn": {
                "errorString": f"{chunk}:1: '=' expected near 'SYNTAX_ERR'", "kahluaErrors": ["syntax"]}})
        if "error(" in body:
            return h._json(500, self._lua_runtime_error(f"{chunk}:3: boom"))
        if "ATTEMPT_INDEX" in body:
            return h._json(500, self._lua_runtime_error(
                f"{chunk}:7: attempted index: foo of non-table: null"))
        if "JAVAEX" in body:
            return h._json(500, {"err_code": 2, "javaException": {
                "className": "java.lang.NullPointerException", "message": "npe!", "file": "X.java",
                "line": 10, "method": "m", "stackTrace": ["a.B.m(X.java:10)", "a.C.n(Y.java:5)"]},
                "kahluaErrors": None})
        if "TIMEOUT_TASK" in body:
            return h._json(500, {"err_code": 3, "javaException": {
                "className": "java.lang.RuntimeException",
                "message": "Timeout waiting for Lua task execution (1000ms)", "stackTrace": []},
                "kahluaErrors": None})
        if "WITH_GLOBALS" in body:
            return h._json(500, {"err_code": 1, "luaReturn": {
                "errorString": "boom", "luaStackTrace": "", "errorObject": None, "javaException": None,
                "kahluaErrors": None}, "errorGlobals": {"current_test": "t1"}})
        if "-- pz-live:inspect" in body:
            if "JAVAOBJ" in body:
                return h._json(200, {"lua_type": "userdata", "tostring": "zombie.Fake@1",
                                     "java_type": "zombie.Fake",
                                     "fields": {"alpha": 1, "beta": "x", "zombieCount": 7},
                                     "methods": ["int getAlpha()", "void setAlpha(int)", "int getZombieCount()"]})
            return h._json(200, {"lua_type": "table", "entries": [
                {"key": "a", "type": "number", "value": 1}, {"key": "f", "type": "function"}]})

        if "-- pz-live:reload" in body:
            if self.reload_api_missing:
                return h._json(200, {"status": "api_missing"})
            m = re.search(r"local wants = \{(.*?)\}\nlocal fallback = \"(.*?)\"\n", body, re.S)
            wants = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)) if m else []
            fallback = m.group(2) if m else ""
            norm = lambda p: p.replace("\\\\", "/").replace("\\", "/").lower()
            res = {"loaded_count": len(self.loaded_lua)}
            matches: list[str] = []
            for w in wants:
                nw = norm(w)
                for lp in self.loaded_lua:
                    npth = norm(lp)
                    if npth == nw or (len(npth) > len(nw) and npth.endswith("/" + nw)):
                        matches.append(lp)
                if matches:
                    res["matched_by"] = w
                    break
            res["matches"] = matches
            res["loaded_before"] = bool(matches)
            if len(matches) > 1:
                res["status"] = "ambiguous"
                return h._json(200, res)
            target = matches[0] if matches else (fallback or None)
            if target is None:
                res["status"] = "not_found"
                return h._json(200, res)
            res["target"] = target
            if "BROKEN" in target:
                res["status"] = "error"
                res["error"] = "boom while reloading"
            else:
                res["status"] = "reloaded"
                self.reload_calls.append(target)
            return h._json(200, res)

        depth = int(q.get("depth", ["1"])[0])
        if "TESTRESULT_SMOKE_FAIL" in body:
            return h._json(200, limit_depth(smoke_result(True), depth))
        if "TESTRESULT_SMOKE" in body:
            return h._json(200, limit_depth(smoke_result(False), depth))
        if "DEEP" in body:
            return h._json(200, limit_depth({"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}, depth))
        if "TESTRESULT_PASS" in body:
            return h._json(200, {"ok": True, "checks": 3, "failed": 0})
        if "TESTRESULT_FAIL" in body:
            return h._json(200, {"ok": False, "failures": ["expected 1 got 2"]})
        if "TESTRESULT_PLAIN" in body:
            return h._json(200, {"value": 42})

        m = re.fullmatch(r"return\s+(.+?);?", stripped, re.S)
        if m:
            expr = m.group(1)
            try:
                v = _safe_eval(expr)
                if isinstance(v, float) and v == int(v):
                    v = int(v)
                return h._json(200, v)
            except Exception:
                pass
            sm = re.fullmatch(r'"(.*)"', expr)
            if sm:
                return h._json(200, sm.group(1))
            if expr.startswith("{"):
                return h._json(200, {"a": 1, "nested": "[table]"})
        return h._json(200, "null")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8642
    srv = FakeZB(port).start()
    print(f"fake ZombieBuddy API em {srv.base}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
