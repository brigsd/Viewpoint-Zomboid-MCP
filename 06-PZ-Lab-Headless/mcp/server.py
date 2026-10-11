"""
pz-live — servidor MCP do laboratório headless de Project Zomboid
=================================================================
Permite que o Claude teste mods de PZ (Build 42) sem abrir o jogo: sobe um
servidor dedicado com ZombieBuddy (via ``lab/pzlab.py``), executa Lua nele pela
API HTTP experimental do ZombieBuddy (``/lua``, ``/log``, ``/status``), lê o log,
faz hot-reload de arquivos Lua e roda arquivos de teste.

Formato da API HTTP do ZombieBuddy (ver HttpServer.java / LuaHandler.java):

* ``POST /lua?chunkname=X&depth=N&sandbox=true|false&thread=false`` — corpo = código Lua
  (UTF-8). O 1º valor retornado vira JSON (tabelas até ``depth`` níveis; padrão do jogo = 1).
  - 200 -> corpo JSON do valor retornado (``null`` se nada foi retornado).
  - 500 -> ``{"err_code":1,"luaReturn":{errorString,luaStackTrace,errorObject,javaException,kahluaErrors}}``
           ``{"err_code":2|3,"javaException":{className,message,file,line,method,stackTrace},"kahluaErrors":[..]}``
           (3 = timeout esperando a thread Lua; ``errorGlobals`` se pedido pelo header
           ``X-ZombieBuddy-Error-Globals``).
  - 400 corpo vazio / 405 método errado (texto puro).
* ``GET /log?lines=N`` — últimas N linhas do console log (texto puro).
* ``GET /status`` -> ``ok``; ``GET /version`` -> versão do ZombieBuddy.

IMPORTANTE: stdout é o canal do protocolo MCP (stdio) — nunca use print() aqui;
logs de diagnóstico vão para stderr.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Optional

import httpx

import api_index  # consultas ao índice da API (07-PZ-API-Knowledge); mesma pasta que este arquivo

# Compatibilidade entre mcp 2.x (MCPServer) e mcp 1.x (FastMCP) — mesmo estilo do módulo 05
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Caminhos e carregamento (tolerante) do launcher pzlab
# --------------------------------------------------------------------------- #
MODULE_ROOT = Path(__file__).resolve().parent.parent          # 06-PZ-Lab-Headless/
LAB_DIR = MODULE_ROOT / "lab"
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

pzlab = None
PZLAB_ERROR: Optional[str] = None
try:
    import pzlab  # type: ignore
except Exception as _e:  # módulo ausente ou quebrado: o servidor MCP ainda sobe
    pzlab = None
    PZLAB_ERROR = f"{type(_e).__name__}: {_e}"

# Overrides por ambiente (úteis para testes e para apontar para outro lab)
ENV_HTTP_BASE = "PZ_LIVE_HTTP_BASE"
ENV_LOG_FILE = "PZ_LIVE_LOG_FILE"
ENV_MODS_DIR = "PZ_LIVE_MODS_DIR"
ENV_HTTP_TIMEOUT = "PZ_LIVE_HTTP_TIMEOUT"          # segundos, padrão 20
ENV_START_TIMEOUT = "PZ_LIVE_START_TIMEOUT"        # segundos, padrão 300

DEFAULT_HTTP_TIMEOUT_S = float(os.environ.get(ENV_HTTP_TIMEOUT, "35"))  # > lua_task_timeout (30 s) do servidor
DEFAULT_START_TIMEOUT_S = int(os.environ.get(ENV_START_TIMEOUT, "300"))

logging.getLogger("httpx").setLevel(logging.WARNING)  # sem spam de "HTTP Request" no stderr

mcp = FastMCP("pz-live")


def _dbg(msg: str) -> None:
    print(f"[pz-live] {msg}", file=sys.stderr, flush=True)


def mods_dir() -> Path:
    env = os.environ.get(ENV_MODS_DIR)
    if env:
        return Path(env)
    if pzlab is not None and getattr(pzlab, "MODS_DIR", None):
        return Path(pzlab.MODS_DIR)
    return MODULE_ROOT / "mods"


def lab_root() -> Path:
    if pzlab is not None and getattr(pzlab, "LAB_ROOT", None):
        return Path(pzlab.LAB_ROOT)
    return MODULE_ROOT


def _fail(error: str, kind: str = "error", hint: Optional[str] = None, **extra: Any) -> dict:
    out: dict[str, Any] = {"ok": False, "error": error, "error_kind": kind}
    if hint:
        out["hint"] = hint
    out.update(extra)
    return out


def _pzlab_missing() -> dict:
    return _fail(
        f"pzlab (lab/pzlab.py) indisponível: {PZLAB_ERROR or 'módulo não encontrado'}",
        kind="config",
        hint="Verifique se 06-PZ-Lab-Headless/lab/pzlab.py existe e importa sem erros "
             "(python -c \"import sys; sys.path.insert(0,'lab'); import pzlab\").",
    )


def _pzlab_call(name: str, *args: Any, **kwargs: Any) -> dict:
    """Chama pzlab.<name> e normaliza para {"ok":..., ...}."""
    if pzlab is None:
        return _pzlab_missing()
    fn = getattr(pzlab, name, None)
    if fn is None:
        return _fail(f"pzlab não expõe '{name}'", kind="config")
    try:
        res = fn(*args, **kwargs)
    except Exception as e:
        return _fail(
            f"pzlab.{name} falhou: {type(e).__name__}: {e}",
            kind="lab",
            hint="Veja log_tail e lab_status; se o servidor ficou meio-vivo, chame lab_stop e depois lab_start.",
            traceback=traceback.format_exc(limit=6),
        )
    if isinstance(res, dict):
        out = {"ok": True}
        out.update(res)
        return out
    return {"ok": True, "result": res}


# --------------------------------------------------------------------------- #
# HTTP para a API do ZombieBuddy
# --------------------------------------------------------------------------- #
class LabDown(Exception):
    """Servidor inacessível (parado, bootando ou porta errada)."""


class LabTimeout(Exception):
    """O servidor aceitou a conexão mas não respondeu a tempo."""


def http_base() -> str:
    env = os.environ.get(ENV_HTTP_BASE)
    if env:
        return env.rstrip("/")
    if pzlab is not None:
        try:
            return str(pzlab.http_base()).rstrip("/")
        except Exception as e:
            _dbg(f"pzlab.http_base falhou: {e}")
    return "http://127.0.0.1:8642"


def _down_hint() -> str:
    """Hint contextual de acordo com o estado do launcher."""
    if os.environ.get(ENV_HTTP_BASE):
        return f"API HTTP em {http_base()} não responde (override {ENV_HTTP_BASE})."
    if pzlab is None:
        return ("API HTTP do jogo inacessível e o launcher pzlab não carregou "
                f"({PZLAB_ERROR}). Suba o servidor manualmente ou corrija o pzlab.")
    try:
        st = pzlab.status()
    except Exception as e:  # pragma: no cover
        return f"API HTTP inacessível; pzlab.status() falhou ({e})."
    if not st.get("running"):
        return "servidor parado — chame lab_start (opcionalmente com a lista de mods)."
    if not st.get("http_ok"):
        return ("o processo do servidor está vivo mas a API HTTP ainda não responde "
                "(boot em andamento ou ZombieBuddy sem modo experimental). "
                "Aguarde e veja log_tail; se travou, lab_restart.")
    return "a API HTTP respondeu ao status mas falhou nesta chamada; tente novamente."


def _http(method: str, path: str, *, params: Optional[dict] = None, content: Optional[bytes] = None,
          headers: Optional[dict] = None, timeout_s: Optional[float] = None) -> httpx.Response:
    t = timeout_s if timeout_s is not None else DEFAULT_HTTP_TIMEOUT_S
    timeout = httpx.Timeout(connect=3.0, read=t, write=10.0, pool=3.0)
    url = http_base() + path
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            return client.request(method, url, params=params, content=content, headers=headers)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise LabDown(str(e)) from e
    except httpx.TimeoutException as e:
        raise LabTimeout(str(e)) from e
    except httpx.TransportError as e:  # reset de conexão etc. durante boot/shutdown
        raise LabDown(f"{type(e).__name__}: {e}") from e


_LOC_COLON = re.compile(r"(?P<file>(?:[A-Za-z]:)?[^\s:()\"'<>|]+?):(?P<line>\d+)")


def _structure_error(status_code: int, text: str) -> dict:
    """Converte o corpo de erro do /lua (HTTP != 200) em {error, error_kind, detail, hint}."""
    try:
        payload = json.loads(text)
    except Exception:
        payload = None

    if not isinstance(payload, dict) or "err_code" not in payload:
        msg = text.strip() or f"HTTP {status_code}"
        return _fail(msg, kind="http", http_status=status_code)

    code = payload.get("err_code")
    lr = payload.get("luaReturn") if isinstance(payload.get("luaReturn"), dict) else None
    je = payload.get("javaException") if isinstance(payload.get("javaException"), dict) else None
    kahlua = (lr or {}).get("kahluaErrors") or payload.get("kahluaErrors")
    detail: dict[str, Any] = {"err_code": code}
    kind = "lua"
    message = ""
    stack = None
    from_protected_call = False

    if lr is not None:
        message = lr.get("errorString") or lr.get("errorObject") or ""
        stack = lr.get("luaStackTrace")
        from_protected_call = "luaStackTrace" in lr
        if isinstance(lr.get("javaException"), dict):
            detail["java_exception"] = lr["javaException"]
            if not message:
                message = lr["javaException"].get("message", "")
        if not from_protected_call:
            kind = "compile"  # KahluaException fora do protectedCall = erro de sintaxe/compilação
    elif je is not None:
        kind = "java"
        message = je.get("message") or je.get("className") or ""
        stack = "\n".join(je.get("stackTrace") or []) or None
        detail["java_exception"] = je
        if code == 3 or "Timeout waiting for Lua task" in message:
            kind = "timeout"

    detail["message"] = message
    if stack:
        detail["stack"] = stack
    if kahlua:
        detail["kahlua_errors"] = kahlua
    if payload.get("errorGlobals"):
        detail["error_globals"] = payload["errorGlobals"]

    m = _LOC_COLON.search(message or "")
    if m:
        detail["file"], detail["line"] = m.group("file"), int(m.group("line"))

    low = (message or "").lower()
    hint = None
    if kind == "timeout":
        hint = ("O servidor não executou a tarefa Lua a tempo: provavelmente ainda está carregando o mundo "
                "(a fila só é drenada no tick do servidor), ou lua_task_timeout (zombiebuddy.lua_task_timeout_ms "
                "em lab/lab.json) é menor que o tempo do script. ATENÇÃO: a tarefa continua na fila e pode "
                "executar depois.")
    elif kind == "compile":
        hint = "Erro de sintaxe/compilação do chunk Lua (nada foi executado). Corrija o código."
    elif "attempted index" in low or "non-table" in low:
        hint = "Acesso a campo de nil/não-tabela: verifique se o global/mod já foi carregado e a ordem de require."
    elif "tried to call nil" in low or "attempt to call" in low:
        hint = "Chamada de função inexistente (nil): confira o nome, ':' vs '.', e o lado (client/server)."

    out = _fail(message or f"HTTP {status_code} err_code={code}", kind=kind, detail=detail,
                http_status=status_code)
    if hint:
        out["hint"] = hint
    out["_compile_like"] = (kind == "compile") or (kind == "java" and code == 2)
    return out


def _lua_post(code: str, *, chunkname: str = "pz_live", depth: int = 4, sandbox: bool = True,
              timeout_ms: Optional[int] = None, error_globals: Optional[list[str]] = None) -> dict:
    """POST /lua. Retorna {"ok":True,"result":<py>,"raw":<texto>} ou dict de erro estruturado."""
    if not code or not code.strip():
        return _fail("código Lua vazio", kind="usage")
    timeout_s = (timeout_ms / 1000.0) if timeout_ms else DEFAULT_HTTP_TIMEOUT_S
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if error_globals:
        headers["X-ZombieBuddy-Error-Globals"] = ",".join(error_globals)
    params = {"chunkname": chunkname, "depth": int(depth), "sandbox": "true" if sandbox else "false"}
    t0 = time.time()
    try:
        resp = _http("POST", "/lua", params=params, content=code.encode("utf-8"),
                     headers=headers, timeout_s=timeout_s)
    except LabDown as e:
        return _fail(f"servidor inacessível: {e}", kind="server_down", hint=_down_hint())
    except LabTimeout:
        return _fail(f"sem resposta do /lua em {timeout_s:.0f}s", kind="timeout",
                     hint="Aumente timeout_ms. Se o script é longo, lembre que o servidor também tem "
                          "lua_task_timeout próprio; o servidor pode estar travado (veja log_tail).")
    elapsed = int((time.time() - t0) * 1000)
    text = resp.content.decode("utf-8", "replace")
    if resp.status_code != 200:
        err = _structure_error(resp.status_code, text)
        err["elapsed_ms"] = elapsed
        return err
    try:
        value = json.loads(text) if text.strip() else None
    except Exception:
        value = text  # resposta não-JSON: devolve crua
    return {"ok": True, "result": value, "raw": text, "elapsed_ms": elapsed}


def _strip_internal(res: dict) -> dict:
    res.pop("_compile_like", None)
    return res


# --------------------------------------------------------------------------- #
# Log
# --------------------------------------------------------------------------- #
MAX_LOG_BYTES = 12 * 1024 * 1024


def _log_file() -> Optional[Path]:
    env = os.environ.get(ENV_LOG_FILE)
    p: Optional[str] = env
    if not p and pzlab is not None:
        try:
            p = pzlab.log_path()
        except Exception as e:
            _dbg(f"pzlab.log_path falhou: {e}")
    if not p:
        return None
    path = Path(p)
    # latest.log pode ser um "ponteiro de texto" quando o hardlink falhou (ver pzlab)
    try:
        if path.is_file() and path.stat().st_size < 1024:
            first = path.read_text(encoding="utf-8", errors="replace").strip()
            if first and "\n" not in first and Path(first).is_file():
                return Path(first)
    except OSError:
        pass
    return path


def _read_file_tail(path: Path, max_bytes: int = MAX_LOG_BYTES) -> str:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        data = f.read()
    return data.decode("utf-8", errors="replace")


def _file_size(path: Optional[Path]) -> int:
    try:
        return path.stat().st_size if path else 0
    except OSError:
        return 0


def _read_file_from(path: Path, offset: int) -> str:
    with open(path, "rb") as f:
        f.seek(max(0, offset))
        return f.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")


def _fetch_console_log(lines: int) -> tuple[Optional[str], Optional[str]]:
    """GET /log?lines=N. Retorna (texto, erro)."""
    try:
        resp = _http("GET", "/log", params={"lines": int(lines)}, timeout_s=15)
    except (LabDown, LabTimeout) as e:
        return None, str(e)
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text.strip()[:200]}"
    return resp.content.decode("utf-8", "replace"), None


def _get_log_text(source: str = "auto", console_lines: int = 20000) -> tuple[str, dict]:
    """Devolve (texto, meta). source: auto|file|console. auto = arquivo do launcher; /log se vazio."""
    meta: dict[str, Any] = {}
    text = ""
    if source in ("auto", "file"):
        path = _log_file()
        meta["path"] = str(path) if path else None
        if path and path.is_file():
            text = _read_file_tail(path)
            meta["source"] = "file"
        if text.strip() or source == "file":
            if not text.strip():
                meta.setdefault("source", "file")
            return text, meta
    t, err = _fetch_console_log(console_lines)
    if t is not None:
        meta["source"] = "console(/log)"
        return t, meta
    meta["source"] = meta.get("source") or "none"
    meta["console_error"] = err
    return text, meta


@mcp.tool()
def log_tail(lines: int = 100, grep: Optional[str] = None, source: str = "auto",
             regex: bool = False, case_sensitive: bool = False) -> dict:
    """Últimas linhas do log do servidor PZ (stdout capturado pelo launcher; cai para o endpoint /log).

    Args:
        lines: quantas linhas devolver (as mais recentes; padrão 100, máx 5000).
        grep: se informado, devolve só as linhas que contêm esse texto (ou regex se regex=True),
              pegando as últimas `lines` correspondências.
        source: "auto" (arquivo do launcher; se vazio/ausente usa /log), "file" ou "console" (só /log,
                que lê o server-console.txt do jogo).
        regex: trata `grep` como expressão regular.
        case_sensitive: padrão False (case-insensitive).
    Retorna {ok, source, path, count, text}. Use `lua_errors` para uma visão agrupada dos erros.
    """
    lines = max(1, min(int(lines), 5000))
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pat = re.compile(grep if regex else re.escape(grep), flags) if grep else None
    except re.error as e:
        return _fail(f"regex inválida: {e}", kind="usage")

    if source == "console":
        text, err = _fetch_console_log(5000 if pat else lines)
        if text is None:
            return _fail(f"/log indisponível: {err}", kind="server_down", hint=_down_hint())
        meta: dict[str, Any] = {"source": "console(/log)", "path": None}
    else:
        text, meta = _get_log_text(source, console_lines=5000 if pat else lines)
        if not text and meta.get("source") == "none":
            return _fail("nenhum log disponível", kind="server_down",
                         hint=_down_hint() + " (nem o arquivo de log do launcher nem /log responderam)",
                         **{k: v for k, v in meta.items() if k != "source"})
    all_lines = text.splitlines()
    if pat:
        all_lines = [ln for ln in all_lines if pat.search(ln)]
    out_lines = all_lines[-lines:]
    body = "\n".join(out_lines)
    if len(body) > 200_000:
        body = body[-200_000:]
    return {"ok": True, "source": meta.get("source"), "path": meta.get("path"),
            "count": len(out_lines), "text": body}


# --------------------------------------------------------------------------- #
# Análise de erros do log
# --------------------------------------------------------------------------- #
LEVEL_RE = re.compile(r"^(?:\[[^\]]*\]\s*)?(LOG|ERROR|WARN|DEBUG|TRACE|INFO)\s*:", re.I)
ZB_ERR_RE = re.compile(r"^\[ZB\]\s*\[!\]")  # linhas de erro do próprio ZombieBuddy (sem prefixo de nível)

# Ruído conhecido do jogo vanilla / do lab que não indica bug no mod (desligável: default_noise_filter=False)
DEFAULT_NOISE = [
    r"Sanitizing container name",
    r"NetChecksum\$Checksummer\.addFile",
    r"AdvancedAnimator\$1\.visitFileFailed",
    # Boot do ZombieBuddy no Windows: premain experimental falha no sinal INFO (contornado pelo agente do lab)
    r"experimental\.PreMain: error invoking premain",
    r"is annotated with @LuaClass but is not in the exact package",
    # Mod sem pastas de animação: o jogo procura AnimSets/actiongroups em todo mod
    r"NoSuchFileException: .*[\\/]media[\\/](?:AnimSets|actiongroups)",
]
PREFIX_RE = re.compile(r"^(?:\[[^\]]*\]\s*)?(?:LOG|ERROR|WARN|DEBUG|TRACE|INFO)\s*:\s*[^>]*?>\s*(?:\d+>\s*)?", re.I)
TIMESTAMP_RE = re.compile(r"\b[ft]:\d+\b,?\s*")
STRONG_RE = re.compile(
    r"(?-i:STACK TRACE)|attempted index|attempted to call|tried to call nil|Exception|Callframe|KahluaException|"
    r"LuaManager[^\n]*(?:error|fail)|Failed to (?:load|parse|run)|Error (?:loading|parsing)|"
    r"ScriptManager[^\n]*(?:error|fail|unknown|invalid)|ScriptParser|stack ?overflow|"
    r"non-table|bad argument|require\(\"[^\"]+\"\) failed",
    re.I)
KEY_LINE_RE = re.compile(
    r"attempted (?:index|to call)|tried to call nil|Exception|failed|error|unknown|invalid|not found|"
    r"non-table|bad argument|cannot|could not|overflow", re.I)
SPECIFIC_RE = re.compile(
    r"attempted (?:index|to call)|tried to call nil|non-table|bad argument|[\w.$]+(?:Exception|Error)(?::| at) \S|"
    r"require\(\"[^\"]+\"\) failed|Failed to (?:load|parse|run)", re.I)
SCRIPT_RE = re.compile(
    r"ScriptManager|ScriptParser|ScriptModule|[\\/]scripts[\\/][^\s]*\.txt|"
    r"unknown (?:script )?(?:property|key|tag|type|item|recipe)|error parsing|"
    r"(?:item|recipe|module|fixing|evolvedrecipe|vehicle|sound|model)[^\n]{0,40}(?:not found|unknown|invalid)", re.I)
LUA_RE = re.compile(r"\.lua\b|LuaManager|Kahlua|attempted index|tried to call nil|(?-i:STACK TRACE)|Callframe|"
                    r"non-table|attempted to call|\bLua\b", re.I)
JAVA_RE = re.compile(r"Exception|\bat [\w.$]+\([\w.]+:\d+\)", re.I)

_LOC_PATTERNS = [
    # "function: foo -- file: Foo.lua line # 12 | ModName"
    re.compile(r"(?P<file>(?:[A-Za-z]:)?[^\s:()\"'<>|]*?[\w\-]+\.lua)\s+line\s*#\s*(?P<line>\d+)(?:\s*\|\s*(?P<mod>[^\r\n|]+?))?\s*$", re.I | re.M),
    # "media/lua/client/Foo.lua:12" / "C:\...\Foo.lua:12:"
    re.compile(r"(?P<file>(?:[A-Za-z]:)?[^\s:()\"'<>|]+?\.lua):(?P<line>\d+)", re.I),
    # "Foo.lua line:12" / "Foo.lua, line 12"
    re.compile(r"(?P<file>(?:[A-Za-z]:)?[^\s:()\"'<>|]+?\.lua)[ ,]+line:?\s*(?P<line>\d+)", re.I),
    # scripts: "scripts/foo.txt line 12"
    re.compile(r"(?P<file>(?:[A-Za-z]:)?[^\s:()\"'<>|]+?\.txt)[ ,]+line:?\s*(?P<line>\d+)", re.I),
]
_MOD_FROM_PATH = re.compile(r"[\\/]mods[\\/]([^\\/]+)[\\/]", re.I)


def _extract_locations(text: str, limit: int = 8) -> list[dict]:
    seen: set[tuple[str, int]] = set()
    locs: list[dict] = []
    for pat in _LOC_PATTERNS:
        for m in pat.finditer(text):
            f = m.group("file")
            ln = int(m.group("line"))
            if (f, ln) in seen:
                continue
            seen.add((f, ln))
            loc: dict[str, Any] = {"file": f, "line": ln}
            mod = m.groupdict().get("mod")
            if mod:
                loc["mod"] = mod.strip()
            else:
                mp = _MOD_FROM_PATH.search(f)
                if mp:
                    loc["mod"] = mp.group(1)
            locs.append(loc)
            if len(locs) >= limit:
                return locs
    return locs


def _split_blocks(text: str, max_block_lines: int = 400) -> list[dict]:
    """Agrupa linhas em blocos: um novo bloco começa em cada linha com prefixo de nível."""
    blocks: list[dict] = []
    cur: Optional[dict] = None
    for idx, ln in enumerate(text.splitlines(), start=1):
        m = LEVEL_RE.match(ln)
        if m or ZB_ERR_RE.match(ln):
            cur = {"level": m.group(1).upper() if m else "ERROR", "start": idx, "end": idx, "lines": [ln]}
            blocks.append(cur)
        else:
            if cur is None:
                cur = {"level": None, "start": idx, "end": idx, "lines": [ln]}
                blocks.append(cur)
            elif len(cur["lines"]) < max_block_lines:
                cur["lines"].append(ln)
                cur["end"] = idx
            else:
                cur["end"] = idx
    return blocks


def _normalize_signature(s: str) -> str:
    s = TIMESTAMP_RE.sub("", s)
    s = re.sub(r"@[0-9a-fA-F]+", "@X", s)
    s = re.sub(r"0x[0-9a-fA-F]+", "0xX", s)
    s = re.sub(r"\d+(?:\.\d+)?", "N", s)
    return re.sub(r"\s+", " ", s).strip()


def analyze_log(text: str, include_warnings: bool = False, ignore: Optional[list[str]] = None,
                max_groups: int = 50, default_noise_filter: bool = False) -> dict:
    """Extrai e agrupa erros Lua/script/Java de um texto de log do PZ."""
    ignore_res = [re.compile(p, re.I) for p in (ignore or [])]
    noise_res = [(p, re.compile(p, re.I)) for p in DEFAULT_NOISE] if default_noise_filter else []
    ignored: dict[str, int] = {}
    blocks = _split_blocks(text)
    groups: dict[str, dict] = {}
    total = 0
    for b in blocks:
        btext = "\n".join(b["lines"])
        level = b["level"]
        strong = bool(STRONG_RE.search(btext))
        if level == "ERROR":
            candidate = True
        elif level == "WARN":
            candidate = include_warnings or strong
        else:  # LOG / DEBUG / sem nível (ex.: stack trace de Java)
            candidate = strong
        if not candidate:
            continue
        if any(r.search(btext) for r in ignore_res):
            continue
        noisy = next((p for p, r in noise_res if r.search(btext)), None)
        if noisy:
            ignored[noisy] = ignored.get(noisy, 0) + 1
            continue

        head = "\n".join(b["lines"][:3])  # categoria "script" só pelo cabeçalho (stacks citam ScriptManager.Load)
        if SCRIPT_RE.search(head) or re.search(r"ScriptParser", btext):
            category = "script"
        elif LUA_RE.search(btext):
            category = "lua"
        elif JAVA_RE.search(btext):
            category = "java"
        else:
            category = "other"

        first = b["lines"][0]
        headline = PREFIX_RE.sub("", first).strip() or first.strip()
        key_line = headline
        specific = next((ln.strip() for ln in b["lines"] if SPECIFIC_RE.search(ln)), None)
        if specific:
            key_line = specific
        elif not KEY_LINE_RE.search(headline):
            for ln in b["lines"][1:]:
                if KEY_LINE_RE.search(ln) and not ln.strip().startswith("at "):
                    key_line = ln.strip()
                    break
        message = key_line[:300]
        locs = _extract_locations(btext)
        sig_loc = f"{locs[0]['file']}:{locs[0]['line']}" if locs else ""
        signature = f"{category}|{_normalize_signature(message)}|{sig_loc}"
        total += 1
        g = groups.get(signature)
        if g is None:
            sample = btext if len(btext) <= 2500 else btext[:2500] + "\n... (truncado)"
            g = groups[signature] = {
                "category": category,
                "level": level,
                "message": message,
                "count": 0,
                "first_line": b["start"],
                "last_line": b["start"],
                "locations": locs,
                "mods": sorted({loc["mod"] for loc in locs if loc.get("mod")}),
                "sample": sample,
            }
        g["count"] += 1
        g["last_line"] = b["start"]

    ordered = sorted(groups.values(), key=lambda g: g["first_line"])
    summary: dict[str, int] = {}
    for g in ordered:
        summary[g["category"]] = summary.get(g["category"], 0) + g["count"]
    return {
        "total_events": total,
        "unique_errors": len(ordered),
        "summary": summary,
        "groups": ordered[:max_groups],
        "truncated_groups": max(0, len(ordered) - max_groups),
        "ignored_noise": ignored,
    }


@mcp.tool()
def lua_errors(since_start: bool = True, include_warnings: bool = False,
               ignore: Optional[list[str]] = None, source: str = "auto", max_groups: int = 50,
               default_noise_filter: bool = True) -> dict:
    """Varre o log do servidor atrás de erros Lua / de script / exceções Java, deduplicados e agrupados.

    Detecta "ERROR:", "STACK TRACE", "attempted index", "tried to call nil", "Exception",
    ScriptManager/ScriptParser, falhas de require etc. Cada grupo traz categoria (lua|script|java|other),
    mensagem, contagem, linhas no log, localizações {file,line,mod} quando presentes e uma amostra do
    stack trace.

    Args:
        since_start: True = só o log da execução atual do servidor (o launcher grava um arquivo por start).
            False = inclui também até 5 logs de execuções anteriores (mesma pasta).
        include_warnings: inclui linhas WARN simples (por padrão só WARN que pareçam erro).
        ignore: lista de regex; blocos que casarem são ignorados (ex.: erros esperados de um teste).
        source: "auto" | "file" | "console" (ver log_tail).
        default_noise_filter: True (padrão) descarta ruído vanilla conhecido (ex.: "Sanitizing container
            name", NetChecksum NPE do boot dedicado); a contagem sai em `ignored_noise`. False = tudo.
    """
    text, meta = _get_log_text(source)
    if meta.get("source") == "none":
        return _fail("nenhum log disponível para analisar", kind="server_down", hint=_down_hint(),
                     **{k: v for k, v in meta.items() if k != "source"})
    scanned_files = [meta.get("path")]
    if not since_start and meta.get("source") == "file" and meta.get("path"):
        cur = Path(meta["path"])
        extra = sorted((p for p in cur.parent.glob("*.log")
                        if p.name != "latest.log" and p.resolve() != cur.resolve()),
                       key=lambda p: p.stat().st_mtime)[-5:]
        older = []
        for p in extra:
            try:
                older.append(_read_file_tail(p, 4 * 1024 * 1024))
                scanned_files.insert(0, str(p))
            except OSError:
                pass
        text = "\n".join(older + [text])
    res = analyze_log(text, include_warnings=include_warnings, ignore=ignore, max_groups=max_groups,
                      default_noise_filter=default_noise_filter)
    res.update({"ok": True, "source": meta.get("source"), "log": meta.get("path"),
                "scanned_files": [f for f in scanned_files if f],
                "scanned_lines": text.count("\n") + 1 if text else 0})
    if res["total_events"] == 0:
        res["hint"] = "Nenhum erro encontrado no log analisado."
    return res


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
@mcp.tool()
def lab_start(mods: Optional[list[str]] = None, timeout_s: int = DEFAULT_START_TIMEOUT_S) -> dict:
    """Sobe o servidor dedicado headless de PZ (com ZombieBuddy) e espera ficar pronto.

    Args:
        mods: ids dos mods de desenvolvimento (de list_dev_mods) a ativar; None = todos os de mods/.
        timeout_s: tempo máximo de espera do boot (padrão 300s; o boot real leva de 1 a vários minutos —
            o cliente MCP pode precisar de MCP_TOOL_TIMEOUT alto).
    Retorna {ok, pid, host, port, cachedir, log_file, started_at, mods}.
    """
    res = _pzlab_call("start", mods=mods, timeout_s=int(timeout_s))
    if not res.get("ok"):
        return res
    res.setdefault("hint", "Servidor pronto: use lua_exec / run_lua_test; confira erros com lua_errors.")
    return res


@mcp.tool()
def lab_stop(timeout_s: int = 60) -> dict:
    """Para o servidor dedicado (shutdown gracioso, com kill como fallback)."""
    return _pzlab_call("stop", timeout_s=int(timeout_s))


@mcp.tool()
def lab_restart(mods: Optional[list[str]] = None, timeout_s: int = DEFAULT_START_TIMEOUT_S) -> dict:
    """Reinicia o servidor (necessário após mudar media/scripts, traduções ou Java; Lua usa reload_lua).

    Args:
        mods: ids dos mods a ativar (None = todos de mods/). timeout_s: espera máxima do boot.
    """
    return _pzlab_call("restart", mods=mods, timeout_s=int(timeout_s))


@mcp.tool()
def lab_status() -> dict:
    """Estado do laboratório: processo vivo, porta, saúde da API HTTP, uptime e arquivo de log."""
    if pzlab is None:
        res = _pzlab_missing()
        try:
            r = _http("GET", "/status", timeout_s=3)
            res["http_probe"] = {"url": http_base(), "status": r.status_code, "body": r.text.strip()[:80]}
        except (LabDown, LabTimeout) as e:
            res["http_probe"] = {"url": http_base(), "error": str(e)}
        return res
    res = _pzlab_call("status")
    if res.get("ok"):
        res["http_base"] = http_base()
        if not res.get("running"):
            res["hint"] = "servidor parado — chame lab_start."
        elif not res.get("http_ok"):
            res["hint"] = "processo vivo, API HTTP ainda não responde (bootando?). Acompanhe com log_tail."
    return res


# --------------------------------------------------------------------------- #
# Lua ao vivo
# --------------------------------------------------------------------------- #
_STMT_START = re.compile(r"^\s*(?:return|local|if|for|while|function|do|repeat|break|goto|end|--)\b")
_ASSIGN = re.compile(r"(?<![=~<>])=(?!=)")


def _as_expression(code: str) -> Optional[str]:
    """Se `code` é uma expressão de uma linha, devolve 'return <code>'; senão None."""
    s = code.strip()
    if not s or "\n" in s or _STMT_START.match(s):
        return None
    no_strings = re.sub(r"(\"[^\"]*\"|'[^']*')", "", s)
    if _ASSIGN.search(no_strings):  # atribuição: é statement
        return None
    if s.endswith(";"):
        s = s[:-1]
    return "return " + s


def _exec(code: str, *, chunkname: str, depth: int, sandbox: bool, timeout_ms: Optional[int],
          error_globals: Optional[list[str]], auto_return: bool) -> dict:
    wrapped = _as_expression(code) if auto_return else None
    if wrapped:
        res = _lua_post(wrapped, chunkname=chunkname, depth=depth, sandbox=sandbox,
                        timeout_ms=timeout_ms, error_globals=error_globals)
        if res.get("ok"):
            return _strip_internal(res)
        if not res.get("_compile_like"):
            res["code_sent"] = wrapped  # erro de execução real: não repetir (efeitos colaterais)
            return _strip_internal(res)
        # falhou ao COMPILAR 'return <code>' (nada executou): tenta o código cru
    res = _lua_post(code, chunkname=chunkname, depth=depth, sandbox=sandbox,
                    timeout_ms=timeout_ms, error_globals=error_globals)
    return _strip_internal(res)


@mcp.tool()
def lua_exec(code: str, timeout_ms: Optional[int] = None, depth: int = 5, sandbox: bool = True,
             auto_return: bool = True, chunkname: str = "pz_live_exec",
             error_globals: Optional[list[str]] = None) -> dict:
    """Executa código Lua no servidor PZ em execução (POST /lua do ZombieBuddy) e devolve o resultado.

    O valor do primeiro `return` volta como JSON em `result` (tabelas viram objetos/arrays até `depth`
    níveis; mais fundo vira "[table]"). Uma expressão de uma linha (ex.: `getGameTime():getWorldAgeHours()`)
    recebe `return` automaticamente (auto_return); para blocos multi-linha escreva `return ...` você mesmo.
    Em erro: ok=false com `error` (mensagem), `error_kind` (lua|compile|java|timeout|server_down|http) e
    `detail` {message, stack, file, line, kahlua_errors, java_exception}.

    Notas importantes:
      * O código roda na thread Lua do SERVIDOR (contexto server: sem getPlayer() de cliente/UI).
      * sandbox (padrão True, igual ao /lua do ZombieBuddy): o chunk roda num ambiente próprio cujo
        __index aponta para o ambiente global — globais do mod/jogo são LIDOS normalmente, mas variáveis
        globais que você CRIAR/ATRIBUIR ficam só dentro da sandbox e somem ao fim da chamada. Use
        sandbox=False para gravar no ambiente global real (estado que persiste entre chamadas).
      * print() vai para o LOG do servidor (veja log_tail), não para a resposta; só o 1º `return` volta.
      * Helpers do ZombieBuddy disponíveis: zbinspect, zbmethods, zbfields, zbget, zbcall, zbgrep, zbgreplog...
      * Várias partes podem ser enviadas com marcadores `---FILE:nome.lua---` (todas menos a última
        executam antes; o retorno vem da última).

    Args:
        code: código Lua. timeout_ms: espera máxima da resposta HTTP (padrão 35000; o servidor espera até lua_task_timeout=30000 ms). O limite do lado do
        servidor (lua_task_timeout) é configurado em lab/lab.json. depth: profundidade do JSON do retorno (padrão 5; o padrão do jogo é 1 e troca tabelas aninhadas por "[table]").
        chunkname: nome do chunk que aparece nos erros. error_globals: nomes de globais Lua cujo valor
        é devolvido em detail.error_globals quando há erro.
    """
    depth = max(1, min(int(depth), 12))
    return _exec(code, chunkname=chunkname, depth=depth, sandbox=sandbox,
                 timeout_ms=timeout_ms, error_globals=error_globals, auto_return=auto_return)


def _lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


_INSPECT_LUA = r"""-- pz-live:inspect
local __obj = (
{EXPR}
)
local __private = {PRIVATE}
local out = { lua_type = type(__obj) }
local t = type(__obj)
if __obj == nil then return out end
local okts, ts = pcall(tostring, __obj)
if okts then out.tostring = ts end
if t == "string" or t == "number" or t == "boolean" then
  out.value = __obj
elseif t == "table" then
  local keys = {}
  for k, _ in pairs(__obj) do
    keys[#keys + 1] = k
    if #keys >= 500 then out.truncated = true break end
  end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  local entries = {}
  for i = 1, #keys do
    local k = keys[i]
    local v = __obj[k]
    local tv = type(v)
    local e = { key = tostring(k), type = tv }
    if tv == "string" or tv == "number" or tv == "boolean" then e.value = v end
    entries[#entries + 1] = e
  end
  out.entries = entries
elseif t == "function" then
  if zbmethod then
    local ok, info = pcall(zbmethod, __obj)
    if ok then out.callable = info else out.inspect_error = tostring(info) end
  end
else
  if zbinspect then
    local ok, info = pcall(zbinspect, __obj, __private)
    if ok and info then
      out.java_type = info.type
      out.fields = info.fields
      out.methods = info.methods
      out.element_types = info.element_types
    else
      out.inspect_error = tostring(info)
    end
  else
    out.zb_available = false
  end
end
return out
"""


def _filter_list(items: Any, flt: Optional[str], cap: int) -> tuple[Any, int]:
    if not isinstance(items, list):
        return items, 0
    if flt:
        lf = flt.lower()
        items = [i for i in items if lf in json.dumps(i, ensure_ascii=False).lower()]
    omitted = max(0, len(items) - cap)
    return items[:cap], omitted


@mcp.tool()
def lua_inspect(expr: str, include_private: bool = False, filter: Optional[str] = None,
                max_items: int = 200) -> dict:
    """Inspeciona o valor de uma expressão Lua no servidor (objeto Java, tabela Lua, função, primitivo).

    Para objetos Java usa zbinspect (tipo Java, campos, assinaturas de métodos, element_types);
    para tabelas Lua lista as chaves com o tipo (e o valor, se primitivo); para funções, zbmethod.
    Ex.: expr="getSandboxOptions()", "SandboxVars", "ScriptManager.instance", "Events.OnTick".

    Args:
        expr: expressão Lua (sem 'return'). include_private: inclui campos/métodos privados e herdados.
        filter: texto (case-insensitive) para filtrar campos/métodos/entradas (ex.: "zombie").
        max_items: máximo de itens por lista devolvida (restante é contado em `omitted`).
    """
    if not expr or not expr.strip():
        return _fail("expr vazia", kind="usage")
    code = (_INSPECT_LUA.replace("{PRIVATE}", "true" if include_private else "false")
            .replace("{EXPR}", expr))
    res = _lua_post(code, chunkname="pz_live_inspect", depth=4, sandbox=True)
    res = _strip_internal(res)
    if not res.get("ok"):
        return res
    info = res["result"] if isinstance(res.get("result"), dict) else {"value": res.get("result")}
    omitted: dict[str, int] = {}
    for k in ("methods", "entries", "element_types"):
        if k in info:
            info[k], om = _filter_list(info[k], filter, max_items)
            if om:
                omitted[k] = om
    if isinstance(info.get("fields"), dict):
        flds = info["fields"]
        if filter:
            flds = {k: v for k, v in flds.items() if filter.lower() in (k + json.dumps(v, ensure_ascii=False)).lower()}
        if len(flds) > max_items:
            omitted["fields"] = len(flds) - max_items
            flds = dict(list(flds.items())[:max_items])
        info["fields"] = flds
    out = {"ok": True, "expr": expr, "info": info}
    if omitted:
        out["omitted"] = omitted
    if info.get("zb_available") is False:
        out["hint"] = "zbinspect indisponível: o ZombieBuddy precisa estar em modo experimental."
    return out


# --------------------------------------------------------------------------- #
# Hot-reload e testes
# --------------------------------------------------------------------------- #
_RELOAD_LUA = r"""-- pz-live:reload
if type(reloadLuaFile) ~= "function" then return { status = "api_missing" } end
local wants = {WANTS}
local fallback = {FALLBACK}
local function norm(p)
  p = string.lower(tostring(p))
  p = string.gsub(p, "\\", "/")
  return p
end
local loaded = {}
local okc, n = pcall(getLoadedLuaCount)
if okc and n then
  for i = 0, n - 1 do loaded[#loaded + 1] = getLoadedLua(i) end
end
local res = { loaded_count = #loaded }
local matches = {}
for wi = 1, #wants do
  local want = norm(wants[wi])
  for i = 1, #loaded do
    local np = norm(loaded[i])
    if np == want or (#np > #want and string.sub(np, -#want - 1) == "/" .. want) then
      matches[#matches + 1] = loaded[i]
    end
  end
  if #matches > 0 then res.matched_by = wants[wi] break end
end
res.matches = matches
res.loaded_before = #matches > 0
if #matches > 1 then
  res.status = "ambiguous"
  return res
end
local target = matches[1]
if target == nil and fallback ~= "" then target = fallback end
if target == nil then
  res.status = "not_found"
  return res
end
res.target = target
local ok, err = pcall(reloadLuaFile, target)
if ok then res.status = "reloaded" else res.status = "error" res.error = tostring(err) end
return res
"""


def _norm_slashes(p: str) -> str:
    return p.replace("\\", "/")


def _reload_wants(path: str) -> list[str]:
    p = _norm_slashes(path)
    while p.startswith("./"):
        p = p[2:]
    wants = [p]
    idx = p.lower().rfind("media/")
    if idx > 0:
        wants.append(p[idx:])
    base = p.rsplit("/", 1)[-1]
    if base not in wants:
        wants.append(base)
    # remove duplicatas preservando ordem
    seen, out = set(), []
    for w in wants:
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _resolve_local(path: str, extra_bases: Optional[list[Path]] = None) -> Optional[Path]:
    p = Path(path)
    if p.is_absolute():
        return p if p.exists() else None
    bases = [Path.cwd(), lab_root(), mods_dir(), MODULE_ROOT, MODULE_ROOT.parent] + (extra_bases or [])
    for b in bases:
        cand = (b / p)
        if cand.exists():
            return cand.resolve()
    return None


def _new_errors_since(log: Optional[Path], mark: int, wait_s: float = 0.6) -> dict:
    """Erros surgidos no log depois de `mark` (tamanho do arquivo antes da ação)."""
    time.sleep(wait_s)
    if not log or not log.is_file():
        return {"checked": False, "reason": "arquivo de log indisponível"}
    size = _file_size(log)
    if size < mark:
        mark = 0  # log rotacionado/truncado
    text = _read_file_from(log, mark)
    res = analyze_log(text, max_groups=20)
    return {"checked": True, "total_events": res["total_events"], "groups": res["groups"]}


@mcp.tool()
def reload_lua(path: str, method: str = "auto") -> dict:
    """Hot-reload de UM arquivo Lua no servidor em execução e reporta erros novos no log.

    Por padrão (method="auto") tenta a API da engine `reloadLuaFile` (localiza o arquivo entre os Lua já
    carregados via getLoadedLua, por sufixo do caminho); se ela não existir/falhar e o arquivo existe no
    disco, REEXECUTA o conteúdo local do arquivo como chunk não-sandbox (sandbox=false) no ambiente global.
    `path` pode ser absoluto, relativo ao repo/lab/mods, ou só o sufixo como o jogo conhece
    ("media/lua/server/MeuMod_Main.lua"). Se for ambíguo devolve as candidatas — passe um caminho mais
    específico.

    LIMITAÇÕES (importante):
      * Só arquivos .lua. Qualquer mudança em media/scripts (itens, receitas, veículos, modelos...), em
        traduções ou Java SEMPRE exige lab_restart (scripts são lidos só no boot). O Lua dos mods também só é
        lido no boot pelo carregador normal; se o reload não surtir efeito, use lab_restart (~45 s).
      * Reexecuta o arquivo inteiro: `Events.X.Add(fn)` no topo registra um listener DUPLICADO (a função
        antiga continua ligada). Estruture o mod com guardas (`if not MeuMod then ... end`) ou
        Events.X.Remove antes de Add; para validar de forma limpa use lab_restart.
      * Tabelas/objetos já criados mantêm o comportamento antigo (closures capturadas); só globais/funções
        redefinidas pelo arquivo mudam.
      * Roda no contexto do servidor; arquivos de client/ só carregam se o servidor os carregou.

    Args:
        path: arquivo .lua. method: "auto" (engine, depois reexecução), "engine" (só reloadLuaFile) ou
        "rerun" (só reexecutar o conteúdo local com sandbox=false).
    Retorna {ok, status, method (reloadLuaFile|rerun_content), target, new_errors{groups}}.
    """
    if not path or not path.strip():
        return _fail("path vazio", kind="usage")
    if method not in ("auto", "engine", "rerun"):
        return _fail("method deve ser auto|engine|rerun", kind="usage")
    if not path.lower().endswith(".lua"):
        return _fail("reload_lua só aceita arquivos .lua",
                     kind="usage",
                     hint="Mudanças em media/scripts/*.txt, traduções ou Java exigem lab_restart.")
    local = _resolve_local(path)
    log = _log_file()
    mark = _file_size(log)

    if method == "rerun":
        if local is None:
            return _fail(f"arquivo local não encontrado: {path}", kind="usage",
                         hint="method='rerun' lê o arquivo do disco; passe um caminho existente.")
        return _rerun_content(local, path, log, mark)

    wants = _reload_wants(path)
    fallback = _norm_slashes(str(local)) if local else ""
    code = (_RELOAD_LUA
            .replace("{WANTS}", "{" + ", ".join(_lua_str(w) for w in wants) + "}")
            .replace("{FALLBACK}", _lua_str(fallback)))
    res = _strip_internal(_lua_post(code, chunkname="pz_live_reload", depth=4, sandbox=True))
    if not res.get("ok"):
        return res
    info = res["result"] if isinstance(res.get("result"), dict) else {"raw": res.get("result")}
    status = info.get("status")

    if status in ("api_missing", "error") and method == "auto" and local is not None:
        out = _rerun_content(local, path, log, mark)
        out["engine_attempt"] = {"status": status, "error": info.get("error")}
        return out

    out: dict[str, Any] = {"ok": status == "reloaded", "status": status, "method": "reloadLuaFile",
                           "requested": path, "local_file": str(local) if local else None,
                           **{k: v for k, v in info.items() if k != "status"}}
    if status == "ambiguous":
        out["error"] = "mais de um arquivo Lua carregado casa com o caminho"
        out["error_kind"] = "usage"
        out["hint"] = "Passe um caminho mais específico (inclua a pasta do mod ou client/server/shared)."
        return out
    if status == "not_found":
        out["error"] = "arquivo não está carregado no servidor e não existe localmente"
        out["error_kind"] = "usage"
        out["hint"] = "Confira o caminho; o mod precisa estar ativo (lab_start com o mod)."
        return out
    if status == "api_missing":
        out["error"] = "reloadLuaFile não existe nesta engine/contexto e não há arquivo local para reexecutar"
        out["error_kind"] = "usage"
        out["hint"] = "Passe um caminho existente no disco (reexecução) ou use lab_restart."
        return out
    if status == "error":
        out["error"] = info.get("error", "reloadLuaFile falhou")
        out["error_kind"] = "lua"
    elif not info.get("loaded_before"):
        out["warning"] = ("o arquivo não estava na lista de Lua carregados; foi executado pelo caminho local "
                          "(pode não corresponder ao caminho que o jogo usaria).")
    out["new_errors"] = _new_errors_since(log, mark)
    if out["new_errors"].get("total_events"):
        out["ok"] = False
        out.setdefault("error", f"{out['new_errors']['total_events']} erro(s) novo(s) no log após o reload")
        out.setdefault("error_kind", "lua")
    return out


def _rerun_content(local: Path, requested: str, log: Optional[Path], mark: int) -> dict:
    """Reexecuta o conteúdo do arquivo local como chunk não-sandbox (escreve nos globais reais)."""
    try:
        code = local.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        return _fail(f"não foi possível ler {local}: {e}", kind="usage")
    res = _strip_internal(_lua_post(code, chunkname=local.name, depth=1, sandbox=False))
    out: dict[str, Any] = {"ok": bool(res.get("ok")), "status": "reloaded" if res.get("ok") else "error",
                           "method": "rerun_content", "requested": requested, "local_file": str(local),
                           "note": "conteúdo do arquivo reexecutado com sandbox=false (globais reais)"}
    if not res.get("ok"):
        out.update({k: v for k, v in res.items() if k != "ok"})
        return out
    out["new_errors"] = _new_errors_since(log, mark)
    if out["new_errors"].get("total_events"):
        out["ok"] = False
        out["error"] = f"{out['new_errors']['total_events']} erro(s) novo(s) no log após o reload"
        out["error_kind"] = "lua"
    return out


def _summarize_test(result: Any) -> dict:
    """Interpreta convenções comuns do valor retornado por um teste."""
    info: dict[str, Any] = {"passed": None}
    if isinstance(result, bool):
        info["passed"] = result
    elif isinstance(result, dict):
        if isinstance(result.get("ok"), bool):
            info["passed"] = result["ok"]
        elif isinstance(result.get("passed"), bool):
            info["passed"] = result["passed"]
        elif isinstance(result.get("success"), bool):
            info["passed"] = result["success"]
        elif isinstance(result.get("failed"), (int, float)):
            info["passed"] = result["failed"] == 0
        elif isinstance(result.get("failures"), list):
            info["passed"] = len(result["failures"]) == 0
        for k in ("passed", "failed", "total", "skipped"):
            if isinstance(result.get(k), (int, float)) and not isinstance(result.get(k), bool):
                info[f"count_{k}"] = result[k]
    return info


@mcp.tool()
def run_lua_test(path: str, timeout_ms: int = 60000, depth: int = 6, sandbox: bool = True,
                 check_log: bool = True) -> dict:
    """Executa um arquivo de teste Lua do disco no servidor PZ e devolve o resultado (JSON).

    O arquivo (ex.: 06-PZ-Lab-Headless/tests/test_x.lua, caminho absoluto ou relativo ao lab/repo/tests)
    é lido localmente e enviado ao /lua; o teste deve terminar com `return <tabela>` — o endpoint
    serializa em JSON até `depth` níveis. Convenção reconhecida para `test_passed`: tabela com
    `ok=true|false`, ou `passed=true|false`, ou `failed=<n>` (0 = passou), ou `failures={}` vazia;
    um `return true/false` também vale. Sem convenção, test_passed=null (inspecione `result`).
    Se houver erro de execução, ok=false com `error`/`detail` (mensagem, stack, arquivo:linha).
    Com check_log=True também devolve `new_errors` (erros que surgiram no log durante o teste).

    Args:
        path: arquivo .lua do teste. timeout_ms: espera máxima (o lua_task_timeout do servidor, em
        lab/lab.json, também limita). depth: profundidade do JSON do retorno.
        sandbox: True (padrão) = globais criadas pelo teste não vazam (globais existentes são lidas via __index).
    """
    local = _resolve_local(path, [lab_root() / "tests"])
    if local is None or not local.is_file():
        return _fail(f"arquivo de teste não encontrado: {path}", kind="usage",
                     hint="Use caminho absoluto ou relativo a 06-PZ-Lab-Headless/ (ex.: tests/meu_teste.lua).")
    try:
        code = local.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        return _fail(f"não foi possível ler {local}: {e}", kind="usage")
    log = _log_file()
    mark = _file_size(log)
    res = _strip_internal(_lua_post(code, chunkname=local.name, depth=max(1, min(int(depth), 12)),
                                    sandbox=sandbox, timeout_ms=timeout_ms))
    res["test_file"] = str(local)
    if res.get("ok"):
        result = res.get("result")
        info = _summarize_test(result)
        res["test_passed"] = info["passed"]
        res.update({k: v for k, v in info.items() if k.startswith("count_")})
        res.pop("raw", None)
        if isinstance(result, dict):
            if isinstance(result.get("test"), str):
                res["test_name"] = result["test"]
            if isinstance(result.get("summary"), str):
                res["summary"] = result["summary"]
            if isinstance(result.get("report"), str):
                res["report"] = result["report"]  # texto multi-linha completo, legível mesmo com depth baixo
            checks = result.get("checks")
            if isinstance(checks, list):
                bad = [c for c in checks if isinstance(c, dict) and c.get("ok") is False]
                res["failed_checks"] = [c for c in bad if not c.get("soft")]
                soft = [c for c in bad if c.get("soft")]
                if soft:
                    res["warnings"] = soft  # soft=true: só aviso, não reprova
            elif isinstance(checks, str) and checks.startswith("["):
                res["hint"] = ("`checks` veio truncado (\"[table]\"): aumente depth (>=3) para ver os checks; "
                               "`report`/`summary` continuam completos.")
        if res["test_passed"] is False:
            res["ok"] = False
            res["error_kind"] = "test_failed"
            res["error"] = res.get("summary") or "o teste reportou falha (ver result/failed_checks)"
    else:
        res["test_passed"] = False
    if check_log and res.get("error_kind") != "server_down":
        res["new_errors"] = _new_errors_since(log, mark, wait_s=0.4)
    return res


# --------------------------------------------------------------------------- #
# Mods de desenvolvimento
# --------------------------------------------------------------------------- #
def _parse_mod_info(path: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    except OSError:
        pass
    return info


def _find_mod_info(mod_dir: Path) -> Optional[Path]:
    for rel in ("common/mod.info", "42/mod.info", "mod.info"):
        p = mod_dir / rel
        if p.is_file():
            return p
    for p in sorted(mod_dir.glob("[0-9]*/mod.info")):
        return p
    return None


@mcp.tool()
def list_dev_mods() -> dict:
    """Lista os mods de desenvolvimento em MODS_DIR (06-PZ-Lab-Headless/mods/*): id, nome, versionMin etc.

    Lê common/mod.info (ou 42/mod.info como fallback). Os `id` retornados são os valores válidos para
    lab_start(mods=[...]).
    """
    root = mods_dir()
    if not root.is_dir():
        return {"ok": True, "mods_dir": str(root), "count": 0, "mods": [],
                "hint": "pasta de mods inexistente; use scaffold_mod para criar o primeiro mod."}
    mods = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        mi = _find_mod_info(d)
        info = _parse_mod_info(mi) if mi else {}
        entry: dict[str, Any] = {
            "dir": d.name,
            "id": info.get("id", d.name),
            "name": info.get("name"),
            "versionMin": info.get("versionMin"),
            "versionMax": info.get("versionMax"),
            "require": info.get("require"),
            "description": info.get("description"),
            "path": str(d),
            "mod_info": str(mi) if mi else None,
        }
        warns = []
        if mi is None:
            warns.append("sem mod.info (common/mod.info)")
        elif info.get("id") and info["id"] != d.name:
            warns.append(f"id '{info['id']}' difere do nome da pasta '{d.name}'")
        if not (d / "common").is_dir():
            warns.append("sem pasta common/ (obrigatória no layout B42)")
        if warns:
            entry["warnings"] = warns
        mods.append(entry)
    return {"ok": True, "mods_dir": str(root), "count": len(mods), "mods": mods}


_MOD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def _one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


@mcp.tool()
def scaffold_mod(mod_id: str, name: str, description: str = "", version_min: str = "42.21") -> dict:
    """Cria o esqueleto mínimo de um mod Build 42 em MODS_DIR/<mod_id>/ (recusa sobrescrever).

    Estrutura criada: common/mod.info, 42/media/lua/{client,server,shared}/, 42/media/scripts/,
    42/media/lua/shared/Translate/EN/ e um Lua de exemplo em server/ que imprime "[<mod_id>] loaded"
    no log (útil para confirmar que o mod foi carregado no servidor).

    Args:
        mod_id: identificador (letras, números, '_' e '-'; também é o nome da pasta).
        name: nome exibido. description: texto curto. version_min: versionMin do mod.info (padrão 42.21, a build do lab).
    """
    if not _MOD_ID_RE.match(mod_id or ""):
        return _fail("mod_id inválido: use letras, números, '_' ou '-' (até 64 chars, sem espaços)",
                     kind="usage")
    root = mods_dir()
    target = (root / mod_id)
    try:
        if root.resolve() not in target.resolve().parents:
            return _fail("mod_id resolve para fora de MODS_DIR", kind="usage")
    except OSError as e:
        return _fail(str(e), kind="usage")
    if target.exists():
        return _fail(f"o mod '{mod_id}' já existe em {target} — recusando sobrescrever", kind="exists",
                     hint="Escolha outro mod_id ou edite os arquivos existentes.")
    name = _one_line(name) or mod_id
    description = _one_line(description)
    info = "\n".join([
        f"name={name}",
        f"id={mod_id}",
        f"description={description}",
        "modversion=0.1.0",
        f"versionMin={version_min}",
        "",
    ])
    sample = (
        f'-- {name}: exemplo gerado por scaffold_mod. Roda no servidor ao carregar o mod.\n'
        f'{mod_id.replace("-", "_")} = {mod_id.replace("-", "_")} or {{}}\n'
        f'print("[{mod_id}] loaded")\n'
    )
    translate = "UI_EN = {\n}\n"
    try:
        (target / "common").mkdir(parents=True)
        (target / "common" / "mod.info").write_text(info, encoding="utf-8", newline="\n")
        lua_root = target / "42" / "media" / "lua"
        for sub in ("client", "server", "shared"):
            (lua_root / sub).mkdir(parents=True)
        (target / "42" / "media" / "scripts").mkdir(parents=True)
        tr = lua_root / "shared" / "Translate" / "EN"
        tr.mkdir(parents=True)
        (tr / "UI_EN.txt").write_text(translate, encoding="utf-8", newline="\n")
        (lua_root / "server" / f"{mod_id}_Main.lua").write_text(sample, encoding="utf-8", newline="\n")
        (target / "42" / "media" / "scripts" / ".gitkeep").write_text("", encoding="utf-8")
        (lua_root / "client" / ".gitkeep").write_text("", encoding="utf-8")
        (lua_root / "shared" / ".gitkeep").write_text("", encoding="utf-8")
    except OSError as e:
        return _fail(f"falha ao criar o mod: {e}", kind="io")
    created = sorted(str(p.relative_to(target)).replace("\\", "/")
                     for p in target.rglob("*") if p.is_file())
    return {"ok": True, "mod_id": mod_id, "path": str(target), "files": created,
            "hint": f"Ative com lab_start(mods=['{mod_id}']) (ou lab_restart) e confira '[{mod_id}] loaded' em log_tail."}


# --------------------------------------------------------------------------- #
# Base de conhecimento da API 42.21 (índice SQLite de 07-PZ-API-Knowledge) — lógica em api_index.py
# --------------------------------------------------------------------------- #
def _api_call(fn: Any, *args: Any, **kwargs: Any) -> dict:
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # nunca derrubar o servidor MCP por causa de uma consulta
        return _fail(f"{fn.__name__} falhou: {type(e).__name__}: {e}", kind="index_error",
                     hint="rode python 07-PZ-API-Knowledge/build_index.py para refazer o índice.",
                     traceback=traceback.format_exc(limit=6))


@mcp.tool()
def api_search(query: str, kind: Optional[str] = None, limit: int = 20) -> dict:
    """Busca na API REAL do Project Zomboid 42.21 (funções globais, classes/métodos/campos Java expostos ao Lua, eventos).

    Use ANTES de escrever código Lua de mod: não chute nomes de API. Cada resultado traz name, kind, owner,
    signature, returns e `call`, a forma de chamar no Lua: `Owner.metodo` (estático), `obj:metodo` (instância),
    `nome()` (função global), `Events.Nome` (evento). Nomes exatos vêm primeiro; aceita 'Classe:metodo' ou
    'Classe.metodo'. Sem resultado no FTS, cai para busca LIKE; sem nada, devolve found=false + suggestions.

    Args:
        query: termo (nome parcial ou completo, ex. 'getCraftRecipe', 'ScriptManager:getCraftRecipe').
        kind: filtro opcional — global_function | class | method | field | event | lua_global.
        limit: máximo de resultados (1-200, padrão 20).
    Resposta: results[], count, found, mode ('fts'|'like'), meta.game_version/meta.built_at.
    """
    return _api_call(api_index.api_search, query, kind, limit)


@mcp.tool()
def api_class(name: str, filter: Optional[str] = None, limit: int = 200) -> dict:
    """Mostra uma classe Java exposta ao Lua: java_class e seus métodos e campos (estáticos e de instância separados).

    Aceita o nome curto ('ScriptManager') ou o nome completo ('zombie.scripting.ScriptManager').
    `filter` restringe por substring no nome/assinatura do membro. Classe inexistente → found=false com
    suggestions (e also_found_as quando existe como global definido em Lua, ex. ISInventoryPage).

    Args:
        name: nome da classe. filter: substring opcional. limit: máximo de membros devolvidos (padrão 200).
    Resposta: static_methods, instance_methods, static_fields, instance_fields, total_members, matched, truncated.
    """
    return _api_call(api_index.api_class, name, filter, limit)


@mcp.tool()
def api_event(name: str) -> dict:
    """Diz se o evento `Events.<name>` existe na 42.21, com usos reais do vanilla (arquivo:linha + trecho, até 10)
    e, quando dá para inferir, o padrão de argumentos do callback (`callback.args`, tirado de
    `Events.X.Add(function(a, b)` nos usos). Evento inexistente → exists=false com suggestions.

    Args:
        name: 'OnServerStarted' ou 'Events.OnServerStarted'.
    """
    return _api_call(api_index.api_event, name)


@mcp.tool()
def script_fields(block_type: Optional[str] = None, field: Optional[str] = None) -> dict:
    """Campos válidos dos blocos de script (media/scripts) da 42.21, com contagem de uso e um exemplo real.

    Sem `block_type` lista os tipos existentes (item, craftRecipe, fluid, entity, ...). Com `block_type` lista
    os campos mais usados desse tipo. Com `field` detalha um campo; campos aninhados aparecem como
    `inputs.item` e devolvem as formas reais da linha (example_value). Campo/tipo inexistente → suggestions.

    Args:
        block_type: ex. 'item', 'craftRecipe'. field: ex. 'ItemType', 'UseDelta', 'inputs', 'inputs.item'.
    """
    return _api_call(api_index.script_fields, block_type, field)


@mcp.tool()
def vanilla_examples(symbol: str, limit: int = 10) -> dict:
    """Usos reais de um símbolo no Lua vanilla da 42.21 (arquivo:linha + trecho de código).

    Args:
        symbol: nome ('getCraftRecipe'), qualificado ('ScriptManager:getCraftRecipe') ou evento ('Events.OnTick').
        limit: máximo de exemplos (1-50, padrão 10); prioriza arquivos diferentes.
    Resposta: examples[], total, definitions[] (linhas do índice com esse nome). Sem uso → found=false + suggestions.
    """
    return _api_call(api_index.vanilla_examples, symbol, limit)


@mcp.tool()
def api_exists(name: str, owner: Optional[str] = None) -> dict:
    """Sim/não rápido: esta API existe na 42.21? Use para NÃO chutar (ex. 'Languages.instance', 'Translator.loadFiles').

    Aceita 'nome', 'Classe.nome', 'Classe:nome' ou 'Events.Nome'; `owner` restringe à classe. Devolve exists,
    matches[] (com a forma de chamada), e se não existe: suggestions, case_mismatch (o Lua diferencia
    maiúsculas) e se a própria classe existe (owner_exists).

    Args:
        name: símbolo. owner: classe dona (opcional).
    """
    return _api_call(api_index.api_exists, name, owner)


if __name__ == "__main__":
    if PZLAB_ERROR:
        _dbg(f"AVISO: pzlab não carregou ({PZLAB_ERROR}); lab_* retornarão erro até corrigir.")
    mcp.run()
