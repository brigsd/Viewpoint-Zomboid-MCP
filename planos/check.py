"""Gate dos planos da suíte: valida estados, pastas e o plano ativo do índice.

Uso: python planos/check.py   (sai com código 1 se houver problema)
"""
import re
import sys
from pathlib import Path

PLANOS = Path(__file__).resolve().parent
INDEX = PLANOS / "README.md"
NOT_PLANS = {"README.md", "MODELO.md", "BACKLOG.md"}
MAX_LINES = 300

# estado -> pasta onde o plano deve morar ("" = raiz de planos/)
FOLDER_BY_STATE = {
    "rascunho": "",
    "pronto": "",
    "ativo": "",
    "concluído": "concluidos",
    "cancelado": "concluidos",
    "congelado": "congelados",
}

STATE_RE = re.compile(r"^\*\*Estado:\*\*\s*(.+?)\s*$", re.M)
ACTIVE_RE = re.compile(r"^\*\*Plano ativo:\*\*\s*(.+?)\s*$", re.M)
LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")


def main() -> int:
    errors: list[str] = []
    active: list[Path] = []

    for path in sorted(PLANOS.rglob("*.md")):
        if path.name in NOT_PLANS:
            continue
        rel = path.relative_to(PLANOS).as_posix()
        text = path.read_text(encoding="utf-8")

        lines = text.count("\n") + 1
        if lines > MAX_LINES:
            errors.append(f"{rel}: {lines} linhas (máximo {MAX_LINES})")

        m = STATE_RE.search(text)
        if not m:
            errors.append(f"{rel}: falta a linha **Estado:**")
            continue
        state = m.group(1).strip().lower()
        if state not in FOLDER_BY_STATE:
            errors.append(f"{rel}: estado '{state}' fora da lista {sorted(FOLDER_BY_STATE)}")
            continue

        folder = path.parent.relative_to(PLANOS).as_posix()
        folder = "" if folder == "." else folder
        expected = FOLDER_BY_STATE[state]
        if folder != expected:
            where = f"em {expected}/" if expected else "na raiz de planos/"
            errors.append(f"{rel}: estado '{state}' deve ficar {where}")

        if state == "ativo":
            active.append(path)

    if len(active) > 1:
        names = ", ".join(p.relative_to(PLANOS).as_posix() for p in active)
        errors.append(f"mais de um plano ativo: {names}")

    index_text = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    m = ACTIVE_RE.search(index_text)
    if not m:
        errors.append("README.md: falta a linha **Plano ativo:**")
    else:
        declared = m.group(1)
        link = LINK_RE.search(declared)
        if link:
            target = (PLANOS / link.group(1)).resolve()
            if not target.exists():
                errors.append(f"README.md: plano ativo aponta para arquivo inexistente: {link.group(1)}")
            elif target not in [p.resolve() for p in active]:
                errors.append(f"README.md: {link.group(1)} está no índice como ativo, mas o arquivo não diz 'ativo'")
        elif declared.strip().lower() != "nenhum.":
            errors.append("README.md: **Plano ativo:** deve linkar o plano entre parênteses ou dizer 'nenhum.'")
        elif active:
            errors.append(f"README.md: diz 'nenhum.', mas {active[0].relative_to(PLANOS).as_posix()} está ativo")

    if errors:
        print("planos: FALHOU")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"planos: ok ({'1 ativo' if active else 'nenhum ativo'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
