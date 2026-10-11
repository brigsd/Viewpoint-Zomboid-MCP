"""Extrator do Lua vanilla: usos (arquivo:linha), eventos e globais definidas.

Le <game>/media/lua/**/*.lua (shared, client, server) sem gravar nada na pasta
do jogo e preenche as tabelas `usages` e `symbols` (kind='event' e 'lua_global').
Usa regex e um tokenizador simples (comentarios e strings), sem parser Lua.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MAX_SNIPPET = 200

# ---------------------------------------------------------------- lexer simples
_LEX = re.compile(
    r"""
    (?P<lcom>--\[(?P<lc>=*)\[.*?\](?P=lc)\])      # comentario longo
  | (?P<com>--[^\n]*)                              # comentario de linha
  | (?P<lstr>\[(?P<ls>=*)\[.*?\](?P=ls)\])         # string longa
  | (?P<str>"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?)
    """,
    re.S | re.X,
)
_NOT_NL = re.compile(r"[^\n]")


def _blank(text: str) -> str:
    return _NOT_NL.sub(" ", text)


def strip_lua(src: str) -> tuple[str, str]:
    """Devolve (sem_comentarios, sem_comentarios_nem_strings).

    Ambos preservam o numero de caracteres e de linhas do original. Em
    `sem_comentarios_nem_strings` o conteudo das strings vira espacos (as
    aspas ficam), o que evita falsos positivos de regex dentro de textos.
    """
    nc: list[str] = []
    ns: list[str] = []
    pos = 0
    for m in _LEX.finditer(src):
        s, e = m.span()
        if s > pos:
            chunk = src[pos:s]
            nc.append(chunk)
            ns.append(chunk)
        text = m.group(0)
        kind = m.lastgroup
        if m.group("lcom") is not None or m.group("com") is not None:
            b = _blank(text)
            nc.append(b)
            ns.append(b)
        elif m.group("lstr") is not None:
            nc.append(text)
            ns.append(_blank(text))
        else:  # string comum
            nc.append(text)
            q = text[0]
            inner = _blank(text[1:-1]) if len(text) >= 2 and text[-1] == q else _blank(text[1:])
            ns.append(q + inner + (q if len(text) >= 2 and text[-1] == q else ""))
        pos = e
    if pos < len(src):
        nc.append(src[pos:])
        ns.append(src[pos:])
    return "".join(nc), "".join(ns)


# ------------------------------------------------------------------- regexes
KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "goto", "if", "in", "local", "nil", "not", "or", "repeat", "return", "then",
    "true", "until", "while",
}
# builtins/stdlib do Lua: nao sao API do PZ, so fariam ruido
LUA_BUILTINS = {
    "ipairs", "pairs", "tostring", "tonumber", "type", "select", "pcall", "xpcall",
    "error", "assert", "unpack", "setmetatable", "getmetatable", "rawget", "rawset",
    "rawequal", "next", "print", "loadstring", "load", "collectgarbage", "dofile",
}
STDLIB_OWNERS = {"table", "string", "math", "os", "io", "coroutine", "self", "debug"}

RE_EVENT_ADD = re.compile(r"\bEvents\s*\.\s*([A-Za-z_]\w*)\s*\.\s*(Add|Remove)\s*\(")
RE_TRIGGER = re.compile(
    r"\b(?:LuaEventManager\s*\.\s*)?triggerEvent\s*\(\s*([\"'])([A-Za-z_]\w*)\1"
)
RE_ADDEVENT = re.compile(r"\bLuaEventManager\s*\.\s*AddEvent\s*\(\s*([\"'])([A-Za-z_]\w*)\1")

RE_METHOD = re.compile(r":\s*([A-Za-z_]\w*)\s*[(\"'{]")
RE_NAMECALL = re.compile(r"([A-Za-z_]\w*)\s*\(")
RE_DEF_BEFORE = re.compile(r"\bfunction\s+[\w.:]*\s*$")
RE_OWNER_BEFORE_COLON = re.compile(r"(?:^|[^\w.:])([A-Za-z_]\w*)\s*$")
RE_OWNER_BEFORE_DOT = re.compile(r"(?:^|[^\w.:\)\]])([A-Za-z_]\w*)\s*\.\s*$")

# declaracoes locais (para nao confundir com globais)
RE_LOCAL_FUNC = re.compile(r"\blocal\s+function\s+([A-Za-z_]\w*)")
RE_LOCAL_FUNC_ASSIGN = re.compile(r"\blocal\s+([A-Za-z_]\w*)\s*=\s*function\b")
RE_FUNC_PARAMS = re.compile(r"\bfunction\s*[\w.:]*\s*\(([^)]*)\)")
RE_TOKENS = re.compile(r"\b(function|if|do|repeat|end|until)\b|[{}()]")

# definicoes de topo
RE_DEF_FUNC = re.compile(
    r"^function\s+([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*)\s*(?::\s*([A-Za-z_]\w*))?\s*\("
)
RE_DEF_ASSIGN = re.compile(r"^([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*)\s*=(?!=)\s*(.*)$")


def _snippet(line: str) -> str:
    return line.strip()[:MAX_SNIPPET]


def _local_names(code_lines: list[str]) -> set[str]:
    names: set[str] = set()
    for ln in code_lines:
        if "function" not in ln and "local" not in ln:
            continue
        for rx in (RE_LOCAL_FUNC, RE_LOCAL_FUNC_ASSIGN):
            for m in rx.finditer(ln):
                names.add(m.group(1))
        for m in RE_FUNC_PARAMS.finditer(ln):
            for p in m.group(1).split(","):
                p = p.strip()
                if p and p != "...":
                    names.add(p)
    return names


def scan_file(rel_media_lua: str, rel_game: str, src: str):
    """Analisa um arquivo. Devolve (usages, events, lua_globals).

    usages:     (symbol, owner, file, line, snippet)
    events:     [(name, line, is_definition)]
    lua_globals:(name, owner, signature, is_static, file, line)
    """
    nocomment, nostr = strip_lua(src)
    orig_lines = src.replace("\r", "").split("\n")
    nc_lines = nocomment.replace("\r", "").split("\n")
    ns_lines = nostr.replace("\r", "").split("\n")

    locals_ = _local_names(ns_lines)

    usages: dict[tuple, tuple] = {}
    events: list[tuple[str, int, bool]] = []
    globals_: list[tuple] = []

    def add_usage(symbol, owner, lineno, line_text):
        key = (symbol, owner, lineno)
        if key not in usages:
            usages[key] = (symbol, owner, rel_media_lua, lineno, _snippet(line_text))

    blk = 0       # profundidade function/if/do/repeat
    brk = 0       # profundidade { } e ( )

    for idx, ns in enumerate(ns_lines):
        lineno = idx + 1
        raw = orig_lines[idx] if idx < len(orig_lines) else ""
        nc = nc_lines[idx] if idx < len(nc_lines) else ""
        if not ns.strip():
            continue

        # ---- definicoes de topo (profundidade zero no inicio da linha)
        if blk == 0 and brk == 0:
            stmt = ns.strip()
            m = RE_DEF_FUNC.match(stmt)
            if m:
                chain = [p.strip() for p in re.split(r"\s*\.\s*", m.group(1))]
                colon = m.group(2)
                params = ""
                pm = re.search(r"\(([^)]*)", stmt)
                if pm:
                    params = pm.group(1).strip()
                if colon:
                    owner = ".".join(chain)
                    globals_.append((colon, owner, f"function {owner}:{colon}({params})", 0,
                                     rel_game, lineno))
                elif len(chain) == 1:
                    globals_.append((chain[0], None, f"function {chain[0]}({params})", 1,
                                     rel_game, lineno))
                else:
                    owner = ".".join(chain[:-1])
                    globals_.append((chain[-1], owner, f"function {owner}.{chain[-1]}({params})",
                                     1, rel_game, lineno))
            else:
                m = RE_DEF_ASSIGN.match(stmt)
                if m:
                    chain = [p.strip() for p in re.split(r"\s*\.\s*", m.group(1))]
                    rhs = m.group(2)
                    if len(chain) == 1:
                        if chain[0] not in KEYWORDS:
                            globals_.append((chain[0], None, _snippet(raw), 1, rel_game, lineno))
                    elif rhs.startswith("function"):
                        owner = ".".join(chain[:-1])
                        pm = re.search(r"function\s*\(([^)]*)", rhs)
                        params = pm.group(1).strip() if pm else ""
                        globals_.append((chain[-1], owner,
                                         f"{owner}.{chain[-1]} = function({params})", 1,
                                         rel_game, lineno))

        # ---- eventos (usam a versao com strings)
        masked = list(ns)
        for m in RE_EVENT_ADD.finditer(nc):
            if ns[m.start()] == " ":
                continue  # dentro de string/comentario
            add_usage(m.group(1), "Events", lineno, raw)
            events.append((m.group(1), lineno, False))
            for k in range(m.start(), m.end()):
                masked[k] = " "
        for m in RE_TRIGGER.finditer(nc):
            if ns[m.start()] == " ":
                continue  # dentro de string/comentario
            add_usage(m.group(2), "Events", lineno, raw)
            events.append((m.group(2), lineno, False))
            for k in range(m.start(), m.end()):
                masked[k] = " "
        for m in RE_ADDEVENT.finditer(nc):
            if ns[m.start()] == " ":
                continue  # dentro de string/comentario
            add_usage(m.group(2), "Events", lineno, raw)
            events.append((m.group(2), lineno, True))
            for k in range(m.start(), m.end()):
                masked[k] = " "
        code = "".join(masked)

        # ---- chamadas de metodo  obj:method(
        for m in RE_METHOD.finditer(code):
            prefix = code[: m.start()]
            if RE_DEF_BEFORE.search(prefix):
                continue  # `function Foo:bar(` e definicao
            name = m.group(1)
            if name in KEYWORDS:
                continue
            owner = None
            om = RE_OWNER_BEFORE_COLON.search(prefix)
            if om and om.group(1)[0].isupper():
                owner = om.group(1)
            add_usage(name, owner, lineno, raw)

        # ---- chamadas de funcao  name(  /  Owner.name(
        for m in RE_NAMECALL.finditer(code):
            name = m.group(1)
            if name in KEYWORDS:
                continue
            prefix = code[: m.start()]
            stripped = prefix.rstrip()
            if RE_DEF_BEFORE.search(prefix):
                continue
            if stripped.endswith(":"):
                continue  # ja tratado como metodo
            if stripped.endswith("."):
                om = RE_OWNER_BEFORE_DOT.search(stripped)
                owner = om.group(1) if om else None
                if owner in STDLIB_OWNERS:
                    continue
                add_usage(name, owner, lineno, raw)
                continue
            # chamada "nua": possivel funcao global
            if name in LUA_BUILTINS or name in locals_:
                continue
            add_usage(name, None, lineno, raw)

        # ---- profundidade (atualiza para a proxima linha)
        for t in RE_TOKENS.finditer(ns):
            w = t.group(1)
            if w in ("function", "if", "do", "repeat"):
                blk += 1
            elif w in ("end", "until"):
                blk = max(0, blk - 1)
            else:
                ch = t.group(0)
                if ch in "{(":
                    brk += 1
                else:
                    brk = max(0, brk - 1)

    return list(usages.values()), events, globals_


def extract(conn: sqlite3.Connection, game_dir) -> dict:
    game = Path(game_dir)
    lua_root = game / "media" / "lua"
    files = sorted(lua_root.rglob("*.lua")) if lua_root.is_dir() else []

    usage_rows: list[tuple] = []
    sym_rows: list[tuple] = []
    # nome do evento -> (file_game, line, is_def)
    event_first: dict[str, tuple[str, int, bool]] = {}
    events_used: dict[str, int] = {}

    for path in files:
        rel_lua = path.relative_to(lua_root).as_posix()
        rel_game = "media/lua/" + rel_lua
        data = path.read_bytes()
        src = data.decode("utf-8", errors="replace").lstrip("﻿")
        usages, events, globs = scan_file(rel_lua, rel_game, src)
        usage_rows.extend(usages)
        for (name, line, is_def) in events:
            events_used[name] = events_used.get(name, 0) + 1
            cur = event_first.get(name)
            if cur is None or (is_def and not cur[2]):
                event_first[name] = (rel_game, line, is_def)
        for (name, owner, sig, is_static, f, line) in globs:
            sym_rows.append(("lua_global", name, owner, None, sig, None, is_static, "lua", f, line))

    for name in sorted(event_first):
        f, line, _ = event_first[name]
        sym_rows.append(("event", name, None, None, None, None, 0, "lua", f, line))

    conn.executemany(
        "INSERT INTO usages(symbol, owner, file, line, snippet) VALUES (?,?,?,?,?)", usage_rows
    )
    conn.executemany(
        "INSERT INTO symbols(kind, name, owner, java_class, signature, returns, is_static,"
        " origin, file, line) VALUES (?,?,?,?,?,?,?,?,?,?)",
        sym_rows,
    )
    n_globals = sum(1 for r in sym_rows if r[0] == "lua_global")
    return {
        "lua_files": len(files),
        "usages": len(usage_rows),
        "events": len(event_first),
        "lua_globals": n_globals,
    }
