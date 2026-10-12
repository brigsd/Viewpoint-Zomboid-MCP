"""Deixa uma versão só do Viewpoint: a da Workshop vira a da pasta do jogo e a cópia da suíte.

Uso:
  python 02-Viewpoint-PrimeiraPessoa/sync_viewpoint.py           # mostra o que mudaria
  python 02-Viewpoint-PrimeiraPessoa/sync_viewpoint.py --apply   # aplica

O que faz com --apply (com o jogo fechado):
  1. Copia o Viewpoint.jar da Workshop para a pasta do jogo (o ProjectZomboid64.json carrega esse
     arquivo via patches_jar). O JAR antigo fica salvo como Viewpoint.jar.bak-<versão>.
  2. Espelha o mod da Workshop em 02-Viewpoint-PrimeiraPessoa/mods/Viewpoint e atualiza o Viewpoint.jar
     da raiz do módulo. Ignora o que o Módulo 05 antigo gravou na pasta da Workshop.
  3. Registra o hash SHA-256 do JAR novo em ~/.zombie_buddy/mod_approvals.json, para o ZombieBuddy
     não abrir a janela de aprovação (que pode ficar escondida atrás do jogo).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid")
WORKSHOP_MOD = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600\3809306528\mods\Viewpoint")
SUITE_MOD = HERE / "mods" / "Viewpoint"
APPROVALS = Path.home() / ".zombie_buddy" / "mod_approvals.json"
JAR_IN_MOD = Path("42/media/java/client/Viewpoint.jar")
WORKSHOP_ID = 3809306528

# Deixado na pasta da Workshop pelo deploy antigo do Módulo 05; não faz parte do Viewpoint.
FOREIGN = ("42/media/modelpacks/", "42/media/lua/client/Viewpoint_AutoRegisterPacks.lua")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mod_version(mod_dir: Path) -> str:
    for line in (mod_dir / "common" / "mod.info").read_text(encoding="utf-8").splitlines():
        if line.startswith("modversion="):
            return line.split("=", 1)[1].strip()
    return "?"


def mod_files(root: Path) -> dict[str, Path]:
    files = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not rel.startswith(FOREIGN):
            files[rel] = p
    return files


def game_running() -> bool:
    out = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout
    return "ProjectZomboid64" in out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="aplica as mudanças (sem isso só mostra)")
    args = ap.parse_args()

    src_jar = WORKSHOP_MOD / JAR_IN_MOD
    if not src_jar.is_file():
        print(f"Viewpoint da Workshop não encontrado em {WORKSHOP_MOD}")
        return 2
    version, new_hash = mod_version(WORKSHOP_MOD), sha256(src_jar)
    game_jar, suite_jar = GAME_DIR / "Viewpoint.jar", HERE / "Viewpoint.jar"

    print(f"Workshop: Viewpoint {version} ({new_hash[:12]})")
    print(f"Pasta do jogo: {sha256(game_jar)[:12] if game_jar.exists() else 'sem JAR'}")
    print(f"Cópia da suíte: {mod_version(SUITE_MOD) if SUITE_MOD.exists() else 'nenhuma'}")

    src, dst = mod_files(WORKSHOP_MOD), mod_files(SUITE_MOD) if SUITE_MOD.exists() else {}
    copy = [r for r, p in src.items() if r not in dst or sha256(p) != sha256(dst[r])]
    delete = [r for r in dst if r not in src]
    need_game = not game_jar.exists() or sha256(game_jar) != new_hash
    approvals = json.loads(APPROVALS.read_text(encoding="utf-8-sig")) if APPROVALS.exists() else {"mods": [], "formatVersion": 1}
    need_approval = not any(m.get("jar_hash") == new_hash for m in approvals.get("mods", []))

    print(f"\nPasta do jogo: {'trocar JAR' if need_game else 'já igual'}")
    print(f"Cópia da suíte: {len(copy)} arquivo(s) para copiar, {len(delete)} para remover")
    print(f"Aprovação do ZombieBuddy: {'registrar hash novo' if need_approval else 'já registrada'}")

    if not args.apply:
        print("\n(nada alterado; rode com --apply)")
        return 0
    if game_running():
        print("\nFeche o Project Zomboid antes de aplicar.")
        return 2

    if need_game:
        if game_jar.exists():
            backup = GAME_DIR / f"Viewpoint.jar.bak-{sha256(game_jar)[:12]}"
            if not backup.exists():
                shutil.copy2(game_jar, backup)
                print(f"backup: {backup.name}")
        shutil.copy2(src_jar, game_jar)
    for rel in copy:
        target = SUITE_MOD / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src[rel], target)
    for rel in delete:
        (SUITE_MOD / rel).unlink()
    for d in sorted((p for p in SUITE_MOD.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    shutil.copy2(src_jar, suite_jar)
    if need_approval:
        approvals.setdefault("mods", []).append(
            {"jar_hash": new_hash, "modId": "Viewpoint", "workshop_id": WORKSHOP_ID, "decision": True})
        APPROVALS.write_text(json.dumps(approvals, indent=4), encoding="utf-8")

    ok = sha256(game_jar) == sha256(suite_jar) == new_hash
    print(f"\n{'OK' if ok else 'FALHOU'}: Viewpoint {version} na Workshop, na pasta do jogo e na suíte")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
