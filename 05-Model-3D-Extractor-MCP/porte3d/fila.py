"""Fila da esteira de porte 3D: o ÚNICO escritor do estado dos objetos (ver planos/2026-10-12-esteira-de-porte-3d.md).

Os agentes nunca editam a fila: o orquestrador (ou a galeria) chama estas funções, e cada uma faz uma transição
validada. O estado fica em `fila/fila.json` (versionado, chaves ordenadas, indentação 1, UTF-8) e as saídas dos
agentes ficam em arquivos próprios, também versionados:

    fila/fila.json                               estado de todos os objetos
    fichas/<id>.json                             ficha do inspetor
    vereditos/<id>/rodada_<n>.json               veredito do crítico de cada rodada
    receitas/<id>.json                           receita atual
    receitas/historico/<id>/rodada_<n>.json      cópia da receita de cada rodada

Fluxo normal:  fila → em_inspecao → em_modelagem → em_critica → (retrabalho → em_modelagem → em_critica)×
→ aguardando_aprovacao → aprovado → publicado.   Saídas laterais: nao_portar (inspetor), reprovado (3 rodadas sem
nota 8), rejeitado (o usuário pediu para refazer; volta para retrabalho com a rodada zerada).

Para os testes, a pasta raiz muda com a variável de ambiente PORTE3D_FILA_DIR ou atribuindo `fila.RAIZ`.

Uso:  python -m porte3d.fila status | popular | proximos | mover | ficha | receita | veredito | decidir | reiniciar | ver
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import jsonschema

from . import acervo, receita as _receita

HERE = Path(__file__).resolve().parent
RAIZ = Path(os.environ["PORTE3D_FILA_DIR"]) if os.environ.get("PORTE3D_FILA_DIR") else HERE

SCHEMA_FICHA = json.loads((HERE / "ficha.schema.json").read_text(encoding="utf-8"))
SCHEMA_VEREDITO = json.loads((HERE / "veredito.schema.json").read_text(encoding="utf-8"))

VERSAO = 1
RODADAS_MAX = 3
NOTA_MINIMA = 8
TRAVA_VELHA_S = 120      # uma trava mais antiga que isso é de um processo que morreu

ESTADOS = ("fila", "em_inspecao", "nao_portar", "em_modelagem", "em_critica", "retrabalho", "reprovado",
           "aguardando_aprovacao", "aprovado", "rejeitado", "publicado")

# estado -> estados para os quais `mover` pode ir. Voltar para `fila` só com `reiniciar`.
TRANSICOES = {
    "fila": {"em_inspecao"},
    "em_inspecao": {"nao_portar", "em_modelagem"},
    "nao_portar": set(),
    "em_modelagem": {"em_critica"},
    "em_critica": {"retrabalho", "reprovado", "aguardando_aprovacao"},
    "retrabalho": {"em_modelagem"},
    "reprovado": set(),
    "aguardando_aprovacao": {"aprovado", "rejeitado"},
    "aprovado": {"publicado"},
    "rejeitado": {"retrabalho"},
    "publicado": set(),
}
# estados que carregam um `motivo` (o resto zera o motivo ao entrar)
COM_MOTIVO = {"nao_portar", "reprovado"}

# peso de cada categoria na prioridade: o que aparece em toda casa vem primeiro
# valor de CustomName que alguns tiles do jogo trazem no lugar do nome (ex.: rádios): é como se não houvesse nome
NOME_VAZIO = {"", "customname"}
PESO_CATEGORIA = {"cozinha": 400, "eletrodomesticos": 400, "moveis": 300, "banheiro": 200, "containers": 100}
_GRAVIDADE = {"grave": 0, "media": 1, "leve": 2}


class FilaErro(ValueError):
    """Qualquer recusa da fila (transição inválida, arquivo fora do contrato, objeto inexistente)."""


class TransicaoInvalida(FilaErro):
    pass


class ArquivoInvalido(FilaErro):
    pass


class ObjetoInexistente(FilaErro):
    pass


# ---------------------------------------------------------------- caminhos e arquivos

def _raiz() -> Path:
    return Path(RAIZ)


def caminho_fila() -> Path:
    return _raiz() / "fila" / "fila.json"


def caminho_ficha(id: str) -> Path:
    return _raiz() / "fichas" / f"{id}.json"


def caminho_receita(id: str) -> Path:
    return _raiz() / "receitas" / f"{id}.json"


def caminho_veredito(id: str, rodada: int) -> Path:
    return _raiz() / "vereditos" / id / f"rodada_{rodada}.json"


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _vazio() -> dict:
    return {"versao": VERSAO, "objetos": {}}


def _tentar(fn, vezes: int = 40):
    """O Windows recusa abrir ou trocar um arquivo que outro processo está usando naquele instante."""
    for i in range(vezes):
        try:
            return fn()
        except PermissionError:
            if i == vezes - 1:
                raise
            time.sleep(0.05)


def _ler() -> dict:
    p = caminho_fila()
    if not p.exists():
        return _vazio()
    return json.loads(_tentar(lambda: p.read_text(encoding="utf-8")))


def _gravar(dados: dict) -> None:
    p = caminho_fila()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"fila.{os.getpid()}.tmp")
    texto = json.dumps(dados, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    tmp.write_bytes(texto.encode("utf-8"))      # bytes: o fim de linha é sempre \n, também no Windows
    _tentar(lambda: os.replace(tmp, p))


@contextlib.contextmanager
def _trava(espera: float = 30.0):
    """Trava de arquivo: dois processos não escrevem a fila ao mesmo tempo."""
    lock = caminho_fila().with_name("fila.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > TRAVA_VELHA_S:
                    lock.unlink()
                    continue
            except OSError:
                continue
            if time.monotonic() - t0 > espera:
                raise FilaErro(f"a fila está travada por outro processo ({lock})")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


@contextlib.contextmanager
def _transacao():
    """Lê a fila com a trava, entrega o dicionário para alterar e grava no fim (se nada deu erro)."""
    with _trava():
        dados = _ler()
        yield dados
        _gravar(dados)


def _gravar_json(destino: Path, conteudo: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(conteudo, ensure_ascii=False, indent=1) + "\n"
    destino.write_bytes(texto.encode("utf-8"))


def _ler_json(caminho: str | Path, o_que: str) -> dict:
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ArquivoInvalido(f"{o_que}: arquivo não encontrado: {caminho}") from None
    except json.JSONDecodeError as e:
        raise ArquivoInvalido(f"{o_que}: JSON inválido em {caminho}: {e}") from None


def _validar_esquema(dado: dict, esquema: dict, o_que: str) -> None:
    erros = [f"{'/'.join(map(str, e.absolute_path)) or '(raiz)'}: {e.message}"
             for e in jsonschema.Draft202012Validator(esquema).iter_errors(dado)]
    if erros:
        raise ArquivoInvalido(f"{o_que} fora do esquema:\n" + "\n".join(erros))


# ---------------------------------------------------------------- leitura

def carregar() -> dict:
    """O estado inteiro: {"versao": 1, "objetos": {id: registro}}."""
    return _ler()


def objetos(estado: str | None = None) -> list[dict]:
    """Os registros (ordenados por id), todos ou só os de um estado."""
    if estado is not None and estado not in ESTADOS:
        raise FilaErro(f"estado desconhecido: {estado}")
    todos = carregar()["objetos"]
    return [todos[i] for i in sorted(todos) if estado is None or todos[i]["estado"] == estado]


def obter(id: str) -> dict:
    try:
        return carregar()["objetos"][id]
    except KeyError:
        raise ObjetoInexistente(f"objeto não está na fila: {id}") from None


def proximos(estado: str = "fila", n: int = 10) -> list[dict]:
    """Os `n` próximos do estado: maior prioridade primeiro, depois id."""
    return sorted(objetos(estado), key=lambda o: (-o["prioridade"], o["id"]))[:n]


def resumo() -> dict:
    """Quantos objetos há em cada estado (todos os estados aparecem, mesmo com zero)."""
    cont = {e: 0 for e in ESTADOS}
    for o in carregar()["objetos"].values():
        cont[o["estado"]] += 1
    return cont


# ---------------------------------------------------------------- transições

def _registro(dados: dict, id: str) -> dict:
    try:
        return dados["objetos"][id]
    except KeyError:
        raise ObjetoInexistente(f"objeto não está na fila: {id}") from None


def _aplicar(o: dict, para: str, nota: str | None = None) -> None:
    """Muda o estado do registro, validando a tabela de transições, e anota no histórico."""
    if para not in ESTADOS:
        raise FilaErro(f"estado desconhecido: {para}")
    de = o["estado"]
    if para not in TRANSICOES[de]:
        validos = ", ".join(sorted(TRANSICOES[de])) or "nenhum (só `reiniciar`)"
        raise TransicaoInvalida(f"{o['id']}: {de} → {para} não é permitido (de {de} vai para: {validos})")
    if de == "rejeitado" and para == "retrabalho":
        o["rodada"] = 0                  # o usuário pediu para refazer: recomeça a contagem, o histórico fica
    _entrar(o, de, para, nota)


def _entrar(o: dict, de: str, para: str, nota: str | None) -> None:
    o["estado"] = para
    o["motivo"] = nota if para in COM_MOTIVO else None
    o["historico"].append({"quando": _agora(), "de": de, "para": para, "nota": nota})


def mover(id: str, para: str, nota: str | None = None) -> dict:
    """Transição manual. Para `nao_portar` e `reprovado`, a nota vira o motivo."""
    with _transacao() as dados:
        o = _registro(dados, id)
        _aplicar(o, para, nota)
        return dict(o)


def reiniciar(id: str) -> dict:
    """Volta o objeto para a fila (de qualquer estado), com a rodada zerada. O histórico e as notas ficam."""
    with _transacao() as dados:
        o = _registro(dados, id)
        if o["estado"] == "fila":
            raise TransicaoInvalida(f"{id}: já está na fila")
        de = o["estado"]
        o["rodada"] = 0
        _entrar(o, de, "fila", "reiniciado")
        return dict(o)


def decidir(id: str, decisao: str, comentario: str | None = None) -> dict:
    """Decisão do usuário na galeria: `aprovado` ou `rejeitado`. O comentário fica no registro. Um objeto
    rejeitado espera em `rejeitado` até alguém movê-lo para `retrabalho` (isso zera a rodada)."""
    if decisao not in ("aprovado", "rejeitado"):
        raise FilaErro(f"decisão precisa ser 'aprovado' ou 'rejeitado', veio {decisao!r}")
    with _transacao() as dados:
        o = _registro(dados, id)
        if o["estado"] != "aguardando_aprovacao":
            raise TransicaoInvalida(f"{id}: só se decide objeto em aguardando_aprovacao (está em {o['estado']})")
        o["comentario_usuario"] = comentario
        _aplicar(o, decisao, comentario)     # `rejeitado` fica visível; o orquestrador manda para retrabalho
        return dict(o)


# ---------------------------------------------------------------- entregas dos agentes

def registrar_ficha(id: str, caminho: str | Path) -> dict:
    """Ficha do inspetor: valida, guarda em fichas/ e move o objeto (nao_portar ou em_modelagem)."""
    ficha = _ler_json(caminho, "ficha")
    _validar_esquema(ficha, SCHEMA_FICHA, "ficha")
    if ficha["objeto"] != id:
        raise ArquivoInvalido(f"ficha de '{ficha['objeto']}' não é do objeto '{id}'")
    with _transacao() as dados:
        o = _registro(dados, id)
        if o["estado"] != "em_inspecao":
            raise TransicaoInvalida(f"{id}: a ficha só entra com o objeto em em_inspecao (está em {o['estado']})")
        _gravar_json(caminho_ficha(id), ficha)
        if ficha["decisao"] == "nao_portar":
            _aplicar(o, "nao_portar", ficha["motivo"])
        else:
            _aplicar(o, "em_modelagem", "ficha registrada")
        return dict(o)


def registrar_receita(id: str, caminho: str | Path) -> dict:
    """Receita do modelador: valida, guarda em receitas/ (e no histórico da rodada) e manda para a crítica."""
    r = _ler_json(caminho, "receita")
    try:
        _receita.validar(r)
    except _receita.ReceitaInvalida as e:
        raise ArquivoInvalido(f"receita inválida:\n{e}") from None
    if r.get("id") != id:
        raise ArquivoInvalido(f"receita de '{r.get('id')}' não é do objeto '{id}'")
    with _transacao() as dados:
        o = _registro(dados, id)
        if o["estado"] != "em_modelagem":
            raise TransicaoInvalida(f"{id}: a receita só entra com o objeto em em_modelagem (está em {o['estado']})")
        if o["rodada"] >= RODADAS_MAX:
            raise TransicaoInvalida(f"{id}: já passou das {RODADAS_MAX} rodadas")
        o["rodada"] += 1
        _gravar_json(caminho_receita(id), r)
        _gravar_json(caminho_receita(id).parent / "historico" / id / f"rodada_{o['rodada']}.json", r)
        _aplicar(o, "em_critica", f"receita da rodada {o['rodada']}")
        return dict(o)


def _defeito_principal(v: dict) -> str:
    """O defeito mais grave do veredito em uma linha: 'parte: tipo (nivel, vista) — onde'."""
    defeitos = sorted(v["defeitos"], key=lambda d: _GRAVIDADE[d["gravidade"]])      # estável: empate fica na ordem
    if defeitos:
        d = defeitos[0]
        return f"{d['parte']}: {d['tipo']} ({d['nivel']}, {d['vista']}) — {d['onde']}"
    ruins = [p for p in v["pecas"] if p["situacao"] != "ok"]
    if ruins:
        return f"{ruins[0]['nome']}: {ruins[0]['situacao']}"
    return f"nota abaixo de {NOTA_MINIMA} sem defeito listado ({v['observacao'].strip()[:80] or 'sem observação'})"


def registrar_veredito(id: str, caminho: str | Path) -> dict:
    """Veredito do crítico: valida, guarda e decide: aguardando_aprovacao (as duas notas ≥ 8), retrabalho ou reprovado."""
    v = _ler_json(caminho, "veredito")
    _validar_esquema(v, SCHEMA_VEREDITO, "veredito")
    if v["objeto"] != id:
        raise ArquivoInvalido(f"veredito de '{v['objeto']}' não é do objeto '{id}'")
    with _transacao() as dados:
        o = _registro(dados, id)
        if o["estado"] != "em_critica":
            raise TransicaoInvalida(f"{id}: o veredito só entra com o objeto em em_critica (está em {o['estado']})")
        if v["rodada"] != o["rodada"]:
            raise ArquivoInvalido(f"veredito da rodada {v['rodada']}, mas o objeto está na rodada {o['rodada']}")
        _gravar_json(caminho_veredito(id, v["rodada"]), v)
        arte, real = v["nota_arte"], v["nota_realista"]
        o["notas"].append({"rodada": v["rodada"], "arte": arte, "realista": real})
        resumo_notas = f"rodada {v['rodada']}: arte {arte:g}, realista {real:g}"
        if arte >= NOTA_MINIMA and real >= NOTA_MINIMA:
            _aplicar(o, "aguardando_aprovacao", resumo_notas)
        elif o["rodada"] < RODADAS_MAX:
            _aplicar(o, "retrabalho", resumo_notas)
        else:
            _aplicar(o, "reprovado", _defeito_principal(v))
        return dict(o)


# ---------------------------------------------------------------- popular a fila a partir do acervo

def _slug(texto: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (texto or "").lower()).strip("_")


def _arredondar(v, casas: int = 2):
    if isinstance(v, float):
        return round(v, casas) + 0.0
    if isinstance(v, list):
        return [_arredondar(x, casas) for x in v]
    if isinstance(v, dict):
        return {k: _arredondar(x, casas) for k, x in v.items() if k != "nome"}
    return v


def _assinatura(db: sqlite3.Connection, sprite: str) -> str | None:
    """A geometria do sprite arredondada a 1 cm, como texto comparável. None se não há peça aproveitável."""
    formas = acervo.formas(db, sprite)
    if not formas:
        return None
    return json.dumps(_arredondar(formas), sort_keys=True)


def _props(db: sqlite3.Connection, nome: str) -> dict:
    return {k: v for k, v in db.execute("select key, value from tile_props where name=?", (nome,))}


def _agrupar(candidatos: list[dict]) -> list[list[dict]]:
    """Sprites do mesmo (tileset, CustomName, GroupName) viram um objeto. Se a mesma direção aparece mais de uma
    vez (balcões em módulos, estantes), cada repetição abre outro objeto, na ordem do índice."""
    grupos: dict[tuple, list[list[dict]]] = {}
    ordem: list[list[dict]] = []
    for c in sorted(candidatos, key=lambda c: (c["tileset"], c["idx"])):
        if c["facing"] not in acervo.DIRECOES:
            ordem.append([c])               # sem Facing: cada sprite é um objeto
            continue
        chave = (c["tileset"], c["custom_name"], c["group_name"])
        for obj in grupos.setdefault(chave, []):
            if all(s["facing"] != c["facing"] for s in obj):
                obj.append(c)
                break
        else:
            novo = [c]
            grupos[chave].append(novo)
            ordem.append(novo)
    return ordem


def planejar(categorias: list[str], db: sqlite3.Connection, existentes: dict | None = None) -> tuple[list[dict], dict]:
    """Os registros novos (ainda sem gravar, na ordem de criação) e as contagens do que ficou de fora."""
    existentes = existentes if existentes is not None else {}
    marcas = ",".join("?" * len(categorias))
    linhas = db.execute(
        f"select t.name, t.tileset, t.idx, t.category from tiles t where t.category in ({marcas}) "
        "and exists (select 1 from geometry g where g.name = t.name) "
        "and exists (select 1 from sprites s where s.name = t.name and s.scale = 2) "
        "and not exists (select 1 from tile_props p where p.name = t.name and p.key = 'SpriteGridPos')",
        list(categorias)).fetchall()
    cands = []
    for nome, tileset, idx, cat in linhas:
        p = _props(db, nome)
        custom = p.get("CustomName")
        cands.append({"name": nome, "tileset": tileset, "idx": idx, "categoria": cat, "facing": p.get("Facing"),
                      "custom_name": None if (custom or "").strip().lower() in NOME_VAZIO else custom,
                      "group_name": p.get("GroupName")})
    ignorados = {"sem_vista_S": 0, "ja_na_fila": 0}
    ja_usados = {s for o in existentes.values() for s in o["sprites"].values()}
    ids = set(existentes)
    novos: list[dict] = []
    for obj in _agrupar(cands):
        rep = next((s for s in obj if s["facing"] == "S"), None)
        if rep is None and obj[0]["facing"] not in acervo.DIRECOES:
            rep = obj[0]                   # sem Facing: o próprio sprite é a vista de frente
        if rep is None:
            ignorados["sem_vista_S"] += 1
            continue
        if rep["name"] in ja_usados:
            ignorados["ja_na_fila"] += 1
            continue
        sprites = acervo.direcoes(db, rep["name"])
        base = _slug(f"{rep['custom_name'] or rep['name']} {rep['group_name'] or ''}")
        tent = [base, f"{base}_{_slug(rep['tileset'])}", f"{base}_{_slug(rep['tileset'])}_{rep['idx']}"]
        id = next((t for t in tent if t not in ids), tent[-1])
        ids.add(id)
        novos.append({
            "id": id, "familia": _slug(rep["custom_name"]) or _slug(rep["tileset"]), "forma_de": None,
            "sprites": sprites, "categoria": rep["categoria"], "tileset": rep["tileset"],
            "custom_name": rep["custom_name"], "group_name": rep["group_name"],
            "material": acervo.material(db, rep["name"]), "prioridade": 0, "estado": "fila", "rodada": 0,
            "notas": [], "historico": [{"quando": _agora(), "de": None, "para": "fila", "nota": "criado por popular"}],
            "motivo": None, "comentario_usuario": None,
        })
    # variantes: mesmo CustomName e mesma geometria (a 1 cm) com outro GroupName reaproveitam a forma do primeiro
    formas: dict[tuple, str] = {}
    familias_novas = {n["familia"] for n in novos}
    for o in existentes.values():
        if o["forma_de"] is None and o["familia"] in familias_novas and o["sprites"].get("S"):
            sig = _assinatura(db, o["sprites"]["S"])
            if sig is not None:
                formas.setdefault((o["custom_name"] or o["tileset"], sig), o["id"])
    for o in novos:
        sig = _assinatura(db, o["sprites"]["S"]) if "S" in o["sprites"] else None
        if sig is None:
            continue
        chave = (o["custom_name"] or o["tileset"], sig)      # sem nome, só o mesmo tileset conta como mesma família
        if chave in formas:
            o["forma_de"] = formas[chave]
        else:
            formas[chave] = o["id"]
    tamanho = {}
    for o in list(existentes.values()) + novos:
        tamanho[o["familia"]] = tamanho.get(o["familia"], 0) + 1
    for o in novos:
        o["prioridade"] = PESO_CATEGORIA.get(o["categoria"], 0) + tamanho[o["familia"]]
    return novos, ignorados


def popular(categorias: list[str], limite: int | None = None, db: sqlite3.Connection | None = None) -> list[str]:
    """Põe na fila os objetos do acervo (escala 2, com geometria, de um só tile) nas categorias dadas.
    Devolve os ids criados. Com `limite`, só os de maior prioridade (a forma-base de uma variante escolhida
    entra junto, mesmo que passe do limite)."""
    if isinstance(categorias, str):
        categorias = [c for c in categorias.split(",") if c.strip()]
    categorias = [c.strip() for c in categorias]
    if not categorias:
        raise FilaErro("informe ao menos uma categoria")
    fechar = db is None
    db = db or acervo.abrir()
    try:
        with _transacao() as dados:
            novos, ign = planejar(categorias, db, dados["objetos"])
            popular.ignorados = ign
            por_id = {o["id"]: o for o in novos}
            ordem = sorted(novos, key=lambda o: (-o["prioridade"], o["forma_de"] or o["id"],
                                                 o["forma_de"] is not None, o["id"]))
            escolhidos: list[str] = []
            for o in ordem:
                if limite is not None and len(escolhidos) >= limite:
                    break
                base = o["forma_de"]
                if base in por_id and base not in escolhidos:
                    escolhidos.append(base)
                if o["id"] not in escolhidos:
                    escolhidos.append(o["id"])
            for i in escolhidos:
                dados["objetos"][i] = por_id[i]
            return escolhidos
    finally:
        if fechar:
            db.close()


popular.ignorados = {}


# ---------------------------------------------------------------- linha de comando

def _linha(o: dict) -> str:
    forma = f"  (forma de {o['forma_de']})" if o["forma_de"] else ""
    return f"{o['id']:<44} {o['prioridade']:>4}  {o['estado']:<20} rodada {o['rodada']}{forma}"


def _cmd_ver(id: str) -> None:
    o = obter(id)
    print(json.dumps(o, ensure_ascii=False, indent=1, sort_keys=True))
    arquivos = [caminho_ficha(id), caminho_receita(id)] + sorted((_raiz() / "vereditos" / id).glob("rodada_*.json"))
    for a in arquivos:
        print(("existe   " if a.exists() else "não há   ") + str(a))


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m porte3d.fila", description="Fila da esteira de porte 3D")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("popular", help="põe na fila objetos do acervo")
    p.add_argument("--categorias", required=True, help="separadas por vírgula: cozinha,eletrodomesticos")
    p.add_argument("--limite", type=int)
    sub.add_parser("status", help="quantos objetos em cada estado")
    p = sub.add_parser("proximos", help="próximos de um estado, por prioridade")
    p.add_argument("-n", type=int, default=10)
    p.add_argument("--estado", default="fila", choices=ESTADOS)
    p = sub.add_parser("mover", help="transição manual")
    p.add_argument("id")
    p.add_argument("estado", choices=ESTADOS)
    p.add_argument("--nota")
    for nome, ajuda in (("ficha", "registra a ficha do inspetor"), ("receita", "registra a receita do modelador"),
                        ("veredito", "registra o veredito do crítico")):
        p = sub.add_parser(nome, help=ajuda)
        p.add_argument("id")
        p.add_argument("arquivo")
    p = sub.add_parser("decidir", help="decisão do usuário")
    p.add_argument("id")
    p.add_argument("decisao", choices=("aprovado", "rejeitado"))
    p.add_argument("--comentario")
    p = sub.add_parser("reiniciar", help="volta o objeto para a fila")
    p.add_argument("id")
    p = sub.add_parser("ver", help="mostra o registro e os arquivos de um objeto")
    p.add_argument("id")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "popular":
            criados = popular(a.categorias, a.limite)
            todos = {o["id"]: o for o in objetos()}
            n_var = sum(1 for i in criados if todos[i]["forma_de"])
            print(f"{len(criados)} objetos criados ({len(criados) - n_var} formas novas, {n_var} variantes de cor); "
                  f"fora: {popular.ignorados.get('sem_vista_S', 0)} sem vista S, "
                  f"{popular.ignorados.get('ja_na_fila', 0)} já na fila")
            for o in sorted((todos[i] for i in criados), key=lambda o: (-o["prioridade"], o["id"]))[:15]:
                print(_linha(o))
        elif a.cmd == "status":
            c = resumo()
            for e in ESTADOS:
                print(f"{e:<22} {c[e]:>5}")
            print(f"{'total':<22} {sum(c.values()):>5}")
        elif a.cmd == "proximos":
            for o in proximos(a.estado, a.n):
                print(_linha(o))
        elif a.cmd == "mover":
            print(_linha(mover(a.id, a.estado, a.nota)))
        elif a.cmd == "ficha":
            print(_linha(registrar_ficha(a.id, a.arquivo)))
        elif a.cmd == "receita":
            print(_linha(registrar_receita(a.id, a.arquivo)))
        elif a.cmd == "veredito":
            o = registrar_veredito(a.id, a.arquivo)
            print(_linha(o) + (f"\nmotivo: {o['motivo']}" if o["motivo"] else ""))
        elif a.cmd == "decidir":
            print(_linha(decidir(a.id, a.decisao, a.comentario)))
        elif a.cmd == "reiniciar":
            print(_linha(reiniciar(a.id)))
        elif a.cmd == "ver":
            _cmd_ver(a.id)
    except (FilaErro, FileNotFoundError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
