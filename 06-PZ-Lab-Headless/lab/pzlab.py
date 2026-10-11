#!/usr/bin/env python3
"""pzlab - launcher do laboratorio headless de Project Zomboid.

Gerencia um servidor dedicado (Build 42) com ZombieBuddy injetado e o servidor
HTTP experimental dele (/status, /lua, /log, /version) para que mods possam ser
testados de forma autonoma, sem abrir o jogo.

Uso como modulo:   import pzlab; pzlab.start(); pzlab.lua("return 1+1"); pzlab.stop()
Uso como CLI:      python pzlab.py start|stop|restart|status|lua|log [opcoes]

Garantias: nunca escreve na pasta de instalacao do jogo nem em C:\\Users\\<u>\\Zomboid.
Tudo (saves, ini, logs, config do ZombieBuddy) vive em RUNTIME_DIR.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:  # opcional, mas recomendado (ja instalado no ambiente do projeto)
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
LAB_DIR = Path(__file__).resolve().parent
LAB_ROOT = LAB_DIR.parent                       # 06-PZ-Lab-Headless/
RUNTIME_DIR = LAB_ROOT / "runtime"              # -cachedir do PZ + logs + estado
MODS_DIR = LAB_ROOT / "mods"                    # mods em desenvolvimento (layout B42)
LOGS_DIR = RUNTIME_DIR / "lab_logs"            # NAO usar runtime/logs: o PZ move tudo de <cachedir>/Logs para logs_<data>/
AGENT_SRC_DIR = LAB_DIR / "agent"               # fonte do agente auxiliar (Java)
AGENT_JAR = RUNTIME_DIR / "pzlab-agent.jar"     # compilado sob demanda
INBOX_FILE = RUNTIME_DIR / "lab_cmd.txt"        # comandos de console para o servidor
STATE_FILE = RUNTIME_DIR / "lab_state.json"
ZB_CONFIG_DIR = RUNTIME_DIR / "zombie_buddy"    # config/aprovacoes do ZombieBuddy
CONFIG_FILE = LAB_DIR / "lab.json"
LOCAL_CONFIG_FILE = LAB_DIR / "lab.local.json"  # gitignored: senha admin etc.


class LabError(RuntimeError):
    """Erro de operacao do laboratorio (mensagem ja pronta para o usuario)."""


# --------------------------------------------------------------------------- #
# Configuracao
# --------------------------------------------------------------------------- #
_DEFAULTS: dict = {
    "game_dir": r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid",
    "server_name": "pzlab",
    "admin_username": "admin",
    "host": "127.0.0.1",
    "port": 8642,
    "game_port": 16261,
    "udp_port": 16262,
    "xmx": "2048m",
    "jvm_args": [
        "--enable-native-access=ALL-UNNAMED",
        "--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED",
        "-XX:+UseZGC",
        "-XX:-CreateCoredumpOnCrash",
        "-XX:-OmitStackTraceInFastThrow",
        "-Djava.awt.headless=true",
        "-Duser.language=en",
        "-Duser.country=US",
    ],
    "zombiebuddy": {
        "verbosity": 0,
        "policy": "deny-new",
        "frontend": "console",
        "lua_task_timeout_ms": 30000,
    },
    "server_ini": {},
    "sandbox": {},
    "ready_marker": "SERVER STARTED",
    "http_timeout_s": 5,
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise LabError(f"JSON invalido em {path}: {e}")


def load_config() -> dict:
    """Defaults + lab/lab.json + lab/lab.local.json (nesta ordem de precedencia)."""
    cfg = _deep_merge(_DEFAULTS, _read_json(CONFIG_FILE))
    cfg = _deep_merge(cfg, _read_json(LOCAL_CONFIG_FILE))
    return cfg


def _ensure_admin_password(cfg: dict) -> str:
    """Gera (uma vez) a senha admin e grava em lab.local.json. Nunca e impressa."""
    pw = cfg.get("admin_password")
    if pw:
        return pw
    local = _read_json(LOCAL_CONFIG_FILE)
    pw = local.get("admin_password") or secrets.token_hex(12)
    local["admin_password"] = pw
    LOCAL_CONFIG_FILE.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
    cfg["admin_password"] = pw
    return pw


# --------------------------------------------------------------------------- #
# Estado e processo
# --------------------------------------------------------------------------- #
def _now() -> float:
    return time.time()


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def _clear_state() -> None:
    try:
        STATE_FILE.unlink()
    except FileNotFoundError:
        pass


def _proc_matches(state: dict):
    """Retorna o psutil.Process se o PID do estado ainda e NOSSO java.exe, senao None."""
    pid = state.get("pid")
    if not pid:
        return None
    if psutil is None:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        return pid if "java" in out.lower() else None
    try:
        p = psutil.Process(pid)
        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
            return None
        if "java" not in p.name().lower():
            return None
        # Evita PID reciclado: compara o horario de criacao registrado.
        ct = state.get("create_time")
        if ct is not None and abs(p.create_time() - ct) > 3:
            return None
        return p
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _http_get(path: str, timeout: float | None = None) -> tuple[int, str]:
    cfg = load_config()
    url = http_base() + path
    t = timeout if timeout is not None else cfg["http_timeout_s"]
    try:
        with urllib.request.urlopen(url, timeout=t) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _http_ok() -> bool:
    try:
        code, body = _http_get("/status", timeout=2)
        return code == 200 and body.strip().lower() == "ok"
    except Exception:
        return False


def http_base() -> str:
    """Ex.: http://127.0.0.1:8642"""
    st = _read_state()
    cfg = load_config()
    host = st.get("host") or cfg["host"]
    port = st.get("port") or cfg["port"]
    return f"http://{host}:{port}"


def log_path() -> str:
    """Arquivo de log do servidor atual (ou o ultimo, se parado)."""
    st = _read_state()
    if st.get("log_file"):
        return st["log_file"]
    latest = LOGS_DIR / "latest.log"
    return str(latest)


def status() -> dict:
    st = _read_state()
    proc = _proc_matches(st) if st else None
    running = proc is not None
    http_ok = _http_ok() if running else False
    if st and not running:
        # Processo morreu sem passar por stop(): limpa o estado obsoleto.
        _clear_state()
    return {
        "running": running,
        "pid": st.get("pid") if running else None,
        "port": st.get("port") if running else load_config()["port"],
        "http_ok": http_ok,
        "uptime_s": round(_now() - st["started_at"], 1) if running and st.get("started_at") else 0,
        "log_file": st.get("log_file") if st else (str(LOGS_DIR / "latest.log")
                                                    if (LOGS_DIR / "latest.log").exists() else None),
    }


# --------------------------------------------------------------------------- #
# Mods de desenvolvimento
# --------------------------------------------------------------------------- #
def _mod_info_path(mod_dir: Path) -> Path | None:
    cands = []
    for sub in sorted(mod_dir.glob("4*"), reverse=True):  # 42, 42.21 ...
        cands.append(sub / "mod.info")
    cands += [mod_dir / "common" / "mod.info", mod_dir / "mod.info"]
    for c in cands:
        if c.is_file():
            return c
    return None


def _mod_id(mod_dir: Path) -> str:
    info = _mod_info_path(mod_dir)
    if info:
        for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*id\s*=\s*(.+?)\s*$", line)
            if m:
                return m.group(1)
    return mod_dir.name


def list_dev_mods() -> list[dict]:
    """[{folder, id, path}] para cada pasta de mod em MODS_DIR."""
    out = []
    if MODS_DIR.is_dir():
        for d in sorted(MODS_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                out.append({"folder": d.name, "id": _mod_id(d), "path": d})
    return out


def _select_mods(mods: list[str] | None) -> list[dict]:
    avail = list_dev_mods()
    if mods is None:
        return avail
    chosen = []
    for want in mods:
        hit = next((m for m in avail if want in (m["folder"], m["id"])), None)
        if hit is None:
            names = ", ".join(f"{m['folder']}({m['id']})" for m in avail) or "(nenhum)"
            raise LabError(f"mod '{want}' nao encontrado em {MODS_DIR}. Disponiveis: {names}")
        chosen.append(hit)
    return chosen


def _is_junction(p: Path) -> bool:
    try:
        return p.is_junction()  # Python 3.12+
    except AttributeError:  # pragma: no cover
        return False


def _link_mods(selected: list[dict], cachedir: Path) -> None:
    """Liga (junction) ou copia as pastas de mod para <cachedir>/mods."""
    mods_target = cachedir / "mods"
    mods_target.mkdir(parents=True, exist_ok=True)
    # Limpa o que e gerenciado por nos (junctions e copias marcadas).
    for entry in mods_target.iterdir():
        if _is_junction(entry) or entry.is_symlink():
            os.rmdir(entry)
        elif entry.is_dir() and (entry / ".pzlab_copy").exists():
            shutil.rmtree(entry, ignore_errors=True)
    for m in selected:
        dest = mods_target / m["folder"]
        src: Path = m["path"]
        if dest.exists() or _is_junction(dest):
            raise LabError(f"{dest} ja existe e nao e gerenciado pelo lab")
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(dest), str(src)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not dest.exists():
            shutil.copytree(src, dest)
            (dest / ".pzlab_copy").write_text("copia gerenciada pelo pzlab\n")


# --------------------------------------------------------------------------- #
# Arquivos de configuracao do servidor (ini / sandbox)
# --------------------------------------------------------------------------- #
def _merge_ini(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    pending = dict(values)
    out = []
    for line in lines:
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=", line)
        if m and m.group(1) in pending:
            out.append(f"{m.group(1)}={pending.pop(m.group(1))}")
        else:
            out.append(line)
    for k, v in pending.items():
        out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _apply_sandbox(path: Path, overrides: dict) -> None:
    """Aplica overrides de SandboxVars. Se o arquivo ainda nao existe, cria um minimo."""
    if not overrides:
        return

    def fmt(v):
        return "true" if v is True else "false" if v is False else str(v)

    if not path.exists():
        body = "SandboxVars = {\n    VERSION = 6,\n" + "".join(
            f"    {k} = {fmt(v)},\n" for k, v in overrides.items()) + "}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for k, v in overrides.items():
        text, n = re.subn(rf"(?m)^(\s*){re.escape(k)}\s*=\s*[^,\r\n{{]+,", rf"\g<1>{k} = {fmt(v)},", text, count=1)
        if n == 0:
            text = re.sub(r"(SandboxVars\s*=\s*\{)", rf"\1\n    {k} = {fmt(v)},", text, count=1)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Log
# --------------------------------------------------------------------------- #
def _read_text_tail(path: Path | str, lines: int = 100) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            data = f.read().decode("utf-8", "replace")
        return "\n".join(data.splitlines()[-lines:])
    except Exception:
        return ""


def _update_latest_pointer(log_file: Path) -> None:
    """latest.log = hardlink (ao vivo) para o log atual; senao copia/ponteiro de texto."""
    latest = LOGS_DIR / "latest.log"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        os.link(log_file, latest)
    except Exception:
        try:
            latest.write_text(str(log_file), encoding="utf-8")
        except Exception:
            pass


def tail_log(lines: int = 100, source: str = "stdout") -> str:
    """source='stdout' -> le o arquivo de log capturado; 'http' -> GET /log (mesmo conteudo)."""
    if source == "http":
        code, body = _http_get(f"/log?lines={int(lines)}", timeout=10)
        return body
    return _read_text_tail(log_path(), lines)


# --------------------------------------------------------------------------- #
# Lua via HTTP
# --------------------------------------------------------------------------- #
def lua(code: str, depth: int = 1, timeout_s: float = 60, sandbox: bool = True,
        chunkname: str = "pzlab") -> dict:
    """POST /lua. Retorna {"http": status, "ok": bool, "result": <json>|None, "raw": str}.

    O corpo e o proprio codigo Lua (text/plain); o valor do primeiro `return` volta como JSON
    (tabelas serializadas ate `depth` niveis).
    """
    q = urllib.parse.urlencode({"depth": depth, "sandbox": str(bool(sandbox)).lower(),
                                "chunkname": chunkname})
    req = urllib.request.Request(http_base() + "/lua?" + q, data=code.encode("utf-8"),
                                 method="POST", headers={"Content-Type": "text/plain; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            status_code, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status_code, raw = e.code, e.read().decode("utf-8", "replace")
    try:
        parsed = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {"http": status_code, "ok": status_code == 200, "result": parsed, "raw": raw}



# --------------------------------------------------------------------------- #
# Agente auxiliar (Java) - contorna bug do PreMain experimental do ZombieBuddy no Windows
# --------------------------------------------------------------------------- #
def _find_javac(cfg: dict) -> str | None:
    cands = []
    if cfg.get("javac"):
        cands.append(cfg["javac"])
    jh = os.environ.get("JAVA_HOME")
    if jh:
        cands.append(str(Path(jh) / "bin" / "javac.exe"))
    w = shutil.which("javac")
    if w:
        cands.append(w)
    for base in (r"C:\Program Files\Eclipse Adoptium", r"C:\Program Files\Java", r"C:\Program Files\Zulu",
                 r"C:\Program Files\Microsoft", r"C:\Program Files\Amazon Corretto"):
        b = Path(base)
        if b.is_dir():
            cands += [str(x) for x in sorted(b.glob("*/bin/javac.exe"), reverse=True)]
    return next((c for c in cands if c and Path(c).is_file()), None)


def _ensure_agent_jar(cfg: dict) -> Path:
    """Compila lab/agent/pzlab/PreMain.java -> runtime/pzlab-agent.jar (se faltar ou estiver velho)."""
    srcs = sorted(AGENT_SRC_DIR.rglob("*.java"))
    if not srcs:
        raise LabError(f"fonte do agente ausente em {AGENT_SRC_DIR}")
    if AGENT_JAR.is_file() and AGENT_JAR.stat().st_mtime >= max(s.stat().st_mtime for s in srcs):
        return AGENT_JAR
    javac = _find_javac(cfg)
    if not javac:
        raise LabError("javac (JDK 17+) nao encontrado para compilar o agente auxiliar. "
                       "Instale um JDK ou defina \"javac\" em lab/lab.local.json.")
    game = Path(cfg["game_dir"])
    out = RUNTIME_DIR / "agent_build"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cp = os.pathsep.join([str(game / "ZombieBuddy.jar"), str(game / "projectzomboid.jar")])
    r = subprocess.run([javac, "--release", "21", "-nowarn", "-cp", cp, "-d", str(out)] + [str(s) for s in srcs],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise LabError("falha ao compilar o agente auxiliar:\n" + r.stdout + r.stderr)
    import zipfile
    tmp = AGENT_JAR.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out.rglob("*.class"):
            z.write(f, f.relative_to(out).as_posix())
    os.replace(tmp, AGENT_JAR)
    return AGENT_JAR

# --------------------------------------------------------------------------- #
# start / stop / restart
# --------------------------------------------------------------------------- #
def _build_command(cfg: dict, cachedir: Path, password: str, log_file: Path) -> list[str]:
    game = Path(cfg["game_dir"])
    java = game / "jre64" / "bin" / "java.exe"
    if not java.is_file():
        raise LabError(f"java.exe do jogo nao encontrado: {java}")
    for needed in ("projectzomboid.jar", "zbNative.dll", "ZombieBuddy.jar"):
        if not (game / needed).is_file():
            raise LabError(f"arquivo ausente em game_dir: {needed}")
    zb = cfg["zombiebuddy"]
    agent_jar = _ensure_agent_jar(cfg)
    try:  # o ZombieBuddy faz split(":") em patches_jar, entao o caminho precisa ser relativo ao game_dir
        rel_jar = os.path.relpath(agent_jar, game)
    except ValueError:
        raise LabError("runtime e game_dir precisam estar no mesmo drive (patches_jar usa caminho relativo)")
    zb_cfg = ZB_CONFIG_DIR
    zb_cfg.mkdir(parents=True, exist_ok=True)
    agent_args = [
        "experimental",
        f"lua_server_host={cfg['host']}",
        f"lua_server_port={cfg['port']}",
        f"lua_task_timeout={zb['lua_task_timeout_ms']}",
        f"policy={zb['policy']}",
        f"frontend={zb['frontend']}",
        f"verbosity={zb['verbosity']}",
        f"config_dir={zb_cfg}",
        f"patches_jar={rel_jar}:pzlab",
    ]
    if any("," in a for a in agent_args):
        raise LabError("caminhos/valores do agente ZombieBuddy nao podem conter virgula")
    cmd = [str(java)] + list(cfg["jvm_args"]) + [
        f"-Xmx{cfg['xmx']}",
        "-Djava.library.path=./natives/;./natives/win64/;./",
        f"-Dpzlab.inbox={INBOX_FILE}",
        f"-Dpzlab.log={log_file}",
        "-agentlib:zbNative=" + ",".join(agent_args),
        "-cp", "./;projectzomboid.jar",
        "zombie.network.GameServer",
        "-nosteam",
        f"-cachedir={cachedir}",
        f"-servername", cfg["server_name"],
        "-adminusername", cfg["admin_username"],
        "-adminpassword", password,
        "-port", str(cfg["game_port"]),
        "-udpport", str(cfg["udp_port"]),
    ]
    return cmd


def _spawn_detached(cmd: list[str], cwd: str, log_file: Path) -> subprocess.Popen:
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    env = os.environ.copy()
    env.pop("_JAVA_OPTIONS", None)
    logf = open(log_file, "ab", buffering=0)
    try:
        for flags in (base | CREATE_BREAKAWAY_FROM_JOB, base):
            try:
                return subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        stdout=logf, stderr=subprocess.STDOUT,
                                        creationflags=flags, close_fds=True)
            except OSError:
                if flags == base:
                    raise
    finally:
        logf.close()  # o filho herdou o handle; o nosso pode fechar


def _kill_tree(proc) -> None:
    if psutil is not None and not isinstance(proc, int):
        try:
            kids = proc.children(recursive=True)
        except Exception:
            kids = []
        for p in kids + [proc]:
            try:
                p.kill()
            except Exception:
                pass
        psutil.wait_procs(kids + [proc], timeout=10)
    else:
        pid = proc if isinstance(proc, int) else proc.pid
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def _ready_marker_seen(cfg: dict, log_file: Path) -> bool:
    marker = cfg["ready_marker"]
    for p in (RUNTIME_DIR / "server-console.txt", log_file):
        try:
            if marker in _read_text_tail(p, 400):
                return True
        except Exception:
            pass
    return False


def start(mods: list[str] | None = None, timeout_s: int = 300) -> dict:
    """Sobe o servidor headless em background e espera ficar pronto.

    mods=None -> todos os mods de MODS_DIR. Retorna
    {"pid","host","port","cachedir","log_file","started_at","mods"}.
    """
    st = _read_state()
    proc = _proc_matches(st) if st else None
    if proc is not None:
        info = status()
        return {"pid": st["pid"], "host": st["host"], "port": st["port"], "cachedir": st["cachedir"],
                "log_file": st["log_file"], "started_at": st["started_at"], "mods": st.get("mods", []),
                "already_running": True, "http_ok": info["http_ok"]}
    _clear_state()

    cfg = load_config()
    password = _ensure_admin_password(cfg)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    selected = _select_mods(mods)
    mod_ids = [m["id"] for m in selected]
    cachedir = RUNTIME_DIR

    _link_mods(selected, cachedir)
    ini = dict(cfg["server_ini"])
    ini.update({"Mods": ";".join(mod_ids), "DefaultPort": str(cfg["game_port"]),
                "UDPPort": str(cfg["udp_port"])})
    _merge_ini(cachedir / "Server" / f"{cfg['server_name']}.ini", ini)
    _apply_sandbox(cachedir / "Server" / f"{cfg['server_name']}_SandboxVars.lua", cfg.get("sandbox", {}))

    # Remove o server-console.txt anterior para o marcador "SERVER STARTED" nao ser de uma sessao velha.
    try:
        (cachedir / "server-console.txt").unlink()
    except FileNotFoundError:
        pass

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOGS_DIR / f"server-{ts}.log"
    log_file.write_bytes(b"")
    _update_latest_pointer(log_file)

    cmd = _build_command(cfg, cachedir, password, log_file)
    p = _spawn_detached(cmd, cfg["game_dir"], log_file)
    started_at = _now()
    create_time = None
    if psutil is not None:
        try:
            create_time = psutil.Process(p.pid).create_time()
        except Exception:
            pass
    state = {"pid": p.pid, "host": cfg["host"], "port": cfg["port"], "cachedir": str(cachedir),
             "log_file": str(log_file), "started_at": started_at, "create_time": create_time,
             "mods": mod_ids, "server_name": cfg["server_name"]}
    _write_state(state)

    # --- espera: processo vivo -> /status ok -> mundo pronto (marcador + Lua responde) ---
    deadline = started_at + timeout_s
    stage = "aguardando HTTP /status"
    while True:
        if _proc_matches(state) is None:
            _clear_state()
            raise LabError("servidor encerrou durante a inicializacao. Ultimas linhas do log:\n"
                           + _read_text_tail(log_file, 40))
        if _now() > deadline:
            _kill_tree(_proc_matches(state) or p.pid)
            _clear_state()
            raise LabError(f"timeout de {timeout_s}s ({stage}); servidor encerrado. Ultimas linhas:\n"
                           + _read_text_tail(log_file, 40))
        if _http_ok():
            stage = "aguardando mundo carregar (marcador/Lua)"
            if _ready_marker_seen(cfg, log_file):
                try:
                    r = lua("return 1", timeout_s=10)
                    if r["ok"]:
                        break
                except Exception:
                    pass
        time.sleep(1.0)

    state["ready_at"] = _now()
    _write_state(state)
    return {"pid": state["pid"], "host": state["host"], "port": state["port"],
            "cachedir": state["cachedir"], "log_file": state["log_file"],
            "started_at": state["started_at"], "mods": mod_ids,
            "boot_s": round(state["ready_at"] - started_at, 1)}


def console(command: str) -> None:
    """Injeta um comando no console do servidor (ex.: 'players', 'save', 'quit'). Saida vai pro log."""
    with open(INBOX_FILE, "a", encoding="utf-8") as f:
        f.write(command.strip() + "\n")


def _graceful_quit() -> bool:
    """Equivale a digitar 'quit' no console do servidor: salva o mundo e encerra."""
    try:
        console("quit")
        return True
    except Exception:
        return False


def stop(timeout_s: int = 60) -> dict:
    """Encerra o servidor: tenta 'quit' gracioso (salva o mundo) e depois mata a arvore."""
    t0 = _now()
    st = _read_state()
    proc = _proc_matches(st) if st else None
    if proc is None:
        _clear_state()
        return {"stopped": True, "was_running": False, "graceful": False, "forced": False,
                "pid": st.get("pid") if st else None, "elapsed_s": 0.0}
    pid = st["pid"]
    graceful_sent = False
    graceful_sent = _graceful_quit()
    exited = False
    if graceful_sent:
        end = _now() + timeout_s
        while _now() < end:
            if _proc_matches(st) is None:
                exited = True
                break
            time.sleep(0.5)
    forced = False
    if not exited:
        cur = _proc_matches(st)
        if cur is not None:
            forced = True
            _kill_tree(cur)
    _clear_state()
    return {"stopped": _proc_matches(st) is None, "was_running": True,
            "graceful": exited, "forced": forced, "pid": pid, "elapsed_s": round(_now() - t0, 1)}


def restart(mods: list[str] | None = None, timeout_s: int = 300) -> dict:
    stop()
    return start(mods=mods, timeout_s=timeout_s)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pzlab", description="Laboratorio headless de Project Zomboid")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "restart"):
        sp = sub.add_parser(name)
        sp.add_argument("--mods", help="IDs/pastas separados por virgula (padrao: todos em mods/)")
        sp.add_argument("--timeout", type=int, default=300)
    sp = sub.add_parser("stop")
    sp.add_argument("--timeout", type=int, default=60)
    sub.add_parser("status")
    sp = sub.add_parser("lua", help="executa codigo Lua no servidor (texto ou --file)")
    sp.add_argument("code", nargs="?")
    sp.add_argument("--file")
    sp.add_argument("--depth", type=int, default=1)
    sp = sub.add_parser("log")
    sp.add_argument("--lines", type=int, default=50)
    sp.add_argument("--http", action="store_true", help="le via endpoint HTTP /log em vez do arquivo")
    args = ap.parse_args(argv)

    try:
        if args.cmd in ("start", "restart"):
            mods = [m.strip() for m in args.mods.split(",") if m.strip()] if args.mods else None
            fn = start if args.cmd == "start" else restart
            out = fn(mods=mods, timeout_s=args.timeout)
        elif args.cmd == "stop":
            out = stop(timeout_s=args.timeout)
        elif args.cmd == "status":
            out = status()
        elif args.cmd == "lua":
            code = Path(args.file).read_text(encoding="utf-8") if args.file else (args.code or "")
            out = lua(code, depth=args.depth)
        else:
            print(tail_log(args.lines, "http" if args.http else "stdout"))
            return 0
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except LabError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        return 1
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(_main())
