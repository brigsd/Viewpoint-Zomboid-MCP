"""Confere o índice contra o conjunto de aceitação, usando as mesmas consultas do MCP pz-live.

Uso: python 07-PZ-API-Knowledge/index_check.py   (sai com 1 se alguma entrada divergir)

É o item 2 do gate do plano: cada API real precisa ser encontrada e cada controle negativo não.
A conferência no jogo vivo é o live_check.py (precisa do laboratório ligado).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "06-PZ-Lab-Headless" / "mcp"))
import api_index  # noqa: E402


def found(entry: dict) -> tuple[bool, str]:
    kind, name, owner = entry["kind"], entry["name"], entry.get("owner")
    if kind == "script_field":
        r = api_index.script_fields(owner, name)
        return bool(r.get("ok") and r.get("found", r.get("detail") is not None)), "script_fields"
    if kind == "event":
        r = api_index.api_event(name)
        return bool(r.get("ok") and r.get("exists")), "api_event"
    if kind == "class":
        r = api_index.api_class(name)
        return bool(r.get("ok") and r.get("found", True) and r.get("java_class")), "api_class"
    r = api_index.api_exists(name, owner if kind in ("method", "static_method", "field") else None)
    if not (r.get("ok") and r.get("exists")):
        return False, "api_exists"
    if kind == "static_method":
        return any(m.get("static") for m in r.get("matches", [])), "api_exists(static)"
    if kind == "method":
        return any(not m.get("static") for m in r.get("matches", [])), "api_exists(instância)"
    return True, "api_exists"


def main() -> int:
    data = json.loads((HERE / "acceptance.json").read_text(encoding="utf-8"))
    bad = 0
    for e in data["entries"]:
        got, via = found(e)
        ok = got == e["expect_exists"]
        bad += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {e['id']:<40} esperado={e['expect_exists']!s:<5} índice={got!s:<5} ({via})")
    total = len(data["entries"])
    print(f"\n{total - bad}/{total} entradas batem com o índice")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
