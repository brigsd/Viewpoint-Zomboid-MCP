"""Extrator dos scripts do jogo (media/scripts/**/*.txt).

Formato (uma chave/chave-fecha por linha):

    module Base
    {
        imports { default, }
        item Foo
        {
            Key = Value,
            nested { Key = Value, }
        }
        craftRecipe Bar
        {
            inputs
            {
                item 2 [Base.X] mode:keep flags[Prop1],
            }
        }
    }

Preenche `script_blocks` (um por bloco de topo dentro de `module`) e
`script_fields` (campos por tipo de bloco, com contagem e exemplo real).
Campos de blocos aninhados recebem o caminho como prefixo (`inputs.item`).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MAX_EXAMPLE = 300

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_NOT_NL = re.compile(r"[^\n]")
_FLAG_RE = re.compile(r"\bflags\[([^\]]*)\]")
_MODE_RE = re.compile(r"(?<![\w])mode:(\w+)")
_BRACKET_RE = re.compile(r"(?<![\w])(tags|mappers|variable)\[[^\]]*\]")
_MAPPER_RE = re.compile(r"(?<![\w])mapper:\S+")


def _strip_comments_keep_lines(text: str) -> list[str]:
    def repl(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    text = _BLOCK_COMMENT.sub(repl, text)
    return text.replace("\r", "").split("\n")


class _Fields:
    """Acumula contagem + primeiro exemplo nao-vazio por (block_type, field)."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], list] = {}

    def add(self, block_type: str, field: str, value: str | None, file: str, line: int) -> None:
        key = (block_type, field)
        value = (value or "").strip()
        if len(value) > MAX_EXAMPLE:
            value = value[:MAX_EXAMPLE]
        rec = self.data.get(key)
        if rec is None:
            self.data[key] = [1, value or None, file, line]
        else:
            rec[0] += 1
            if rec[1] is None and value:
                rec[1], rec[2], rec[3] = value, file, line


def _clean_value(v: str) -> str:
    v = v.strip()
    if v.endswith(","):
        v = v[:-1].rstrip()
    return v


def _split_header(header: str) -> tuple[str, str]:
    parts = header.split()
    kind = parts[0]
    if kind == "template" and len(parts) >= 3:
        return f"template {parts[1]}", " ".join(parts[2:])
    return kind, " ".join(parts[1:])


def parse_script_text(text: str, rel_file: str, blocks: list, fields: _Fields) -> None:
    lines = [l.strip() for l in _strip_comments_keep_lines(text)]
    # linhas que comecam com // sao comentario
    lines = ["" if l.startswith("//") else l for l in lines]
    n = len(lines)

    # proxima linha nao vazia, para saber se a linha atual e cabecalho
    next_nonempty = [""] * n
    nxt = ""
    for i in range(n - 1, -1, -1):
        next_nonempty[i] = nxt
        if lines[i]:
            nxt = lines[i]

    # pilha de contexto: ("module", nome) | ("block", tipo, nome) | ("nested", segmento)
    stack: list[tuple] = []
    module: str | None = None
    pending: tuple | None = None  # cabecalho aguardando '{'

    def block_ctx():
        for ctx in stack:
            if ctx[0] == "block":
                return ctx
        return None

    for i, line in enumerate(lines):
        if not line:
            continue
        lineno = i + 1
        if line == "{":
            if pending is not None:
                stack.append(pending)
                if pending[0] == "module":
                    module = pending[1]
            else:
                stack.append(("anon",))
            pending = None
            continue
        if line == "}":
            if stack:
                ctx = stack.pop()
                if ctx[0] == "module":
                    module = None
            continue

        if next_nonempty[i] == "{":  # cabecalho
            first = line.split()[0]
            rest = " ".join(line.split()[1:])
            bctx = block_ctx()
            if bctx is None:
                if first == "module":
                    pending = ("module", rest)
                else:
                    btype, name = _split_header(line)
                    if btype != "imports":
                        blocks.append((btype, module, name, rel_file, lineno))
                    pending = ("block", btype, name, [])
            else:
                # aninhado: caminho = segmentos dos ancestrais + primeiro termo
                path = [c[1] for c in stack if c[0] == "nested"]
                path.append(first)
                pending = ("nested", first)
                if bctx[1] != "imports":
                    fields.add(bctx[1], ".".join(path), rest, rel_file, lineno)
            continue

        # linha de campo
        bctx = block_ctx()
        if bctx is None:
            continue  # linhas soltas fora de bloco (imports, etc.)
        btype = bctx[1]
        if btype == "imports":
            continue
        path = [c[1] for c in stack if c[0] == "nested"]
        prefix = ".".join(path) + "." if path else ""
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            if path and ("." in key or key[:1].isdigit()):
                continue  # mapeamentos arbitrarios (itemMapper: Base.A = Base.B)
            fields.add(btype, prefix + key, _clean_value(val), rel_file, lineno)
        else:
            toks = line.rstrip(",").split()
            if len(toks) < 2:
                continue  # entradas de lista (ex.: `Beverage,`)
            key = toks[0]
            full = line  # linha real, como aparece no vanilla (com a virgula final)
            fields.add(btype, prefix + key, full, rel_file, lineno)
            tail = " ".join(toks[1:])
            for fm in _FLAG_RE.finditer(tail):
                for flag in fm.group(1).split(";"):
                    flag = flag.strip()
                    if flag:
                        fields.add(btype, f"{prefix}{key} flags[{flag}]", full, rel_file, lineno)
            for mm in _MODE_RE.finditer(tail):
                fields.add(btype, f"{prefix}{key} mode:{mm.group(1)}", full, rel_file, lineno)
            for bm in _BRACKET_RE.finditer(tail):
                fields.add(btype, f"{prefix}{key} {bm.group(1)}[]", full, rel_file, lineno)
            if _MAPPER_RE.search(tail):
                fields.add(btype, f"{prefix}{key} mapper:", full, rel_file, lineno)


def extract(conn: sqlite3.Connection, game_dir) -> dict:
    game = Path(game_dir)
    root = game / "media" / "scripts"
    files = sorted(root.rglob("*.txt")) if root.is_dir() else []

    blocks: list[tuple] = []
    fields = _Fields()
    for path in files:
        rel = path.relative_to(root).as_posix()
        text = path.read_bytes().decode("utf-8", errors="replace").lstrip("﻿")
        parse_script_text(text, rel, blocks, fields)

    conn.executemany(
        "INSERT INTO script_blocks(block_type, module, name, file, line) VALUES (?,?,?,?,?)",
        blocks,
    )
    conn.executemany(
        "INSERT INTO script_fields(block_type, field, count, example_value, example_file,"
        " example_line) VALUES (?,?,?,?,?,?)",
        [(bt, f, r[0], r[1], r[2], r[3]) for (bt, f), r in sorted(fields.data.items())],
    )
    return {
        "script_files": len(files),
        "script_blocks": len(blocks),
        "script_block_types": len({b[0] for b in blocks}),
        "script_fields": len(fields.data),
    }
