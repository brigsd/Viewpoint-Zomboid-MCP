#!/usr/bin/env python3
"""Conferencia ao vivo do conjunto de aceitacao (acceptance.json) no laboratorio headless.

Para cada entrada executa `lua_probe` (existe?) e `type(lua_type)` (tipo) no servidor
dedicado via `pzlab.lua(...)`, compara com `expect_exists` / `expect_type` e imprime uma
tabela seguida de JSON. Nao grava nada na pasta do jogo nem em C:\\Users\\<voce>\\Zomboid.

Uso:
    python 07-PZ-API-Knowledge/live_check.py            # servidor ja rodando
    python 07-PZ-API-Knowledge/live_check.py --start    # sobe o servidor se preciso
    python 07-PZ-API-Knowledge/live_check.py --start --stop   # e desliga ao final
    python 07-PZ-API-Knowledge/live_check.py --json-out resultado.json

Codigo de saida: 0 = tudo bate; 1 = alguma entrada difere do esperado (ou erro de probe);
2 = servidor indisponivel / acceptance.json invalido.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB_DIR = HERE.parent / "06-PZ-Lab-Headless" / "lab"
ACCEPTANCE = HERE / "acceptance.json"

sys.path.insert(0, str(LAB_DIR))
import pzlab  # noqa: E402


def build_chunk(entry: dict) -> str:
    """Chunk Lua: roda o probe e o type() cada um em pcall; devolve tudo como strings."""
    probe = entry["lua_probe"]
    type_expr = entry.get("lua_type")
    lines = [
        f"local ok, v = pcall(function() return ({probe}) end)",
        "local r = {ok = ok, v = tostring(v)}",
    ]
    if type_expr:
        lines += [
            f"local ok2, t = pcall(function() return type({type_expr}) end)",
            "r.ok2 = ok2",
            "r.t = tostring(t)",
        ]
    lines.append("return r")
    return "\n".join(lines)


def run_entry(entry: dict) -> dict:
    out = {
        "id": entry["id"],
        "kind": entry["kind"],
        "name": entry["name"],
        "owner": entry.get("owner"),
        "expect_exists": entry["expect_exists"],
        "expect_type": entry.get("expect_type"),
        "live_mode": entry.get("live", "direct"),
        "actual_exists": None,
        "actual_type": None,
        "status": "error",
        "detail": "",
    }
    if entry.get("live") == "n/a":
        out["status"] = "skipped"
        out["detail"] = entry.get("live_reason", "n/a")
        return out
    res = pzlab.lua(build_chunk(entry), depth=1, sandbox=True)
    if not res["ok"] or not isinstance(res["result"], dict):
        out["detail"] = f"http {res['http']}: {res['raw'][:200]}"
        return out
    r = res["result"]
    if not r.get("ok"):
        out["detail"] = f"probe falhou: {r.get('v')}"
        return out
    out["actual_exists"] = r.get("v") == "true"
    if entry.get("lua_type"):
        if not r.get("ok2"):
            out["detail"] = f"type() falhou: {r.get('t')}"
            return out
        out["actual_type"] = r.get("t")
    mismatches = []
    if out["actual_exists"] != entry["expect_exists"]:
        mismatches.append(f"exists={out['actual_exists']} (esperado {entry['expect_exists']})")
    if entry.get("expect_type") and out["actual_type"] != entry["expect_type"]:
        mismatches.append(f"type={out['actual_type']} (esperado {entry['expect_type']})")
    out["status"] = "FAIL" if mismatches else "ok"
    out["detail"] = "; ".join(mismatches)
    return out


def print_table(rows: list[dict]) -> None:
    head = ("status", "id", "kind", "exists(exp/real)", "type(exp/real)", "live")
    data = []
    for r in rows:
        data.append((
            r["status"],
            r["id"],
            r["kind"],
            f"{r['expect_exists']}/{r['actual_exists']}",
            f"{r['expect_type']}/{r['actual_type']}" if r["expect_type"] else "-",
            r["live_mode"],
        ))
    widths = [max(len(str(x[i])) for x in [head] + data) for i in range(len(head))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*head))
    print(fmt.format(*("-" * w for w in widths)))
    for d in data:
        print(fmt.format(*d))
    for r in rows:
        if r["detail"]:
            print(f"  ! {r['id']}: {r['detail']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", action="store_true", help="sobe o servidor do laboratorio se nao estiver rodando")
    ap.add_argument("--stop", action="store_true", help="para o servidor ao final (so se o --start o subiu)")
    ap.add_argument("--acceptance", default=str(ACCEPTANCE), help="caminho do acceptance.json")
    ap.add_argument("--json-out", help="grava o JSON do resultado neste arquivo")
    ap.add_argument("--timeout", type=int, default=300, help="timeout do start (s)")
    args = ap.parse_args(argv)

    try:
        entries = json.loads(Path(args.acceptance).read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError, KeyError) as e:
        print(f"acceptance.json invalido: {e}", file=sys.stderr)
        return 2

    t0 = time.time()
    started_here = False
    st = pzlab.status()
    if not (st["running"] and st["http_ok"]):
        if not args.start:
            print("servidor do laboratorio nao esta rodando (use --start ou "
                  "`python 06-PZ-Lab-Headless/lab/pzlab.py start`)", file=sys.stderr)
            return 2
        pzlab.start(timeout_s=args.timeout)
        started_here = True
    boot_s = round(time.time() - t0, 1)

    try:
        try:
            version = pzlab.lua("return getCore():getVersion()")["result"]
            rows = [run_entry(e) for e in entries]
        except Exception as e:  # servidor caiu no meio, etc.
            print(f"erro falando com o servidor: {e}", file=sys.stderr)
            return 2
    finally:
        if started_here and args.stop:
            pzlab.stop()

    checked = [r for r in rows if r["status"] != "skipped"]
    summary = {
        "version": version,
        "total": len(rows),
        "checked": len(checked),
        "ok": sum(r["status"] == "ok" for r in rows),
        "fail": sum(r["status"] == "FAIL" for r in rows),
        "error": sum(r["status"] == "error" for r in rows),
        "skipped": sum(r["status"] == "skipped" for r in rows),
        "boot_s": boot_s,
        "run_s": round(time.time() - t0 - boot_s, 1),
    }
    print_table(rows)
    print()
    print(f"versao {version}: {summary['ok']}/{summary['checked']} batem, "
          f"{summary['fail']} divergem, {summary['error']} com erro, {summary['skipped']} ignoradas")
    payload = {"summary": summary, "results": rows}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if summary["fail"] == 0 and summary["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
