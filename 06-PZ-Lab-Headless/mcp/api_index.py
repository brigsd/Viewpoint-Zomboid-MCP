"""
api_index — consultas ao índice da API do Project Zomboid 42.21 (SQLite)
=========================================================================
Lógica das ferramentas ``api_search``, ``api_class``, ``api_event``, ``script_fields``,
``vanilla_examples`` e ``api_exists`` do servidor MCP ``pz-live`` (ver ``server.py``).

O banco é gerado por ``07-PZ-API-Knowledge/build_index.py`` (esquema fixo em
``07-PZ-API-Knowledge/schema.sql``) e é aberto **somente leitura**. O caminho pode ser trocado com a
variável de ambiente ``PZ_API_DB``. Toda resposta é um dict com ``ok``; falhas trazem
``error``/``error_kind``/``hint`` (mesmo formato do restante do ``pz-live``) e toda resposta de sucesso
traz ``meta.game_version`` e ``meta.built_at`` para que um índice velho seja visível.

"Não encontrado" NÃO é falha: devolve ``ok: true`` com ``found``/``exists`` = ``false``, sugestões e um
``hint`` dizendo para não inventar a API.

IMPORTANTE: este módulo roda dentro de um servidor stdio — nunca use print().
"""

from __future__ import annotations

import difflib
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Optional

ENV_API_DB = "PZ_API_DB"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = REPO_ROOT / "07-PZ-API-Knowledge" / "data" / "pz_api.sqlite"
BUILD_HINT = "rode python 07-PZ-API-Knowledge/build_index.py"

KINDS = ("global_function", "class", "method", "field", "event", "lua_global")
# Desempate entre tipos quando o nome casa igual (classe/global antes de método, etc.)
_KIND_PRIORITY = {"class": 0, "global_function": 1, "event": 2, "method": 3, "field": 4, "lua_global": 5}

MAX_EVENT_USAGES = 10


# --------------------------------------------------------------------------- #
# Infra: caminho, conexão somente leitura, erro padronizado
# --------------------------------------------------------------------------- #
def db_path() -> Path:
    env = os.environ.get(ENV_API_DB)
    return Path(env) if env else DEFAULT_DB


def fail(error: str, kind: str = "error", hint: Optional[str] = None, **extra: Any) -> dict:
    out: dict[str, Any] = {"ok": False, "error": error, "error_kind": kind}
    if hint:
        out["hint"] = hint
    out.update(extra)
    return out


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _meta(conn: sqlite3.Connection) -> dict:
    try:
        kv = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    except sqlite3.Error:
        kv = {}
    return {"game_version": kv.get("game_version"), "built_at": kv.get("built_at")}


def _run(handler: Callable[[sqlite3.Connection], dict]) -> dict:
    """Abre o banco (somente leitura), roda o handler e acrescenta ``meta``."""
    path = db_path()
    if not path.is_file():
        return fail(f"índice da API não encontrado: {path}", kind="index_missing", hint=BUILD_HINT,
                    db_path=str(path))
    try:
        conn = _connect_ro(path)
    except sqlite3.Error as e:
        return fail(f"não foi possível abrir o índice {path}: {e}", kind="index_error", hint=BUILD_HINT,
                    db_path=str(path))
    try:
        out = handler(conn)
        out.setdefault("ok", True)
        if out.get("ok"):
            out["meta"] = _meta(conn)
        return out
    except sqlite3.DatabaseError as e:  # arquivo corrompido / tabela ausente / esquema velho
        return fail(f"índice da API inválido ({type(e).__name__}: {e})", kind="index_error",
                    hint=BUILD_HINT, db_path=str(path))
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Helpers de dados
# --------------------------------------------------------------------------- #
def _q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def call_form(kind: str, name: str, owner: Optional[str], is_static: bool) -> str:
    """Forma de chamada no Lua: ``Owner.metodo`` (estático), ``obj:metodo`` (instância), ``nome()`` (global)."""
    if kind == "global_function":
        return f"{name}()"
    if kind == "method":
        return f"{owner}.{name}" if is_static and owner else f"obj:{name}"
    if kind == "field":
        return f"{owner}.{name}" if is_static and owner else f"obj.{name}"
    if kind == "event":
        return f"Events.{name}"
    return name  # class, lua_global


def _sym(r: sqlite3.Row) -> dict:
    d: dict[str, Any] = {
        "name": r["name"], "kind": r["kind"], "owner": r["owner"], "java_class": r["java_class"],
        "signature": r["signature"], "returns": r["returns"], "static": bool(r["is_static"]),
        "origin": r["origin"], "call": call_form(r["kind"], r["name"], r["owner"], bool(r["is_static"])),
    }
    if r["file"]:
        d["location"] = f"{r['file']}:{r['line']}" if r["line"] is not None else r["file"]
    return d


def _split_qualified(text: str) -> tuple[Optional[str], str]:
    """'ScriptManager:getCraftRecipe' -> ('ScriptManager','getCraftRecipe'); 'Events.OnX.Add' -> ('Events','OnX');
    'getScriptManager()' -> (None,'getScriptManager')."""
    s = re.sub(r"\(.*$", "", (text or "").strip())
    parts = [p for p in re.split(r"[.:]", s) if p]
    if not parts:
        return None, ""
    if len(parts) == 1:
        return None, parts[0]
    if parts[0] == "Events":
        return "Events", parts[1]
    return parts[-2], parts[-1]


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _suggest(conn: sqlite3.Connection, name: str, *, owner: Optional[str] = None,
             kinds: Optional[tuple[str, ...]] = None, limit: int = 8) -> list[dict]:
    """Sugestões "você quis dizer": nomes contendo o termo + nomes parecidos (difflib)."""
    n = (name or "").lower()
    if not n:
        return []
    where, params = [], []
    if owner:
        where.append("owner = ?")
        params.append(owner)
    if kinds:
        where.append("kind IN (%s)" % ",".join("?" * len(kinds)))
        params += list(kinds)
    base = " AND ".join(where)
    pre = _like_escape(n[:3])
    cand_sql = ("SELECT name, owner, kind FROM symbols WHERE " + (base + " AND " if base else "") +
                "(lower(name) LIKE ? ESCAPE '\\' OR lower(name) LIKE ? ESCAPE '\\') LIMIT 4000")
    cands = _q(conn, cand_sql, tuple(params) + (f"%{_like_escape(n)}%", f"{pre}%"))
    if not owner and len(n) >= 4:  # nome parecido sem prefixo/trecho em comum: tenta também pelo sufixo
        tail = _like_escape(n[-3:])
        cands += _q(conn, "SELECT name, owner, kind FROM symbols WHERE " + (base + " AND " if base else "") +
                    "lower(name) LIKE ? ESCAPE '\\' LIMIT 2000", tuple(params) + (f"%{tail}",))
    by_lower: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in cands:
        by_lower[r["name"].lower()].append(r)
    contains = sorted((k for k in by_lower if n in k and k != n), key=lambda k: (len(k), k))
    close = difflib.get_close_matches(n, [k for k in by_lower if k != n], n=limit, cutoff=0.6)
    out: list[dict] = []
    seen: set[tuple] = set()
    for k in contains + close:
        for r in by_lower[k]:
            key = (r["name"], r["owner"], r["kind"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": r["name"], "owner": r["owner"], "kind": r["kind"],
                        "call": call_form(r["kind"], r["name"], r["owner"], False)})
        if len(out) >= limit:
            break
    return out[:limit]


def _clamp(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


NOT_FOUND_HINT = ("não existe no índice da API {ver}: não invente — confira as sugestões, ou valide ao vivo "
                  "com lua_exec/lua_inspect antes de usar.")


def _nf_hint(conn: sqlite3.Connection) -> str:
    return NOT_FOUND_HINT.format(ver=_meta(conn).get("game_version") or "")


# --------------------------------------------------------------------------- #
# 1. api_search
# --------------------------------------------------------------------------- #
def _fts_expr(tokens: list[str]) -> str:
    return " ".join('"%s"*' % t for t in tokens)


def api_search(query: str, kind: Optional[str] = None, limit: int = 20) -> dict:
    query = (query or "").strip()
    if not query:
        return fail("query vazia", kind="usage", hint="Informe um termo, ex. 'getCraftRecipe' ou 'ScriptManager'.")
    if kind and kind not in KINDS:
        return fail(f"kind inválido: {kind!r}", kind="usage", hint="kinds válidos: " + ", ".join(KINDS))
    limit = _clamp(limit, 1, 200, 20)
    owner_q, name_q = _split_qualified(query) if re.search(r"[.:]", query) else (None, query)
    tokens = re.findall(r"[A-Za-z0-9_]+", query)

    def handler(conn: sqlite3.Connection) -> dict:
        kind_sql, kind_p = (" AND s.kind = ?", (kind,)) if kind else ("", ())
        cand: dict[int, tuple[sqlite3.Row, float]] = {}
        mode = "fts"
        # candidatos exatos (independem do FTS estar populado)
        for r in _q(conn, "SELECT s.* FROM symbols s WHERE s.name = ? COLLATE NOCASE" + kind_sql,
                    (name_q,) + kind_p):
            cand[r["id"]] = (r, -1e9)
        if tokens:
            try:
                for r in _q(conn, "SELECT s.*, bm25(symbols_fts) AS rk FROM symbols_fts "
                                  "JOIN symbols s ON s.id = symbols_fts.rowid "
                                  "WHERE symbols_fts MATCH ?" + kind_sql + " ORDER BY rk LIMIT 500",
                            (_fts_expr(tokens),) + kind_p):
                    cand.setdefault(r["id"], (r, r["rk"]))
            except sqlite3.OperationalError:
                pass  # tabela FTS ausente/inconsistente: cai para LIKE
        if not cand:
            mode = "like"
            terms = tokens or [query]
            cond = " AND ".join(
                "(lower(s.name) LIKE ? ESCAPE '\\' OR lower(ifnull(s.owner,'')) LIKE ? ESCAPE '\\' "
                "OR lower(ifnull(s.signature,'')) LIKE ? ESCAPE '\\')" for _ in terms)
            params: list[Any] = []
            for t in terms:
                p = f"%{_like_escape(t.lower())}%"
                params += [p, p, p]
            for r in _q(conn, f"SELECT s.* FROM symbols s WHERE {cond}{kind_sql} LIMIT 500",
                        tuple(params) + kind_p):
                cand[r["id"]] = (r, 0.0)

        nl = name_q.lower()

        def sort_key(item: tuple[sqlite3.Row, float]) -> tuple:
            r, rk = item
            name, owner = r["name"], r["owner"]
            if owner_q and name == name_q and (owner == owner_q or (owner_q == "Events" and r["kind"] == "event")):
                cls = 0
            elif name == name_q:
                cls = 1
            elif name.lower() == nl:
                cls = 2
            elif name.lower().startswith(nl):
                cls = 3
            else:
                cls = 4
            return (cls, _KIND_PRIORITY.get(r["kind"], 9), rk, name, owner or "")

        ordered = sorted(cand.values(), key=sort_key)
        results = [_sym(r) for r, _ in ordered[:limit]]
        out: dict[str, Any] = {"query": query, "kind": kind, "mode": mode, "count": len(results),
                               "total_candidates": len(ordered), "truncated": len(ordered) > limit,
                               "results": results}
        if not results:
            out["found"] = False
            out["suggestions"] = _suggest(conn, name_q, kinds=(kind,) if kind else None)
            out["hint"] = _nf_hint(conn)
        else:
            out["found"] = True
        return out

    return _run(handler)


# --------------------------------------------------------------------------- #
# 2. api_class
# --------------------------------------------------------------------------- #
def api_class(name: str, filter: Optional[str] = None, limit: int = 200) -> dict:
    name = (name or "").strip()
    if not name:
        return fail("name vazio", kind="usage", hint="Informe o nome da classe, ex. 'ScriptManager'.")
    limit = _clamp(limit, 1, 1000, 200)

    def handler(conn: sqlite3.Connection) -> dict:
        classes = _q(conn, "SELECT * FROM symbols WHERE kind = 'class' AND "
                           "(name = ? COLLATE NOCASE OR java_class = ? COLLATE NOCASE) "
                           "ORDER BY (name = ?) DESC, java_class", (name, name, name))
        if not classes:  # aceita 'zombie.scripting.ScriptManager' mesmo se só o sufixo foi dado
            short = re.split(r"[.$]", name)[-1]
            classes = _q(conn, "SELECT * FROM symbols WHERE kind = 'class' AND name = ? COLLATE NOCASE", (short,))
        if not classes:
            owner_rows = _q(conn, "SELECT DISTINCT owner FROM symbols WHERE owner = ? COLLATE NOCASE "
                                  "AND kind IN ('method','field') LIMIT 1", (name,))
            if not owner_rows:
                lua = _q(conn, "SELECT * FROM symbols WHERE kind = 'lua_global' AND name = ? COLLATE NOCASE LIMIT 5",
                         (name,))
                sug = _suggest(conn, name.split(".")[-1], kinds=("class",))
                out = {"ok": True, "found": False, "name": name, "suggestions": sug, "hint": _nf_hint(conn)}
                if lua:
                    out["also_found_as"] = [_sym(r) for r in lua]
                    out["hint"] += " Existe como global definido em Lua (não é classe Java): veja also_found_as."
                return out
            cls_name, java_class, extra_classes = owner_rows[0]["owner"], None, []
        else:
            cls_name, java_class = classes[0]["name"], classes[0]["java_class"]
            extra_classes = [c["java_class"] for c in classes[1:]]

        members = _q(conn, "SELECT * FROM symbols WHERE owner = ? AND kind IN ('method','field') "
                           "ORDER BY kind DESC, name, signature", (cls_name,))
        total = len(members)
        if filter:
            f = filter.lower()
            members = [m for m in members if f in m["name"].lower() or f in (m["signature"] or "").lower()]
        matched = len(members)
        members = members[:limit]
        groups: dict[str, list[dict]] = {k: [] for k in ("static_methods", "instance_methods",
                                                        "static_fields", "instance_fields")}
        for m in members:
            key = ("static_" if m["is_static"] else "instance_") + ("methods" if m["kind"] == "method" else "fields")
            groups[key].append(_sym(m))
        out = {"ok": True, "found": True, "name": cls_name, "java_class": java_class,
               "filter": filter, "total_members": total, "matched": matched, "shown": len(members),
               "truncated": matched > len(members), **groups,
               "counts": {k: len(v) for k, v in groups.items()}}
        if extra_classes:
            out["also_matches"] = extra_classes
        if java_class is None:
            out["note"] = "classe sem linha 'class' no índice (só membros) — java_class desconhecido"
        return out

    return _run(handler)


# --------------------------------------------------------------------------- #
# 3. api_event
# --------------------------------------------------------------------------- #
_ADD_INLINE = re.compile(r"\.Add\s*\(\s*function\s*\(([^)]*)\)")
_ADD_NAMED = re.compile(r"\.Add\s*\(\s*([A-Za-z_][\w.:]*)\s*\)")


def _infer_callback(snippets: list[str]) -> Optional[dict]:
    args: Counter = Counter()
    named: Counter = Counter()
    for s in snippets:
        m = _ADD_INLINE.search(s or "")
        if m:
            args[tuple(a.strip() for a in m.group(1).split(",") if a.strip())] += 1
            continue
        m = _ADD_NAMED.search(s or "")
        if m:
            named[m.group(1)] += 1
    if not args:
        return {"args": None, "inline_samples": 0, "named_handlers": [n for n, _ in named.most_common(5)],
                "note": "nenhum Events.X.Add(function(...)) numa só linha nos usos; veja os handlers nomeados/exemplos"} \
            if named else None
    best, cnt = args.most_common(1)[0]
    return {"args": list(best), "pattern": "function(%s)" % ", ".join(best), "inline_samples": sum(args.values()),
            "agree": cnt, "variants": [{"args": list(a), "count": c} for a, c in args.most_common(5)],
            "named_handlers": [n for n, _ in named.most_common(5)],
            "note": "inferido dos nomes dos parâmetros em usos vanilla; confirme a semântica nos exemplos"}


def api_event(name: str) -> dict:
    ev = (name or "").strip()
    ev = re.sub(r"\(.*$", "", ev)
    ev = re.sub(r"^Events\.", "", ev)
    ev = re.sub(r"\.(Add|Remove)$", "", ev)
    if not ev:
        return fail("name vazio", kind="usage", hint="Informe o evento, ex. 'OnServerStarted' ou 'Events.OnTick'.")

    def handler(conn: sqlite3.Connection) -> dict:
        rows = _q(conn, "SELECT * FROM symbols WHERE kind = 'event' AND name = ?", (ev,))
        if not rows:
            rows = _q(conn, "SELECT * FROM symbols WHERE kind = 'event' AND name = ? COLLATE NOCASE", (ev,))
        sample_name = rows[0]["name"] if rows else ev
        usage_rows = _q(conn, "SELECT * FROM usages WHERE symbol = ? AND owner = 'Events' ORDER BY file, line",
                        (sample_name,))
        out: dict[str, Any] = {"ok": True, "name": sample_name, "usage": f"Events.{sample_name}.Add(function(...) end)",
                               "usage_count": len(usage_rows)}
        if not rows:
            out.update(exists=False, found=False, suggestions=_suggest(conn, ev, kinds=("event",)),
                       hint=_nf_hint(conn))
            if usage_rows:
                out["hint"] += " (há usos no vanilla, mas o evento não está na lista de eventos do índice)"
        else:
            r = rows[0]
            out.update(exists=True, found=True, signature=r["signature"],
                       definition=_sym(r))
        # usos exibidos: espalhados por arquivo; no máximo 10
        shown = _spread(usage_rows, MAX_EVENT_USAGES)
        out["usages"] = [_usage(u) for u in shown]
        out["callback"] = _infer_callback([u["snippet"] for u in usage_rows])
        if rows and not usage_rows:
            out["note"] = "o evento existe, mas nenhum uso no Lua vanilla foi indexado"
        return out

    return _run(handler)


def _usage(u: sqlite3.Row) -> dict:
    return {"location": f"{u['file']}:{u['line']}", "file": u["file"], "line": u["line"],
            "snippet": u["snippet"], "owner": u["owner"]}


def _spread(rows: list[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
    """Escolhe até `limit` usos, no máximo um por arquivo antes de repetir arquivos (mais variedade)."""
    by_file: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)
    picked: list[sqlite3.Row] = []
    rnd = 0
    while len(picked) < limit and any(len(v) > rnd for v in by_file.values()):
        for v in by_file.values():
            if len(v) > rnd and len(picked) < limit:
                picked.append(v[rnd])
        rnd += 1
    return picked


# --------------------------------------------------------------------------- #
# 4. script_fields
# --------------------------------------------------------------------------- #
def _field_row(r: sqlite3.Row) -> dict:
    d = {"field": r["field"], "count": r["count"], "example_value": r["example_value"]}
    if r["example_file"]:
        d["example_location"] = (f"{r['example_file']}:{r['example_line']}"
                                 if r["example_line"] is not None else r["example_file"])
    return d


def _block_types(conn: sqlite3.Connection) -> list[dict]:
    blocks = {r["block_type"]: r["n"] for r in _q(conn, "SELECT block_type, count(*) n FROM script_blocks "
                                                        "GROUP BY block_type")}
    fields = {r["block_type"]: r["n"] for r in _q(conn, "SELECT block_type, count(*) n FROM script_fields "
                                                        "GROUP BY block_type")}
    return [{"block_type": t, "blocks": blocks.get(t, 0), "distinct_fields": fields.get(t, 0)}
            for t in sorted(set(blocks) | set(fields), key=lambda x: (-blocks.get(x, 0), x))]


def script_fields(block_type: Optional[str] = None, field: Optional[str] = None) -> dict:
    block_type = (block_type or "").strip()

    def handler(conn: sqlite3.Connection) -> dict:
        types = _block_types(conn)
        if not block_type:
            return {"ok": True, "block_types": types,
                    "hint": "passe block_type (ex. 'item', 'craftRecipe') para listar os campos."}
        canon = next((t["block_type"] for t in types if t["block_type"] == block_type), None) \
            or next((t["block_type"] for t in types if t["block_type"].lower() == block_type.lower()), None)
        if canon is None:
            names = [t["block_type"] for t in types]
            return {"ok": True, "found": False, "block_type": block_type, "block_types": types,
                    "suggestions": difflib.get_close_matches(block_type, names, n=5, cutoff=0.5),
                    "hint": _nf_hint(conn)}
        total = next(t["blocks"] for t in types if t["block_type"] == canon)
        samples = [{"name": r["name"], "module": r["module"], "location": f"{r['file']}:{r['line']}"}
                   for r in _q(conn, "SELECT * FROM script_blocks WHERE block_type = ? ORDER BY file, line LIMIT 3",
                               (canon,))]
        base: dict[str, Any] = {"ok": True, "found": True, "block_type": canon, "block_count": total,
                                "block_samples": samples, "block_types": [t["block_type"] for t in types]}
        rows = _q(conn, "SELECT * FROM script_fields WHERE block_type = ? ORDER BY count DESC, field", (canon,))
        if not field:
            base["field_count"] = len(rows)
            base["fields"] = [_field_row(r) for r in rows]
            return base
        f = field.strip()
        exact = [r for r in rows if r["field"] == f] or [r for r in rows if r["field"].lower() == f.lower()]
        children = [r for r in rows if r["field"].lower().startswith(f.lower() + ".")]
        parent = None
        if not exact and "." in f:  # 'inputs.item' ausente: devolve o campo pai ('inputs')
            pf = f.rsplit(".", 1)[0].lower()
            parent = next((r for r in rows if r["field"].lower() == pf), None)
        base["queried_field"] = f
        if exact or children:
            base["field_found"] = True
            if exact:
                base["detail"] = _field_row(exact[0])
            if children:
                base["children"] = [_field_row(r) for r in children]
            return base
        base["field_found"] = False
        if parent is not None:
            base["parent"] = _field_row(parent)
            base["note"] = f"'{f}' não está indexado como campo próprio; o campo pai é '{parent['field']}'"
        others = _q(conn, "SELECT block_type, field, count FROM script_fields WHERE lower(field) = ? "
                          "AND block_type <> ? ORDER BY count DESC LIMIT 5", (f.lower(), canon))
        if others:
            base["found_in_other_blocks"] = [{"block_type": o["block_type"], "field": o["field"],
                                              "count": o["count"]} for o in others]
        base["suggestions"] = difflib.get_close_matches(f, [r["field"] for r in rows], n=5, cutoff=0.5)
        base["hint"] = _nf_hint(conn)
        return base

    return _run(handler)


# --------------------------------------------------------------------------- #
# 5. vanilla_examples
# --------------------------------------------------------------------------- #
def vanilla_examples(symbol: str, limit: int = 10) -> dict:
    owner, sym = _split_qualified(symbol)
    if not sym:
        return fail("symbol vazio", kind="usage", hint="Ex.: 'getCraftRecipe', 'ScriptManager:getCraftRecipe', 'Events.OnTick'.")
    limit = _clamp(limit, 1, 50, 10)

    def handler(conn: sqlite3.Connection) -> dict:
        rows = _q(conn, "SELECT * FROM usages WHERE symbol = ? ORDER BY file, line", (sym,))
        note = None
        if not rows:
            rows = _q(conn, "SELECT * FROM usages WHERE symbol = ? COLLATE NOCASE ORDER BY file, line", (sym,))
            if rows:
                note = f"sem usos com a grafia exata '{sym}'; mostrando '{rows[0]['symbol']}' (o Lua diferencia maiúsculas)"
        excluded = 0
        if owner and rows:
            keep = [r for r in rows if r["owner"] in (owner, None)]
            excluded = len(rows) - len(keep)
            rows = sorted(keep, key=lambda r: (r["owner"] != owner, r["file"], r["line"]))  # dono certo primeiro
        shown = rows[:limit] if owner else _spread(rows, limit)
        defs = [_sym(r) for r in _q(conn, "SELECT * FROM symbols WHERE name = ? " +
                                    ("AND (owner = ? OR kind = 'event') " if owner else "") +
                                    "ORDER BY kind LIMIT 5", (sym, owner) if owner else (sym,))]
        out: dict[str, Any] = {"ok": True, "symbol": sym, "owner": owner, "total": len(rows), "shown": len(shown),
                               "examples": [_usage(u) for u in shown], "definitions": defs}
        if excluded:
            out["excluded_other_owner"] = excluded
        if note:
            out["note"] = note
        if not rows:
            out["found"] = False
            sug = [r["symbol"] for r in _q(conn, "SELECT DISTINCT symbol FROM usages WHERE lower(symbol) LIKE ? ESCAPE '\\' "
                                                  "ORDER BY length(symbol) LIMIT 8",
                                           (f"%{_like_escape(sym.lower())}%",))]
            out["suggestions"] = sug or [s["name"] for s in _suggest(conn, sym)]
            out["hint"] = ("sem usos no Lua vanilla indexado" +
                           (" (o símbolo existe no índice, apenas não é usado no vanilla)" if defs else
                            " e o símbolo nem existe no índice — não invente; use api_search/api_exists"))
        else:
            out["found"] = True
        return out

    return _run(handler)


# --------------------------------------------------------------------------- #
# 6. api_exists
# --------------------------------------------------------------------------- #
def api_exists(name: str, owner: Optional[str] = None) -> dict:
    raw = (name or "").strip()
    if not raw:
        return fail("name vazio", kind="usage", hint="Ex.: api_exists('Languages.instance') ou api_exists('getCraftRecipe', owner='ScriptManager').")
    q_owner, q_name = _split_qualified(raw) if re.search(r"[.:]", raw) else (None, re.sub(r"\(.*$", "", raw))
    owner = (owner or "").strip() or q_owner
    if not q_name:
        return fail("name inválido", kind="usage")

    def handler(conn: sqlite3.Connection) -> dict:
        out: dict[str, Any] = {"ok": True, "query": raw, "name": q_name, "owner": owner}
        if owner == "Events":
            rows = _q(conn, "SELECT * FROM symbols WHERE kind = 'event' AND name = ?", (q_name,))
            soft = _q(conn, "SELECT * FROM symbols WHERE kind = 'event' AND name = ? COLLATE NOCASE", (q_name,))
        elif owner:
            rows = _q(conn, "SELECT * FROM symbols WHERE name = ? AND owner = ?", (q_name, owner))
            soft = _q(conn, "SELECT * FROM symbols WHERE name = ? COLLATE NOCASE AND owner = ? COLLATE NOCASE",
                      (q_name, owner))
        else:
            rows = _q(conn, "SELECT * FROM symbols WHERE name = ?", (q_name,))
            soft = _q(conn, "SELECT * FROM symbols WHERE name = ? COLLATE NOCASE", (q_name,))
        out["exists"] = bool(rows)
        out["matches"] = [_sym(r) for r in sorted(rows, key=lambda r: (_KIND_PRIORITY.get(r["kind"], 9), r["owner"] or ""))[:20]]
        if rows:
            out["kinds"] = sorted({r["kind"] for r in rows})
            return out
        # --- não existe ---
        if soft:
            out["case_mismatch"] = [_sym(r) for r in soft[:10]]
        if owner and owner != "Events":
            cls = _q(conn, "SELECT 1 FROM symbols WHERE kind = 'class' AND name = ? LIMIT 1", (owner,))
            if not cls:
                owner_any = _q(conn, "SELECT 1 FROM symbols WHERE owner = ? LIMIT 1", (owner,))
                out["owner_exists"] = bool(owner_any)
                if not owner_any:
                    lg = _q(conn, "SELECT * FROM symbols WHERE kind = 'lua_global' AND name = ? LIMIT 1", (owner,))
                    if lg:
                        out["owner_is_lua_global"] = _sym(lg[0])
                    out["owner_suggestions"] = _suggest(conn, owner, kinds=("class",))
            else:
                out["owner_exists"] = True
            out["suggestions"] = _suggest(conn, q_name, owner=owner)
            if not out["suggestions"] and out.get("owner_exists"):
                out["suggestions"] = _suggest(conn, q_name)
        else:
            out["suggestions"] = _suggest(conn, q_name, kinds=("event",) if owner == "Events" else None)
        out["hint"] = _nf_hint(conn)
        return out

    return _run(handler)
