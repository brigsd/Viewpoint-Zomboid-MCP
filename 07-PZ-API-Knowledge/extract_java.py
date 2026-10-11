#!/usr/bin/env python3
"""Extrator do lado Java do índice da API do Project Zomboid (Módulo 07).

Descobre quais classes Java o jogo expõe ao Lua e quais métodos/campos/funções
globais o Lua enxerga, e grava em `symbols` (origin='java'):

  kind='class'           classe exposta (name = nome curto, java_class = FQN)
  kind='method'          método público (owner = nome curto); construtores viram 'new'
  kind='field'           constante/campo público estático
  kind='global_function' função global do Lua (@LuaMethod(global=true))

Como a exposição funciona na 42.21 (confirmado nos bytecodes do jar):

  * `zombie.Lua.LuaManager$Exposer.exposeAll()` chama `setExposed(Class)` para
    ~1000 classes (constantes de classe) e delega a helpers estáticos
    (`BuildingRoomsEditor.setExposed(Exposer)`, `UIWorldMap.setExposed(...)`,
    que por sua vez chamam outros). Só as classes desse conjunto são
    registradas (`Exposer.shouldExpose` = pertence ao conjunto).
  * Para cada classe exposta o Kahlua (`LuaJavaClassExposer`) usa
    `Class.getMethods()`/`getFields()`: expõe métodos públicos (inclusive os
    herdados) e campos públicos estáticos, exceto o que tem `@HiddenFromLua`;
    métodos estáticos e construtores (`Classe.new`) ficam na tabela da classe.
    O nome global no Lua é `Class.getSimpleName()` (a primeira classe com o nome
    ganha; o caminho completo `zombie.inventory.ItemContainer` também existe).
  * Funções globais: `exposeGlobalFunctions(new LuaManager$GlobalObject())`
    publica cada método com `@LuaMethod(name=..., global=true)`; o nome Lua vem
    da anotação e pode diferir do nome Java.
  * `exposeKeyboardKeys/exposeMouseButtons/exposeLuaCalendar` publicam
    constantes inteiras em `Keyboard`, `Mouse` e `Calendar`.

Ferramentas: o `.class` é lido direto do jar com um leitor de class file em
Python puro (rápido e exato: flags, anotações, assinaturas genéricas); o
`javap -c` só é usado para ler o bytecode do `Exposer` (lista de classes). Para
herança vinda do JDK (ArrayList, Collection...) as classes são extraídas do
runtime com `jimage` para o cache. Nada é gravado na pasta do jogo.

Uso:
    python extract_java.py [--game-dir DIR] [--db ARQUIVO.sqlite]
ou, via build_index.py: `extract(conn, game_dir) -> dict` de contagens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "data" / "cache"
SCHEMA_PATH = HERE / "schema.sql"
CACHE_VERSION = 3
DEFAULT_GAME_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
JAR_NAME = "projectzomboid.jar"

# Nomes internos que o mecanismo de exposição usa (configuráveis para testes).
EXPOSER_CANDIDATES = ("zombie/Lua/LuaManager$Exposer",)
EXPOSER_SUPER = "se/krka/kahlua/integration/expose/LuaJavaClassExposer"
HIDDEN_ANN = "Lzombie/HiddenFromLua;"
LUA_METHOD_ANN = "Lse/krka/kahlua/integration/annotations/LuaMethod;"

ACC_PUBLIC, ACC_STATIC, ACC_FINAL = 0x0001, 0x0008, 0x0010
ACC_VARARGS, ACC_BRIDGE, ACC_SYNTHETIC = 0x0080, 0x0040, 0x1000
ACC_INTERFACE, ACC_ABSTRACT, ACC_ANNOTATION, ACC_ENUM = 0x0200, 0x0400, 0x2000, 0x4000

# Constantes inteiras que o LuaManager publica fora do mecanismo de classes:
#   método -> (nome da tabela no Lua, filtro do nome do campo)
SPECIAL_CONSTANTS = {
    "exposeKeyboardKeys": ("Keyboard", lambda n: n.startswith("KEY_") and not n.endswith("WIN")),
    "exposeMouseButtons": ("Mouse", lambda n: n.startswith("BTN_") or n in ("LMB", "RMB", "MMB")),
    "exposeLuaCalendar": ("Calendar", lambda n: True),
}


# ---------------------------------------------------------------------------
# Leitor de class file
# ---------------------------------------------------------------------------
class ClassInfo:
    __slots__ = ("name", "super", "interfaces", "flags", "fields", "methods", "annotations", "signature")

    def __init__(self):
        self.name = ""
        self.super = None
        self.interfaces = []
        self.flags = 0
        self.fields = []      # dicts: flags,name,desc,sig,anns,const
        self.methods = []     # dicts: flags,name,desc,sig,anns
        self.annotations = []
        self.signature = None


def _parse_annotation(b, pos, cp):
    type_idx, n = struct.unpack_from(">HH", b, pos)
    pos += 4
    elems = {}
    for _ in range(n):
        (name_idx,) = struct.unpack_from(">H", b, pos)
        pos += 2
        val, pos = _parse_element_value(b, pos, cp)
        elems[cp[name_idx][1]] = val
    return (cp[type_idx][1], elems), pos


def _parse_element_value(b, pos, cp):
    tag = chr(b[pos])
    pos += 1
    if tag in "BCDFIJSZ":
        (idx,) = struct.unpack_from(">H", b, pos)
        pos += 2
        ent = cp[idx]
        if ent[0] == 3:
            val = struct.unpack(">i", ent[1])[0]
            if tag == "Z":
                val = bool(val)
        else:
            val = ent[1]
        return val, pos
    if tag == "s":
        (idx,) = struct.unpack_from(">H", b, pos)
        return cp[idx][1], pos + 2
    if tag == "e":
        t, c = struct.unpack_from(">HH", b, pos)
        return (cp[t][1], cp[c][1]), pos + 4
    if tag == "c":
        (idx,) = struct.unpack_from(">H", b, pos)
        return cp[idx][1], pos + 2
    if tag == "@":
        return _parse_annotation(b, pos, cp)
    if tag == "[":
        (n,) = struct.unpack_from(">H", b, pos)
        pos += 2
        out = []
        for _ in range(n):
            v, pos = _parse_element_value(b, pos, cp)
            out.append(v)
        return out, pos
    raise ValueError("element_value desconhecido: " + tag)


def _parse_attributes(b, pos, cp, want):
    """Lê os atributos; devolve (dict nome->valor, nova posição). `want` filtra."""
    (n,) = struct.unpack_from(">H", b, pos)
    pos += 2
    out = {}
    for _ in range(n):
        name_idx, length = struct.unpack_from(">HI", b, pos)
        pos += 6
        name = cp[name_idx][1]
        if name in want:
            if name == "Signature":
                (i,) = struct.unpack_from(">H", b, pos)
                out[name] = cp[i][1]
            elif name == "ConstantValue":
                (i,) = struct.unpack_from(">H", b, pos)
                out[name] = i
            elif name == "RuntimeVisibleAnnotations":
                (cnt,) = struct.unpack_from(">H", b, pos)
                p = pos + 2
                anns = []
                for _ in range(cnt):
                    a, p = _parse_annotation(b, p, cp)
                    anns.append(a)
                out[name] = anns
        pos += length
    return out, pos


def parse_class(data: bytes) -> ClassInfo:
    magic, _minor, _major = struct.unpack_from(">IHH", data, 0)
    if magic != 0xCAFEBABE:
        raise ValueError("não é um class file")
    pos = 8
    (n,) = struct.unpack_from(">H", data, pos)
    pos += 2
    cp = [None] * n
    i = 1
    while i < n:
        t = data[pos]
        pos += 1
        if t == 1:
            (ln,) = struct.unpack_from(">H", data, pos)
            pos += 2
            cp[i] = (1, data[pos:pos + ln].decode("utf-8", "replace"))
            pos += ln
        elif t in (3, 4):
            cp[i] = (t, data[pos:pos + 4])
            pos += 4
        elif t in (5, 6):
            cp[i] = (t, data[pos:pos + 8])
            pos += 8
            i += 1
        elif t in (7, 8, 16, 19, 20):
            cp[i] = (t, struct.unpack_from(">H", data, pos)[0])
            pos += 2
        elif t in (9, 10, 11, 12, 17, 18):
            cp[i] = (t, struct.unpack_from(">HH", data, pos))
            pos += 4
        elif t == 15:
            cp[i] = (t, data[pos:pos + 3])
            pos += 3
        else:
            raise ValueError("tag de constant pool desconhecida %d" % t)
        i += 1

    def cls_name(idx):
        return cp[cp[idx][1]][1] if idx else None

    ci = ClassInfo()
    ci.flags, this_i, super_i, n_if = struct.unpack_from(">HHHH", data, pos)
    pos += 8
    ci.name = cls_name(this_i)
    ci.super = cls_name(super_i)
    for _ in range(n_if):
        (idx,) = struct.unpack_from(">H", data, pos)
        pos += 2
        ci.interfaces.append(cls_name(idx))

    want = {"Signature", "ConstantValue", "RuntimeVisibleAnnotations"}
    for kind, bucket in (("f", ci.fields), ("m", ci.methods)):
        (cnt,) = struct.unpack_from(">H", data, pos)
        pos += 2
        for _ in range(cnt):
            flags, name_i, desc_i = struct.unpack_from(">HHH", data, pos)
            pos += 6
            attrs, pos = _parse_attributes(data, pos, cp, want)
            ent = {
                "flags": flags,
                "name": cp[name_i][1],
                "desc": cp[desc_i][1],
                "sig": attrs.get("Signature"),
                "anns": attrs.get("RuntimeVisibleAnnotations", []),
            }
            if kind == "f" and "ConstantValue" in attrs:
                ent["const"] = _const_text(cp, attrs["ConstantValue"], ent["desc"])
            bucket.append(ent)
    attrs, pos = _parse_attributes(data, pos, cp, want)
    ci.signature = attrs.get("Signature")
    ci.annotations = attrs.get("RuntimeVisibleAnnotations", [])
    return ci


def _const_text(cp, idx, desc):
    ent = cp[idx]
    t = ent[0]
    if t == 3:
        v = struct.unpack(">i", ent[1])[0]
        if desc == "Z":
            return "true" if v else "false"
        if desc == "C":
            return repr(chr(v))
        return str(v)
    if t == 4:
        return repr(struct.unpack(">f", ent[1])[0])
    if t == 5:
        return str(struct.unpack(">q", ent[1])[0])
    if t == 6:
        return repr(struct.unpack(">d", ent[1])[0])
    if t == 8:
        s = cp[ent[1]][1]
        return json.dumps(s if len(s) <= 60 else s[:57] + "...", ensure_ascii=False)
    return None


# ---------------------------------------------------------------------------
# Tipos legíveis a partir de descritores / assinaturas genéricas
# ---------------------------------------------------------------------------
_BASE = {"B": "byte", "C": "char", "D": "double", "F": "float", "I": "int", "J": "long",
         "S": "short", "Z": "boolean", "V": "void"}


def _simple(internal: str) -> str:
    return internal.rsplit("/", 1)[-1].split("$")[-1]


def _parse_type(sig, i):
    c = sig[i]
    if c in _BASE:
        return _BASE[c], i + 1
    if c == "[":
        t, i = _parse_type(sig, i + 1)
        return t + "[]", i
    if c == "T":
        j = sig.index(";", i)
        return sig[i + 1:j], j + 1
    if c == "L":
        i += 1
        start = i
        name = ""
        while True:
            j = i
            while sig[j] not in "<;.":
                j += 1
            seg = sig[start:j]
            name = _simple(seg)
            ch = sig[j]
            if ch == "<":
                j += 1
                parts = []
                while sig[j] != ">":
                    if sig[j] == "*":
                        parts.append("?")
                        j += 1
                    elif sig[j] in "+-":
                        word = "? extends " if sig[j] == "+" else "? super "
                        t, j = _parse_type(sig, j + 1)
                        parts.append(word + t)
                    else:
                        t, j = _parse_type(sig, j)
                        parts.append(t)
                j += 1
                name += "<" + ", ".join(parts) + ">"
                ch = sig[j]
            if ch == ";":
                return name, j + 1
            i = j + 1  # '.': classe interna, continua
            start = i
    raise ValueError("assinatura inválida: %r em %d" % (sig, i))


def parse_method_types(sig: str):
    """'<T:...>(params)ret^throws' ou descritor -> (lista de params, retorno)."""
    i = 0
    if sig[0] == "<":
        i = 1
        while sig[i] != ">":
            i = sig.index(":", i)
            while sig[i] == ":":
                i += 1
                if sig[i] in "LT[":
                    _t, i = _parse_type(sig, i)
        i += 1
    assert sig[i] == "("
    i += 1
    params = []
    while sig[i] != ")":
        t, i = _parse_type(sig, i)
        params.append(t)
    ret, _ = _parse_type(sig, i + 1)
    return params, ret


def raw_param_key(desc: str) -> str:
    return desc[:desc.index(")") + 1]


def field_type(ent) -> str:
    return _parse_type(ent["sig"] or ent["desc"], 0)[0]


def _ann(anns, type_desc):
    for t, elems in anns:
        if t == type_desc:
            return elems
    return None


# ---------------------------------------------------------------------------
# Repositório de classes: jar do jogo + runtime do JDK (via jimage)
# ---------------------------------------------------------------------------
def _java_home_from_tool(tool: str):
    exe = shutil.which(tool)
    if exe:
        return Path(exe).resolve().parent.parent
    jh = os.environ.get("JAVA_HOME")
    return Path(jh) if jh else None


def find_tool(name: str):
    exe = shutil.which(name)
    if exe:
        return exe
    jh = os.environ.get("JAVA_HOME")
    if jh:
        for ext in ("", ".exe"):
            p = Path(jh) / "bin" / (name + ext)
            if p.exists():
                return str(p)
    return None


class ClassRepo:
    def __init__(self, jar_path: Path, jdk_cache: Path):
        self.jar = zipfile.ZipFile(jar_path)
        self.jar_names = set(self.jar.namelist())
        self.jdk_cache = jdk_cache
        self.cache: dict[str, ClassInfo | None] = {}
        self._jdk_tried: set[str] = set()
        self._modules = None
        self._jimage = find_tool("jimage")
        home = _java_home_from_tool("javap") or _java_home_from_tool("jimage")
        if home and (home / "lib" / "modules").exists():
            self._modules = home / "lib" / "modules"

    def in_jar(self, internal):
        return (internal + ".class") in self.jar_names

    def _jdk_path(self, internal):
        for mod in ("java.base", "java.desktop", "java.sql", "java.xml"):
            p = self.jdk_cache / mod / (internal + ".class")
            if p.exists():
                return p
        return None

    def extract_jdk(self, names):
        """Extrai do runtime do JDK (um único jimage) as classes ainda não vistas."""
        todo = [n for n in names if n not in self._jdk_tried and not self.in_jar(n) and not self._jdk_path(n)]
        self._jdk_tried.update(names)
        if not todo or not self._jimage or not self._modules:
            return
        self.jdk_cache.mkdir(parents=True, exist_ok=True)
        pat = "|".join(re.escape(n) for n in todo)
        subprocess.run([self._jimage, "extract", "--dir", str(self.jdk_cache),
                        "--include", "regex:.*/(%s)\\.class" % pat, str(self._modules)],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get(self, internal):
        if internal in self.cache:
            return self.cache[internal]
        ci = None
        try:
            if self.in_jar(internal):
                ci = parse_class(self.jar.read(internal + ".class"))
            else:
                p = self._jdk_path(internal)
                if p:
                    ci = parse_class(p.read_bytes())
        except Exception:
            ci = None
        self.cache[internal] = ci
        return ci

    def load_hierarchy(self, roots):
        """Carrega as classes e todos os ancestrais (puxando do JDK quando preciso)."""
        wave = list(roots)
        seen = set()
        while wave:
            self.extract_jdk([n for n in wave if not self.in_jar(n)])
            nxt = []
            for n in wave:
                if n in seen:
                    continue
                seen.add(n)
                ci = self.get(n)
                if not ci:
                    continue
                if ci.super:
                    nxt.append(ci.super)
                nxt.extend(ci.interfaces)
            wave = nxt


# ---------------------------------------------------------------------------
# Detecção das classes expostas (bytecode do Exposer via javap -c)
# ---------------------------------------------------------------------------
_INSN = re.compile(r"^\s+(\d+):\s+(\w+)\s*(.*)$")
_SET_EXPOSED_CLASS = re.compile(r"Method (?:[\w/$]+\.)?setExposed:\(Ljava/lang/Class;\)V")
_SET_EXPOSED_STATIC = re.compile(r"Method ([\w/$]+)\.setExposed:\(L[\w/$]*Exposer;\)V")
_GLOBAL_FUNCS = re.compile(r"Method (?:[\w/$]+\.)?exposeGlobalFunctions:\(Ljava/lang/Object;\)V")
_CLASS_CONST = re.compile(r"//\s*class\s+([\w/$]+)\s*$")
_INVOKESTATIC_SPECIAL = re.compile(r"Method ([\w/$]+)\.(expose\w+):")


def run_javap_c(javap, jar_path, class_names):
    """Roda `javap -c -p` em lote; devolve {classe(interna): [linhas]}."""
    if not class_names:
        return {}
    cmd = [javap, "-c", "-p", "-cp", str(jar_path)] + [n.replace("/", ".") for n in class_names]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = {}
    cur = None
    for line in proc.stdout.splitlines():
        if line.startswith("Compiled from"):
            cur = None
            continue
        if cur is None and line and not line[0].isspace():
            m = re.search(r"(?:class|interface|enum)\s+([\w.$]+)", line)
            if m:
                cur = m.group(1).replace(".", "/")
                out[cur] = []
                continue
        if cur is not None:
            out[cur].append(line)
    return out


def method_body(lines, header_re):
    """Linhas de instrução do primeiro método cujo cabeçalho casa com header_re."""
    body, inside = [], False
    for line in lines:
        if not inside:
            if re.match(r"^  \S", line) and re.search(header_re, line):
                inside = True
            continue
        if line.strip() == "" and body:
            break
        body.append(line)
    return body


def scan_expose_body(body):
    """Interpreta as instruções de um método de exposição.

    Devolve (classes expostas em ordem, helpers estáticos, objetos globais,
    chamadas LuaManager.expose*, classes só de debug).
    """
    classes, helpers, globals_, specials, debug_only = [], [], [], [], []
    last_ldc_class = None
    last_new = None
    skip_until = -1
    prev_debug_get = False
    prev_op = None
    for line in body:
        m = _INSN.match(line)
        if not m:
            continue
        off, op, rest = int(m.group(1)), m.group(2), m.group(3)
        in_debug = off < skip_until
        if op in ("ldc", "ldc_w"):
            cm = _CLASS_CONST.search(rest)
            last_ldc_class = cm.group(1) if cm else None
        elif op == "new":
            cm = _CLASS_CONST.search(rest)
            last_new = cm.group(1) if cm else None
        elif op == "getstatic":
            prev_debug_get = bool(re.search(r"Core\.debug:Z", rest))
        elif op == "ifeq" and prev_debug_get:
            target = re.search(r"(\d+)\s*$", rest.split("//")[0].strip())
            if target:
                skip_until = int(target.group(1))
        elif op == "invokevirtual":
            if _SET_EXPOSED_CLASS.search(rest):
                if last_ldc_class and not last_ldc_class.startswith("["):
                    (debug_only if in_debug else classes).append(last_ldc_class)
                last_ldc_class = None
            elif _GLOBAL_FUNCS.search(rest) and last_new:
                globals_.append(last_new)
        elif op == "invokestatic":
            sm = _SET_EXPOSED_STATIC.search(rest)
            if sm:
                if not in_debug:
                    helpers.append(sm.group(1))
            else:
                xm = _INVOKESTATIC_SPECIAL.search(rest)
                if xm and xm.group(2) in SPECIAL_CONSTANTS:
                    specials.append((xm.group(1), xm.group(2)))
        if op != "getstatic":
            prev_debug_get = prev_debug_get and False if op != "ifeq" else prev_debug_get
        prev_op = op
    return classes, helpers, globals_, specials, debug_only


def find_exposer(repo: ClassRepo):
    for cand in EXPOSER_CANDIDATES:
        if repo.in_jar(cand):
            return cand
    for n in sorted(repo.jar_names):
        if n.endswith(".class") and "Exposer" in n:
            ci = repo.get(n[:-6])
            if ci and ci.super == EXPOSER_SUPER:
                return ci.name
    raise RuntimeError("não encontrei a subclasse de LuaJavaClassExposer no jar")


def detect_exposure(repo: ClassRepo, jar_path: Path, javap: str):
    exposer = find_exposer(repo)
    texts = run_javap_c(javap, jar_path, [exposer])
    lines = texts.get(exposer)
    if lines is None:
        raise RuntimeError("javap não devolveu o bytecode de " + exposer)
    body = method_body(lines, r"\bexposeAll\(\)")
    classes, helpers, global_objs, specials, debug_only = scan_expose_body(body)
    all_classes = list(classes)
    done = set([exposer])
    queue = [h for h in helpers]
    while queue:
        wave = [h for h in dict.fromkeys(queue) if h not in done]
        queue = []
        if not wave:
            break
        done.update(wave)
        for cname, clines in run_javap_c(javap, jar_path, wave).items():
            hb = method_body(clines, r"\bsetExposed\(\S*Exposer\)")
            c2, h2, g2, _s2, d2 = scan_expose_body(hb)
            all_classes.extend(c2)
            global_objs.extend(g2)
            debug_only.extend(d2)
            queue.extend(h2)
    # classes usadas pelas constantes especiais (Keyboard/Mouse/Calendar)
    special_classes = {}
    if specials:
        owners = sorted({o for o, _m in specials})
        for oname, olines in run_javap_c(javap, jar_path, owners).items():
            for o, mname in specials:
                if o != oname:
                    continue
                sb = method_body(olines, r"\b" + mname + r"\(")
                for line in sb:
                    m = _INSN.match(line)
                    if m and m.group(2) in ("ldc", "ldc_w"):
                        cm = _CLASS_CONST.search(m.group(3))
                        if cm and not cm.group(1).endswith("/Class"):
                            special_classes[mname] = cm.group(1)
                            break
    ordered = list(dict.fromkeys(all_classes))
    return {
        "exposer": exposer,
        "classes": ordered,
        "global_objects": list(dict.fromkeys(global_objs)),
        "special_classes": special_classes,
        "debug_only": [c for c in dict.fromkeys(debug_only) if c not in ordered],
    }


# ---------------------------------------------------------------------------
# Modelagem: o que o Lua enxerga de cada classe (emula Class.getMethods/getFields)
# ---------------------------------------------------------------------------
def dotted(internal: str) -> str:
    return internal.replace("/", ".")


def _hidden(ent) -> bool:
    return _ann(ent["anns"], HIDDEN_ANN) is not None


def _ancestors(repo, ci):
    """Superclasses (do mais próximo para o mais distante)."""
    out = []
    cur = ci
    seen = set()
    while cur and cur.super and cur.super not in seen:
        seen.add(cur.super)
        s = repo.get(cur.super)
        if not s:
            break
        out.append(s)
        cur = s
    return out


def _all_interfaces(repo, ci, chain):
    out, seen = [], set()
    stack = [ci] + chain
    queue = []
    for c in stack:
        queue.extend(c.interfaces)
    while queue:
        n = queue.pop(0)
        if n in seen:
            continue
        seen.add(n)
        ic = repo.get(n)
        if ic:
            out.append(ic)
            queue.extend(ic.interfaces)
    return out


def visible_methods(repo, ci):
    """Métodos públicos (inclusive herdados) que o Lua enxerga: lista de (ent, declarante)."""
    chain = _ancestors(repo, ci)
    ifaces = _all_interfaces(repo, ci, chain)
    seen = set()
    out = []
    own_is_interface = bool(ci.flags & ACC_INTERFACE)
    for src in [ci] + chain + ifaces:
        if src.name == "java/lang/Object":
            continue
        src_is_iface = bool(src.flags & ACC_INTERFACE)
        for m in src.methods:
            f = m["flags"]
            if not f & ACC_PUBLIC or f & (ACC_BRIDGE | ACC_SYNTHETIC) or m["name"] in ("<init>", "<clinit>"):
                continue
            if src_is_iface and f & ACC_STATIC and src is not ci:
                continue  # estáticos de interface não são herdados
            key = (m["name"], raw_param_key(m["desc"]))
            if key in seen:
                continue
            seen.add(key)
            if _hidden(m):
                continue
            out.append((m, src))
    return out


def visible_static_fields(repo, ci):
    chain = _ancestors(repo, ci)
    ifaces = _all_interfaces(repo, ci, chain)
    seen = set()
    out = []
    for src in [ci] + chain + ifaces:
        for f in src.fields:
            fl = f["flags"]
            if not fl & ACC_PUBLIC or fl & ACC_SYNTHETIC or f["name"] in seen:
                continue
            seen.add(f["name"])
            if fl & ACC_STATIC and not _hidden(f):
                out.append((f, src))
    return out


def class_header(ci) -> str:
    f = ci.flags
    if f & ACC_ANNOTATION:
        kw = "@interface"
    elif f & ACC_INTERFACE:
        kw = "interface"
    elif f & ACC_ENUM:
        kw = "enum"
    elif f & ACC_ABSTRACT:
        kw = "abstract class"
    else:
        kw = "class"
    txt = "%s %s" % (kw, _simple(ci.name))
    if ci.super and ci.super not in ("java/lang/Object", "java/lang/Enum") and not f & ACC_INTERFACE:
        txt += " extends " + _simple(ci.super)
    if ci.interfaces:
        txt += (" extends " if f & ACC_INTERFACE else " implements ") + ", ".join(_simple(i) for i in ci.interfaces)
    return txt


def method_signature(name, ent, ctor_class=None):
    params, ret = parse_method_types(ent["sig"] or ent["desc"])
    if ent["flags"] & ACC_VARARGS and params and params[-1].endswith("[]"):
        params[-1] = params[-1][:-2] + "..."
    if ctor_class:
        ret = ctor_class
    return "%s %s(%s)" % (ret, name, ", ".join(params)), ret


def build_model(repo: ClassRepo, exposure: dict) -> dict:
    """Constrói as linhas (dicts no formato da tabela symbols)."""
    rows = []
    stats = {"classes": 0, "methods": 0, "fields": 0, "global_functions": 0, "missing_classes": []}
    seen_class_names = {}  # nome curto -> FQN (a primeira vence no Lua)
    collisions = []
    exposed = exposure["classes"]
    repo.load_hierarchy(exposed + exposure["global_objects"] + list(exposure["special_classes"].values()))

    for internal in exposed:
        ci = repo.get(internal)
        if not ci:
            stats["missing_classes"].append(internal)
            continue
        short = _simple(internal)
        fqn = dotted(internal)
        if short.startswith("$") or not short:
            continue
        if short in seen_class_names and seen_class_names[short] != fqn:
            # No Lua o nome curto global fica com a primeira classe; as demais só são
            # alcançáveis pelo caminho completo. No índice usamos 'Externa.Interna'
            # (ou o nome binário) para não misturar métodos de classes diferentes.
            collisions.append((short, seen_class_names[short], fqn))
            short = internal.rsplit("/", 1)[-1].replace("$", ".")
            if short in seen_class_names:
                short = fqn
        seen_class_names.setdefault(short, fqn)
        rows.append(dict(kind="class", name=short, owner=None, java_class=fqn,
                         signature=class_header(ci), returns=None, is_static=0, file=None))
        stats["classes"] += 1

        if not ci.flags & (ACC_ABSTRACT | ACC_INTERFACE):
            for m in ci.methods:
                if m["name"] == "<init>" and m["flags"] & ACC_PUBLIC and not m["flags"] & ACC_SYNTHETIC and not _hidden(m):
                    sig, ret = method_signature("new", m, ctor_class=short)
                    rows.append(dict(kind="method", name="new", owner=short, java_class=fqn,
                                     signature=sig, returns=ret, is_static=1, file=None))
                    stats["methods"] += 1
        for m, src in visible_methods(repo, ci):
            sig, ret = method_signature(m["name"], m)
            rows.append(dict(kind="method", name=m["name"], owner=short, java_class=fqn,
                             signature=sig, returns=ret, is_static=1 if m["flags"] & ACC_STATIC else 0,
                             file=None if src is ci else dotted(src.name)))
            stats["methods"] += 1
        for f, src in visible_static_fields(repo, ci):
            t = field_type(f)
            sig = "%s %s" % (t, f["name"])
            if f.get("const") is not None:
                sig += " = " + f["const"]
            rows.append(dict(kind="field", name=f["name"], owner=short, java_class=fqn,
                             signature=sig, returns=t, is_static=1,
                             file=None if src is ci else dotted(src.name)))
            stats["fields"] += 1

    # Constantes publicadas fora do mecanismo de classes (Keyboard, Mouse, Calendar)
    have = {(r["owner"], r["name"]) for r in rows if r["kind"] == "field"}
    for mname, cname in exposure["special_classes"].items():
        table, accept = SPECIAL_CONSTANTS[mname]
        ci = repo.get(cname)
        if not ci:
            continue
        if table not in seen_class_names:
            rows.append(dict(kind="class", name=table, owner=None, java_class=dotted(cname),
                             signature="constantes inteiras publicadas por LuaManager." + mname,
                             returns=None, is_static=0, file=None))
            seen_class_names[table] = dotted(cname)
            stats["classes"] += 1
        for f, src in visible_static_fields(repo, ci):
            if f["desc"] != "I" or not f["flags"] & ACC_FINAL or not accept(f["name"]):
                continue
            if (table, f["name"]) in have:
                continue
            have.add((table, f["name"]))
            sig = "int %s" % f["name"]
            if f.get("const") is not None:
                sig += " = " + f["const"]
            rows.append(dict(kind="field", name=f["name"], owner=table, java_class=dotted(cname),
                             signature=sig, returns="int", is_static=1, file=None))
            stats["fields"] += 1

    # Funções globais (@LuaMethod(global=true)) dos objetos globais
    for gobj in exposure["global_objects"]:
        gci = repo.get(gobj)
        if not gci:
            continue
        gchain = _ancestors(repo, gci)
        seen_sig = set()
        for src in [gci] + gchain:
            for m in src.methods:
                if not m["flags"] & ACC_PUBLIC or m["flags"] & (ACC_BRIDGE | ACC_SYNTHETIC):
                    continue
                ann = _ann(m["anns"], LUA_METHOD_ANN)
                if ann is None or not ann.get("global", False):
                    continue
                lua_name = ann.get("name") or m["name"]
                sig, ret = method_signature(lua_name, m)
                if (lua_name, sig) in seen_sig:
                    continue
                seen_sig.add((lua_name, sig))
                rows.append(dict(kind="global_function", name=lua_name, owner=None,
                                 java_class=dotted(src.name), signature=sig, returns=ret,
                                 is_static=0,
                                 file=None))
                stats["global_functions"] += 1
    stats["collisions"] = collisions
    return {"rows": rows, "stats": stats}


# ---------------------------------------------------------------------------
# Cache + entrada pública
# ---------------------------------------------------------------------------
def _cache_key(jar_path: Path) -> str:
    st = jar_path.stat()
    h = hashlib.sha1(("%d|%d|%d|%s" % (CACHE_VERSION, st.st_size, int(st.st_mtime), str(jar_path))).encode()).hexdigest()
    return h[:16]


def build_rows(game_dir, use_cache=True, cache_dir: Path | None = None, log=None):
    log = log or (lambda *_a: None)
    jar_path = Path(game_dir) / JAR_NAME
    if not jar_path.exists():
        raise FileNotFoundError("jar do jogo não encontrado: %s" % jar_path)
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_file = cache_dir / "java_symbols.json"
    key = _cache_key(jar_path)
    if use_cache and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("key") == key:
                log("cache de símbolos Java reaproveitado")
                return data["model"]
        except Exception:
            pass
    javap = find_tool("javap")
    if not javap:
        raise RuntimeError("javap não encontrado (instale o JDK ou defina JAVA_HOME)")
    t0 = time.time()
    repo = ClassRepo(jar_path, cache_dir / "jdk_classes")
    exposure = detect_exposure(repo, jar_path, javap)
    log("classes expostas: %d (%.1fs)" % (len(exposure["classes"]), time.time() - t0))
    model = build_model(repo, exposure)
    model["exposure"] = {k: v for k, v in exposure.items() if k != "classes"}
    model["exposure"]["class_count"] = len(exposure["classes"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"key": key, "model": model}, ensure_ascii=False), encoding="utf-8")
    log("modelo montado em %.1fs" % (time.time() - t0))
    return model


def extract(conn: sqlite3.Connection, game_dir, use_cache: bool = True, cache_dir=None, log=None) -> dict:
    """Preenche `symbols` (origin='java') e devolve as contagens."""
    model = build_rows(game_dir, use_cache=use_cache, cache_dir=cache_dir, log=log)
    conn.execute("DELETE FROM symbols WHERE origin='java'")
    conn.executemany(
        "INSERT INTO symbols(kind,name,owner,java_class,signature,returns,is_static,origin,file,line)"
        " VALUES(?,?,?,?,?,?,?,'java',?,NULL)",
        [(r["kind"], r["name"], r["owner"], r["java_class"], r["signature"], r["returns"],
          r["is_static"], r["file"]) for r in model["rows"]])
    conn.commit()
    st = model["stats"]
    return {"classes": st["classes"], "methods": st["methods"], "fields": st["fields"],
            "global_functions": st["global_functions"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game-dir", default=os.environ.get("PZ_GAME_DIR", DEFAULT_GAME_DIR))
    ap.add_argument("--db", required=True, help="sqlite de saída (criado a partir de schema.sql se não existir)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    t0 = time.time()
    counts = extract(conn, args.game_dir, use_cache=not args.no_cache,
                     log=lambda *a: print(*a, file=sys.stderr))
    conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('rebuild')")
    conn.commit()
    print(json.dumps(counts), "em %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
