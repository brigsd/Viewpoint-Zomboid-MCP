"""Acervo do jogo para o porte 3D: quadros, geometria, direções e materiais de um sprite (ver CONTRATO.md).

Tudo o que sai daqui já está na convenção da receita: metros, x = leste (X do jogo), y = norte (−Z do jogo),
z = cima (Y do jogo). A origem é o centro do tile, no chão.

Fatos conferidos sobre o `tileGeometry.txt` (comparando a projeção das formas com o desenho de milhares de sprites):

- Toda forma é descrita no referencial local, girada por `rotate` e depois movida por `translate`:
  `ponto_do_jogo = translate + R · ponto_local`.
- `rotate = AxBxC` (1/10000 de grau) vale `R = Rx(A) · Ry(B) · Rz(C)` com as matrizes de rotação usuais
  (sentido positivo da regra da mão direita nos eixos do jogo, que também formam um sistema destro), ou seja,
  o Z é aplicado primeiro. Um giro `B` em torno do Y do jogo é o mesmo giro `+B` em torno do `z` da receita.
- `cylinder`: o eixo do cilindro é o Z local e a origem é o centro do cilindro (o `translate` fica no meio da altura).
- `polygon`: os pontos são sempre `(x, y)` no plano local z = 0 (o `plane = ...` é só uma etiqueta; quem coloca o
  polígono em pé ou deitado é o `rotate`). A espessura do jogo é zero; aqui vira 1 cm.
- `box` com `min`/`max` locais; sem espessura própria, o `translate` desloca a caixa inteira.

Peças com giro: se o giro, depois de encaixar a peça numa orientação de eixos (múltiplos de 90°), sobra só um
giro em torno de `z`, a peça sai alinhada aos eixos com `rot = [0, 0, θ]`. Se não, a peça sai sem giro de eixos e
com `rot = [rx, ry, rz]` em graus no padrão Euler XYZ do Blender (`R = Rz · Ry · Rx`), em torno do centro da peça.
"""
from __future__ import annotations

import itertools
import math
import re
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ACERVO_DB = HERE.parent / "acervo" / "data" / "acervo.sqlite"
FW, FH = 128, 256
DIRECOES = ("S", "E", "N", "W")
ESPESSURA_POLIGONO = 0.01      # m
CASAS = 4                      # casas decimais das medidas (0,1 mm)

# jogo (X, Y, Z) -> receita (x, y, z) = (X, −Z, Y); é uma rotação própria (det = +1)
_M = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)


def abrir(path: str | Path | None = None) -> sqlite3.Connection:
    """Conexão com o banco do acervo (por padrão acervo/data/acervo.sqlite)."""
    p = Path(path) if path else ACERVO_DB
    if not p.exists():
        raise FileNotFoundError(f"acervo não encontrado: {p}")
    return sqlite3.connect(p)


def _raiz(db: sqlite3.Connection) -> Path:
    """Pasta dos PNGs: a mesma do arquivo do banco (os caminhos de sprites.png são relativos a ela)."""
    for _, nome, arq in db.execute("pragma database_list"):
        if nome == "main" and arq:
            return Path(arq).resolve().parent
    return ACERVO_DB.parent


# ---------------------------------------------------------------- quadros

def quadro(db: sqlite3.Connection, nome: str) -> np.ndarray | None:
    """Quadro RGBA uint8 (256, 128, 4) do sprite, com o recorte no lugar. None se não houver sprite de escala 2."""
    row = db.execute("select png, offset_x, offset_y, scale from sprites where name=?", (nome,)).fetchone()
    if not row or row[3] != 2:
        return None
    png, ox, oy, _ = row
    q = Image.new("RGBA", (FW, FH))
    im = Image.open(_raiz(db) / png).convert("RGBA")
    q.paste(im, (ox or 0, oy or 0))
    return np.asarray(q).copy()


def bleed(rgba: np.ndarray, n: int = 12) -> np.ndarray:
    """Espalha a cor das bordas do desenho `n` pixels para os vizinhos transparentes (que ficam opacos).
    Os cantos arredondados viram quina e a textura não puxa transparência na borda.
    É o `bleed` do teste_adesivo, mas sem dar a volta no quadro (deslocamento com zeros, não `np.roll`)."""
    out = rgba.copy()
    solid = out[..., 3] >= 200
    h, w = solid.shape
    for _ in range(n):
        grow = np.zeros_like(solid)
        acc = np.zeros((h, w, 3), np.float32)
        cnt = np.zeros((h, w), np.float32)
        sp = np.pad(solid, 1)
        cp = np.pad(out[..., :3].astype(np.float32), ((1, 1), (1, 1), (0, 0)))
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            sh = sp[1 - dy:1 - dy + h, 1 - dx:1 - dx + w]
            col = cp[1 - dy:1 - dy + h, 1 - dx:1 - dx + w]
            add = sh & ~solid
            acc[add] += col[add]
            cnt[add] += 1
            grow |= add
        if not grow.any():
            break
        out[grow, :3] = (acc[grow] / cnt[grow, None]).astype(np.uint8)
        out[grow, 3] = 255
        solid |= grow
    return out


def espelhado(db: sqlite3.Connection, a: str, b: str) -> float:
    """Semelhança (0..1) entre o sprite `a` e o sprite `b` virado de lado (espelho horizontal em torno do
    centro do tile). Perto de 1 = `b` é cópia espelhada de `a` (típico de E/W em relação a S/N)."""
    qa, qb = quadro(db, a), quadro(db, b)
    if qa is None or qb is None:
        return 0.0
    qb = qb[:, ::-1]
    ma, mb = qa[..., 3] >= 128, qb[..., 3] >= 128
    uniao = ma | mb
    if not uniao.any():
        return 0.0
    dif = np.abs(qa[..., :3].astype(np.int16) - qb[..., :3].astype(np.int16)).mean(-1) / 255.0
    dif = np.where(ma & mb, dif, 1.0)
    return float(1.0 - dif[uniao].mean())


# ---------------------------------------------------------------- geometria

def _rot(eixo: str, graus: float) -> np.ndarray:
    t = math.radians(graus)
    c, s = math.cos(t), math.sin(t)
    if eixo == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if eixo == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _r_jogo(rx: float, ry: float, rz: float) -> np.ndarray:
    """R do jogo para `rotate = rx x ry x rz` (1/10000 de grau): Rx · Ry · Rz."""
    return _rot("x", rx / 1e4) @ _rot("y", ry / 1e4) @ _rot("z", rz / 1e4)


def _orientacoes() -> list[np.ndarray]:
    """As 24 rotações que levam eixos em eixos (matrizes de permutação com sinal e det +1)."""
    out = []
    for perm in itertools.permutations(range(3)):
        for sinais in itertools.product((1, -1), repeat=3):
            m = np.zeros((3, 3))
            for i, (j, s) in enumerate(zip(perm, sinais)):
                m[i, j] = s
            if round(np.linalg.det(m)) == 1:
                out.append(m)
    return out


_ORIENT = _orientacoes()


def _euler_xyz(r: np.ndarray) -> list[float]:
    """Ângulos [rx, ry, rz] em graus com R = Rz · Ry · Rx (Euler XYZ do Blender)."""
    sy = -r[2, 0]
    if abs(sy) < 0.999999:
        a = math.atan2(r[2, 1], r[2, 2])
        b = math.asin(sy)
        c = math.atan2(r[1, 0], r[0, 0])
    else:  # travamento de gimbal
        a = math.atan2(-r[1, 2], r[1, 1])
        b = math.copysign(math.pi / 2, sy)
        c = 0.0
    return [math.degrees(a), math.degrees(b), math.degrees(c)]


def _candidatos(rr: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Pares (S, Q) com Rr = Q · S: S leva eixos em eixos e Q é só um giro em torno de z (do menor para o maior
    ângulo); por último, o caso geral S = I, Q = Rr."""
    achados = []
    for s in _ORIENT:
        q = rr @ s.T
        if q[2, 2] > 0.99995 and abs(q[2, 0]) < 1e-2 and abs(q[2, 1]) < 1e-2:
            ang = math.degrees(math.atan2(q[1, 0], q[0, 0]))
            achados.append((abs(ang), s, q))
    achados.sort(key=lambda t: t[0])
    return [(s, q) for _, s, q in achados] + [(np.eye(3), rr)]


def _rot_peca(q: np.ndarray) -> list[float] | None:
    """`rot` da receita para o giro Q (None se for desprezível)."""
    e = [round(v, 2) + 0.0 for v in _euler_xyz(q)]
    return None if all(abs(v) < 0.05 for v in e) else e


def _r(v: float) -> float:
    return round(float(v), CASAS) + 0.0


def _parse_raw(raw: str | None) -> dict:
    d = {}
    for linha in (raw or "").split("\n")[2:]:
        if "=" in linha:
            k, v = (s.strip() for s in linha.split("=", 1))
            d[k] = v
    return d


def _num(v: float | None) -> float:
    return float(v) if v is not None else 0.0


def _caixa(row, s: np.ndarray, q: np.ndarray, mt: np.ndarray):
    lo = np.array([_num(row["min_x"]), _num(row["min_y"]), _num(row["min_z"])]) / 1e4
    hi = np.array([_num(row["max_x"]), _num(row["max_y"]), _num(row["max_z"])]) / 1e4
    centro = _M @ ((lo + hi) / 2)
    meio = np.abs(_M) @ ((hi - lo) / 2)        # meias medidas no referencial da receita
    c_s = s @ centro
    meio_s = np.abs(s) @ meio
    cf = mt + q @ c_s
    mn, mx = cf - meio_s, cf + meio_s
    if np.any(np.round(mx - mn, CASAS) <= 0):
        return None, "caixa sem espessura"
    p = {"forma": "caixa", "min": [_r(v) for v in mn], "max": [_r(v) for v in mx]}
    rot = _rot_peca(q)
    if rot:
        p["rot"] = rot
    return p, None


def _cilindro(row, s: np.ndarray, q: np.ndarray, mt: np.ndarray):
    d = _parse_raw(row["raw"])
    try:
        r1, r2, h = (float(d[k]) / 1e4 for k in ("radius1", "radius2", "height"))
    except (KeyError, ValueError):
        return None, "cilindro sem raio/altura no raw"
    if h <= 0 or max(r1, r2) <= 0:
        return None, "cilindro com medida zero"
    a_s = s @ (_M @ np.array([0.0, 0.0, 1.0]))   # eixo do cilindro (Z local do jogo) na receita
    i = int(np.argmax(np.abs(a_s)))
    if abs(a_s[i]) < 0.999:
        return None, "eixo do cilindro fora dos eixos"
    cf = mt                                         # a origem é o centro do cilindro (S·0 = 0)
    sentido = 1.0 if a_s[i] > 0 else -1.0
    r_base, r_topo = (r1, r2) if sentido > 0 else (r2, r1)   # radius1 fica no −Z local
    base = cf.copy()
    base[i] -= h / 2
    p = {"forma": "cilindro", "centro": [_r(v) for v in base], "raio": _r(r_base),
         "altura": _r(h), "eixo": "xyz"[i]}
    if abs(r_topo - r_base) > 1e-6:
        p["raio_topo"] = _r(r_topo)
    if p["raio"] <= 0:
        return None, "cilindro com raio zero na base"
    rot = _rot_peca(q)
    if rot:
        p["rot"] = rot
    return p, None


def _poligono(row, s: np.ndarray, q: np.ndarray, mt: np.ndarray):
    d = _parse_raw(row["raw"])
    try:
        pts = [tuple(float(v) / 1e4 for v in par.split("x")) for par in d["points"].split()]
    except (KeyError, ValueError):
        return None, "polígono sem pontos legíveis"
    if len(pts) < 3:
        return None, "polígono com menos de 3 pontos"
    e = ESPESSURA_POLIGONO / 2
    # pontos (x, y) no plano local z = 0 do jogo; na receita local isso é (u, 0, v) com a espessura em y
    local = np.array([[u, 0.0, v] for u, v in pts])
    ps = local @ s.T
    normal = s @ np.array([0.0, 1.0, 0.0])
    i = int(np.argmax(np.abs(normal)))
    if abs(normal[i]) < 0.999 or i == 2:
        return None, "polígono deitado (normal vertical), sem prisma equivalente"
    eixo = "xy"[i]
    h_idx = 1 - i                                   # coordenada horizontal que sobra
    lo, hi = ps.min(0).copy(), ps.max(0).copy()
    lo[i] -= e
    hi[i] += e
    c_s = (lo + hi) / 2
    cf = mt + q @ c_s
    perfil = [[float(p[h_idx] - c_s[h_idx] + cf[h_idx]), float(p[2] - c_s[2] + cf[2])] for p in ps]
    # tira pontos repetidos seguidos e deixa o contorno anti-horário (como nas receitas à mão)
    limpo = []
    for pt in perfil:
        if not limpo or math.dist(pt, limpo[-1]) > 1e-6:
            limpo.append(pt)
    if len(limpo) > 1 and math.dist(limpo[0], limpo[-1]) <= 1e-6:
        limpo.pop()
    if len(limpo) < 3:
        return None, "polígono degenerado"
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(limpo, limpo[1:] + limpo[:1])) / 2
    if abs(area) < 1e-8:
        return None, "polígono sem área"
    if area < 0:
        limpo.reverse()
    p = {"forma": "prisma", "perfil": [[_r(a), _r(z)] for a, z in limpo], "eixo": eixo,
         "de": _r(cf[i] - e), "ate": _r(cf[i] + e)}
    rot = _rot_peca(q)
    if rot:
        p["rot"] = rot
    return p, None


def _converter(row) -> tuple[dict | None, str | None]:
    """Uma linha de `geometry` -> (peça da receita sem nome, motivo de descarte)."""
    forma = row["shape"]
    conv = {"box": _caixa, "cylinder": _cilindro, "polygon": _poligono}.get(forma)
    if conv is None:
        return None, f"forma '{forma}' não suportada"
    mt = _M @ (np.array([_num(row["tx"]), _num(row["ty"]), _num(row["tz"])]) / 1e4)
    rr = _M @ _r_jogo(_num(row["rx"]), _num(row["ry"]), _num(row["rz"])) @ _M.T
    motivo = None
    for s, q in _candidatos(rr):
        p, motivo = conv(row, s, q, mt)
        if p is not None:
            return p, None
    return None, motivo


def _placa_de_sombra(p: dict) -> bool:
    """Caixa fina e plana, no chão, cobrindo boa parte do tile: a sombra do jogo, não é o objeto."""
    if p["forma"] != "caixa":
        return False
    (x0, y0, z0), (x1, y1, z1) = p["min"], p["max"]
    rot = p.get("rot")
    if rot and (abs(rot[0]) > 0.5 or abs(rot[1]) > 0.5):
        return False
    return (z1 - z0) <= 0.03 and z0 <= 0.001 and (x1 - x0) * (y1 - y0) >= 0.5


def formas(db: sqlite3.Connection, nome: str, ignoradas: list | None = None) -> list[dict]:
    """Geometria do jogo do sprite como peças da receita (`forma_0`, `forma_1`, ...), em metros, eixos da receita.

    Tem `box` (com translate e rotate), `cylinder` e `polygon` (prisma de 1 cm). A placa de sombra no chão é
    descartada (a não ser que seja a única forma, como num tapete). Se `ignoradas` for uma lista, recebe
    `(índice da forma no jogo, motivo)` de cada forma que não virou peça."""
    cur = db.cursor()
    cur.row_factory = sqlite3.Row
    rows = cur.execute("select * from geometry where name=? order by shape_idx", (nome,)).fetchall()
    conv = []
    for row in rows:
        p, motivo = _converter(row)
        if p is None:
            if ignoradas is not None:
                ignoradas.append((row["shape_idx"], motivo))
        else:
            conv.append((row["shape_idx"], p))
    sem_placa = [(i, p) for i, p in conv if not _placa_de_sombra(p)]
    if sem_placa and len(sem_placa) < len(conv):
        if ignoradas is not None:
            ignoradas += [(i, "placa de sombra no chão") for i, p in conv if _placa_de_sombra(p)]
        conv = sem_placa
    out = []
    for k, (_, p) in enumerate(conv):
        out.append({"nome": f"forma_{k}", **p})
    return out


# ---------------------------------------------------------------- direções

def _props(db: sqlite3.Connection, nome: str) -> dict:
    return {k: v for k, v in db.execute("select key, value from tile_props where name=?", (nome,))}


def direcoes(db: sqlite3.Connection, nome: str) -> dict:
    """Sprites do mesmo objeto nas outras direções: {"S":..,"E":..,"N":..,"W":..} (só as que existem).
    Mesmo tileset, mesmo CustomName e GroupName, e o `Facing` diz a direção. Sem `Facing`: {"S": nome}."""
    p = _props(db, nome)
    facing = p.get("Facing")
    if facing not in DIRECOES:
        return {"S": nome}
    row = db.execute("select tileset, idx from tiles where name=?", (nome,)).fetchone()
    if not row:
        return {facing: nome}
    tileset, idx = row
    res = {facing: nome}
    cands = {}
    for n, i in db.execute("select name, idx from tiles where tileset=? and name!=?", (tileset, nome)):
        q = _props(db, n)
        if (q.get("Facing") in DIRECOES and q.get("CustomName") == p.get("CustomName")
                and q.get("GroupName") == p.get("GroupName") and q.get("SpriteGridPos") == p.get("SpriteGridPos")
                and q["Facing"] != facing and db.execute(
                    "select 1 from sprites where name=? and scale=2", (n,)).fetchone()):
            cands.setdefault(q["Facing"], []).append((abs(i - idx), i, n))
    for f, lista in cands.items():
        res[f] = min(lista)[2]
    return {f: res[f] for f in DIRECOES if f in res}


# ---------------------------------------------------------------- material

_FIXADORES = {"nails", "screws"}
_TIPOS = {
    "madeira": {"wood", "wood_solid", "log", "plank", "planks"},
    "tecido": {"fabric", "cloth", "upholstery", "leather", "carpet"},
    "metal": {"electric", "fridge", "steel", "pipes", "plumbing", "mechanical", "aluminumscrap"},
}


def _tipo_de(valor: str) -> str:
    v = valor.strip().lower()
    for tipo, nomes in _TIPOS.items():
        if v in nomes:
            return tipo
    if v.startswith("metal") or "metal" in v:
        return "metal"
    return "liso"


def material(db: sqlite3.Connection, nome: str) -> str:
    """Tipo de material da receita (madeira | metal | tecido | liso) a partir de Material, Material2, Material3
    e MaterialType. Fixadores (Nails, Screws) não contam: olha o próximo."""
    p = _props(db, nome)
    for chave in ("Material", "Material2", "Material3", "MaterialType"):
        v = p.get(chave)
        if v and v.strip().lower() not in _FIXADORES:
            return _tipo_de(v)
    return "liso"


# ---------------------------------------------------------------- receita

def _slug(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_") or "objeto"


def sugerir_receita(db: sqlite3.Connection, nome_S: str) -> dict:
    """Receita válida a partir do sprite de frente: direções, material e peças da geometria do jogo."""
    from . import receita as _receita
    sprites = direcoes(db, nome_S)
    if "S" not in sprites:
        sprites = {"S": nome_S, **sprites}
    mat = material(db, nome_S)
    pecas = formas(db, sprites["S"])
    r = {
        "versao": 1,
        "id": _slug(nome_S),
        "sprites": sprites,
        "tras": "N" if "N" in sprites else "simetrico",
        "material": mat,
        "pecas": pecas,
        "arte": {"modo": "adesivo"},
        "realista": {"materiais": {mat: {"tipo": mat}}},
    }
    _receita.validar(r)
    return r


def deslocamento_tras(db: sqlite3.Connection, nome_S: str, nome_N: str) -> list[float]:
    """Quanto o objeto virado para N está deslocado, no tile, em relação ao objeto virado para S girado 180°.
    O jogo posiciona cada direção por conta própria (ex.: a geladeira N tem translate), então o desenho N não é
    exatamente o desenho S girado no centro do tile. Devolve [dx, dy] em metros, nos eixos da receita, a somar
    depois de girar 180°: p_N = giro180(p_S) + [dx, dy]. Usa o centro da caixa envolvente das peças (caixas e
    cilindros); [0, 0] se faltar geometria em uma das direções."""
    def centro(nome):
        lo, hi = [], []
        for p in formas(db, nome):
            if p["forma"] == "caixa":
                lo.append(p["min"]); hi.append(p["max"])
            elif p["forma"] == "cilindro":
                c, r = np.array(p["centro"], float), float(p["raio"])
                lo.append((c - r).tolist()); hi.append((c + r).tolist())
        if not lo:
            return None
        return (np.min(lo, axis=0) + np.max(hi, axis=0)) / 2
    cs, cn = centro(nome_S), centro(nome_N)
    if cs is None or cn is None:
        return [0.0, 0.0]
    return [round(float(cn[0] + cs[0]), 4), round(float(cn[1] + cs[1]), 4)]
