"""Materiais procedurais do porte 3D (rodam DENTRO do Blender; só usam bpy e numpy).

No nível "realista" só a COR BASE do material importa: ela é assada numa textura de cor (o carregador de
modelos do jogo só aceita map_Kd). Por isso cada material é uma rede de nós que produz Base Color a partir
de TexCoord **Object** (metros). As malhas de um objeto são juntadas num objeto só, na origem, então
coordenada de objeto = coordenada da receita.

Uso:
    mat = criar("tampo", "madeira", (88, 82, 78), eixos=("x", "y", "z"), faixa=(-0.45, 0.45),
                superficie=0.72, tabuas=3, semente=1)

Limite conhecido: uma textura "esticada" num eixo (veio da madeira, risco do inox) só aparece como linha nas
faces que contêm esse eixo; na face de topo/cabeça da peça vira ruído fino. Use um material por orientação
de peça quando isso importar (a madeira já faz anéis de verdade nas cabeças).
"""
import math

import bpy
import numpy as np

_AX = {"x": 0, "y": 1, "z": 2}


def _lin(c):
    """sRGB 0..255 -> linear 0..1."""
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


class _Rede:
    """Ajudante para montar a rede de nós com poucas linhas."""

    def __init__(self, mat, semente):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.N, self.Lk = self.nt.nodes, self.nt.links
        self.bsdf = self.N["Principled BSDF"]
        self.tc = self.N.new("ShaderNodeTexCoord")
        self.sep = self.N.new("ShaderNodeSeparateXYZ")
        self.Lk.new(self.tc.outputs["Object"], self.sep.inputs["Vector"])
        self.semente = float(semente)
        self._k = 0

    # -- aritmética escalar
    def M(self, op, a, b=None, c=None):
        n = self.N.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.Lk.new(v, n.inputs[i])
        return n.outputs[0]

    def coord(self, eixo):
        return self.sep.outputs[_AX[eixo]]

    def rng(self, v, lo, hi, fmin=0.0, fmax=1.0, suave=False):
        mr = self.N.new("ShaderNodeMapRange")
        if suave:
            mr.interpolation_type = "SMOOTHSTEP"
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = fmin, fmax
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = lo, hi
        self.Lk.new(v, mr.inputs["Value"])
        return mr.outputs["Result"]

    # -- cor
    def mult(self, col, fac):
        mm = self.N.new("ShaderNodeMix")
        mm.data_type, mm.blend_type = "RGBA", "MULTIPLY"
        mm.inputs["Factor"].default_value = 1.0
        self.Lk.new(col, mm.inputs["A"])
        if isinstance(fac, (int, float)):
            mm.inputs["B"].default_value = (fac, fac, fac, 1)
        elif isinstance(fac, tuple):
            mm.inputs["B"].default_value = (*fac, 1)
        else:
            self.Lk.new(fac, mm.inputs["B"])
        return mm.outputs["Result"]

    def misturar(self, a, b, fac):
        """Mistura de cor: a quando fac=0, b quando fac=1."""
        mm = self.N.new("ShaderNodeMix")
        mm.data_type, mm.blend_type = "RGBA", "MIX"
        if isinstance(fac, (int, float)):
            mm.inputs["Factor"].default_value = fac
        else:
            self.Lk.new(fac, mm.inputs["Factor"])
        self.Lk.new(a, mm.inputs["A"])
        if isinstance(b, tuple):
            mm.inputs["B"].default_value = (*b, 1)
        else:
            self.Lk.new(b, mm.inputs["B"])
        return mm.outputs["Result"]

    def cor_base(self, rgb):
        n = self.N.new("ShaderNodeRGB")
        n.outputs[0].default_value = (*_lin(rgb), 1)
        return n.outputs[0]

    # -- ruído com escala por eixo (esticar = escala pequena no eixo do comprimento)
    def ruido(self, escala, detalhe=2.0, rugosidade=0.5, saida="Fac"):
        """`escala` = (sx, sy, sz) em ciclos por metro (aprox.); deslocamento sorteado pela semente."""
        self._k += 1
        mp = self.N.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = tuple(escala)
        r = np.random.RandomState(int(self.semente * 977 + self._k * 31) % (2 ** 31))
        mp.inputs["Location"].default_value = tuple(r.uniform(0, 500, 3))
        self.Lk.new(self.tc.outputs["Object"], mp.inputs["Vector"])
        nz = self.N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 1.0
        nz.inputs["Detail"].default_value = detalhe
        nz.inputs["Roughness"].default_value = rugosidade
        self.Lk.new(mp.outputs["Vector"], nz.inputs["Vector"])
        return nz.outputs[saida]

    def esc(self, base, eixo=None, valor=None):
        """Vetor de escala: `base` em todos os eixos, `valor` no eixo `eixo`."""
        v = [base] * 3
        if eixo is not None:
            v[_AX[eixo]] = valor
        return v

    def saida(self, col, rugosidade, metalico=0.0):
        self.Lk.new(col, self.bsdf.inputs["Base Color"])
        self.bsdf.inputs["Roughness"].default_value = rugosidade
        # Metallic fica em 0: o bake DIFFUSE COLOR escurece pela fração metálica, e só a cor base importa
        self.bsdf.inputs["Metallic"].default_value = 0.0


# ------------------------------------------------------------------------------------------ madeira
def _madeira(R, cor, comp, atrav, prof, faixa, superficie, tabuas, lado, espacamento=0.0055):
    """Madeira com anéis de crescimento de verdade: cada tábua tem o próprio centro de tronco (sorteado),
    inclinação, espaçamento de anel e tom — nenhuma tábua repete a outra. Os anéis são linhas finas escuras
    (lenho tardio) sobre fundo claro, e não listras de seno. Poros finos esticados no comprimento."""
    M, N, Lk = R.M, R.N, R.Lk
    pl, pa, pb = R.coord(comp), R.coord(atrav), R.coord(prof)
    lo, hi = faixa
    larg = float(hi - lo)
    if tabuas:
        idx = M("FLOOR", M("MULTIPLY", M("SUBTRACT", pa, lo), tabuas / larg))
    else:
        idx = M("ADD", 0.0, 0.0)
    rnd = []
    for k in range(2):                                   # 6 números sorteados por tábua
        wn = N.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "1D"
        Lk.new(M("ADD", idx, R.semente * 13.7 + k * 0.37), wn.inputs["W"])
        sc = N.new("ShaderNodeSeparateColor")
        Lk.new(wn.outputs["Color"], sc.inputs["Color"])
        rnd += [sc.outputs[i] for i in range(3)]
    r0, r1, r2, r3, r4, r5 = rnd
    w = larg / tabuas if tabuas else min(0.6, max(0.06, 3.0 * larg))   # peça única: tronco um pouco além da peça
    # centro do tronco: ao lado da tábua (às vezes dentro dela -> arcos "catedral"), um pouco inclinado
    if tabuas:
        base_a = M("MULTIPLY_ADD", M("ADD", idx, 0.5), w, lo)
    else:
        base_a = (lo + hi) / 2.0
    ca = M("ADD", M("ADD", base_a, M("MULTIPLY", M("SUBTRACT", r0, 0.5), w * 1.6)),
           M("MULTIPLY", pl, M("MULTIPLY", M("SUBTRACT", r1, 0.5), 0.05)))
    # o centro fica atrás da face principal (lado=+1: face em cima/frente; -1: face do lado oposto)
    cb = M("ADD", M("SUBTRACT", superficie, M("MULTIPLY", M("MULTIPLY_ADD", r2, 0.22, 0.02), float(lado))),
           M("MULTIPLY", pl, M("MULTIPLY", M("SUBTRACT", r3, 0.5), 0.12)))
    da, db = M("SUBTRACT", pa, ca), M("SUBTRACT", pb, cb)
    dist = M("SQRT", M("ADD", M("MULTIPLY", da, da), M("MULTIPLY", db, db)))
    # anéis levemente tortos (ruído lento ao longo do comprimento)
    nz = R.ruido(R.esc(6.0, comp, 1.2), detalhe=3.0)
    dist = M("ADD", dist, M("MULTIPLY", M("SUBTRACT", nz, 0.5), 0.012))
    sp = M("MULTIPLY_ADD", r4, espacamento * 0.6, espacamento * 0.7)
    aneis = M("FRACT", M("DIVIDE", dist, sp))
    ramp = N.new("ShaderNodeValToRGB")
    base = _lin(cor) * 1.05                       # compensa o escurecimento médio dos anéis
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*(base * 1.06), 1)
    els[1].position, els[1].color = 1.0, (*(base * 1.04), 1)
    for pos, f in ((0.55, 1.0), (0.80, 0.80), (0.88, 0.70)):
        e = els.new(pos)
        e.color = (*(base * f), 1)
    Lk.new(aneis, ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    # poros/fibras: ruído fino esticado no comprimento
    fib = R.ruido(R.esc(140.0, comp, 3.0), detalhe=2.0)
    col = R.mult(col, R.rng(fib, 0.90, 1.07, 0.3, 0.7))
    col = R.mult(col, R.rng(r5, 0.88, 1.08))              # tom próprio de cada tábua
    if tabuas:                                           # junta entre tábuas
        fr = M("PINGPONG", M("MULTIPLY", M("SUBTRACT", pa, lo), tabuas / larg), 0.5)
        col = R.mult(col, R.rng(fr, 0.4, 1.0, 0.0, 0.015))
    big = R.ruido((3.0, 3.0, 3.0), detalhe=2.0)
    col = R.mult(col, R.rng(big, 0.92, 1.06, 0.3, 0.7))   # manchas de uso
    R.saida(col, 0.65)


# ------------------------------------------------------------------------------------------ metal
def _metal(R, cor, comp, atrav, prof, escovado):
    """Chapa de metal pintada (geladeira, fogão): casca de laranja bem sutil, riscos verticais fracos,
    sujeira/escurecimento perto do chão (z perto de 0) e lascas minúsculas. Se escovado (cinza médio):
    aço escovado, com fios finos ao longo do `comp`."""
    M = R.M
    col = R.cor_base(cor)
    z = R.coord("z")
    if escovado:
        fios = R.ruido(R.esc(1100.0, comp, 3.0), detalhe=1.0, rugosidade=0.7)      # fios finíssimos
        col = R.mult(col, R.rng(fios, 0.90, 1.10, 0.25, 0.75))
        fios2 = R.ruido(R.esc(160.0, comp, 2.5), detalhe=2.0)                      # faixas mais largas
        col = R.mult(col, R.rng(fios2, 0.955, 1.045, 0.25, 0.75))
        mancha = R.ruido((4.0, 4.0, 4.0), detalhe=2.0)
        col = R.mult(col, R.rng(mancha, 0.94, 1.05, 0.3, 0.7))
        gz = R.rng(z, 1.0, 0.0, 0.0, 0.18, suave=True)
        col = R.misturar(col, R.mult(col, (0.62, 0.60, 0.56)), M("MULTIPLY", gz, 0.30))
        R.saida(col, 0.38, 0.0)
        return
    casca = R.ruido((650.0, 650.0, 650.0), detalhe=2.0)                            # casca de laranja
    col = R.mult(col, R.rng(casca, 0.982, 1.014, 0.3, 0.7))
    risco = R.ruido(R.esc(300.0, "z", 7.0), detalhe=2.0)                           # riscos verticais fracos
    col = R.mult(col, R.rng(risco, 0.985, 1.008, 0.3, 0.7))
    grande = R.ruido((2.2, 2.2, 2.2), detalhe=2.0)
    col = R.mult(col, R.rng(grande, 0.975, 1.02, 0.3, 0.7))
    po = R.ruido((1200.0, 1200.0, 1200.0), detalhe=1.0)                            # pó/granulado fino
    col = R.mult(col, R.rng(po, 0.985, 1.008, 0.3, 0.7))
    # sujeira perto do chão, escorrida em riscos verticais
    escorre = R.ruido(R.esc(35.0, "z", 4.0), detalhe=2.0)
    gz = R.rng(z, 1.0, 0.0, 0.0, 0.34, suave=True)
    g = M("MULTIPLY", gz, R.rng(escorre, 0.35, 1.0, 0.25, 0.75))
    sujo = R.rng(R.ruido((7.0, 7.0, 7.0), detalhe=3.0), 0.55, 1.0, 0.3, 0.7)
    g = M("MULTIPLY", g, sujo)
    col = R.misturar(col, R.mult(col, (0.84, 0.80, 0.72)), M("MULTIPLY", g, 0.55))
    # lascas minúsculas (pontos esparsos que mostram a chapa/primer por baixo)
    vo = R.N.new("ShaderNodeTexVoronoi")
    vo.feature = "F1"
    vo.inputs["Scale"].default_value = 70.0
    mp = R.N.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (R.semente * 3.1, R.semente * 1.7, R.semente * 2.3)
    R.Lk.new(R.tc.outputs["Object"], mp.inputs["Vector"])
    R.Lk.new(mp.outputs["Vector"], vo.inputs["Vector"])
    sc = R.N.new("ShaderNodeSeparateColor")
    R.Lk.new(vo.outputs["Color"], sc.inputs["Color"])
    cel = R.rng(vo.outputs["Distance"], 1.0, 0.0, 0.0, 0.07, suave=True)          # 1 no centro da célula
    sel = R.rng(sc.outputs[0], 0.0, 1.0, 0.955, 0.975)                             # só ~4% das células
    mpn = R.ruido((900.0, 900.0, 900.0), detalhe=1.0)
    irreg = R.rng(mpn, 0.0, 1.0, 0.40, 0.55)
    lasca = M("MULTIPLY", M("MULTIPLY", cel, sel), irreg)
    col = R.misturar(col, R.mult(col, (0.50, 0.50, 0.50)), M("MULTIPLY", lasca, 0.8))
    R.saida(col, 0.35, 0.0)


# ------------------------------------------------------------------------------------------ tecido
def _tecido(R, cor, comp, atrav, prof):
    """Tecido de trama simples: dois fios de ~1,8 mm, cada fio com tom próprio, ondulação leve, penugem fina e
    variação suave de tom em escala grande. A trama é calculada nos dois eixos que ficam NO PLANO de cada face
    (escolhidos pela normal em coordenadas de objeto): na face de `prof` usa (comp, atrav); na face de `atrav`
    usa (comp, prof); na face de `comp` usa (atrav, prof). Assim toda face mostra tecido, não só risco."""
    M, N, Lk = R.M, R.N, R.Lk
    p = 0.0018

    def tom_fio(i, k):
        wn = N.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "1D"
        Lk.new(M("ADD", i, R.semente * 5.3 + k), wn.inputs["W"])
        sc = N.new("ShaderNodeSeparateColor")
        Lk.new(wn.outputs["Color"], sc.inputs["Color"])
        return R.rng(sc.outputs[0], 0.90, 1.10)

    def trama(eu, ev, k):
        """Fator de brilho (~0,6..1,3) da trama nos eixos `eu` e `ev`."""
        pu, pv = R.coord(eu), R.coord(ev)
        ond_u = R.ruido((45.0, 45.0, 45.0), detalhe=1.0)
        ond_v = R.ruido((45.0, 45.0, 45.0), detalhe=1.0)
        uu = M("ADD", M("MULTIPLY", pu, 1.0 / p), M("MULTIPLY", M("SUBTRACT", ond_u, 0.5), 0.9))
        vv = M("ADD", M("MULTIPLY", pv, 1.0 / p), M("MULTIPLY", M("SUBTRACT", ond_v, 0.5), 0.9))
        iu, iv = M("FLOOR", uu), M("FLOOR", vv)
        fu, fv = M("FRACT", uu), M("FRACT", vv)
        soma = M("ADD", iu, iv)
        par = M("SUBTRACT", soma, M("MULTIPLY", M("FLOOR", M("MULTIPLY", soma, 0.5)), 2.0))   # 0/1 sem sinal
        su = M("SINE", M("MULTIPLY", fu, math.pi))
        sv = M("SINE", M("MULTIPLY", fv, math.pi))
        # fio que corre ao longo de `ev` (par=1): redondo no sentido `eu`, cai nas pontas
        pf = M("MULTIPLY", M("POWER", su, 0.7), M("MULTIPLY_ADD", sv, 0.30, 0.70))
        pt = M("MULTIPLY", M("POWER", sv, 0.7), M("MULTIPLY_ADD", su, 0.30, 0.70))
        prof_v = M("ADD", pt, M("MULTIPLY", par, M("SUBTRACT", pf, pt)))
        t_a, t_b = tom_fio(iu, 0.11 + k), tom_fio(iv, 0.57 + k)
        tom = M("ADD", t_b, M("MULTIPLY", par, M("SUBTRACT", t_a, t_b)))
        return M("MULTIPLY", R.rng(prof_v, 0.62, 1.34), tom)

    pares = {}
    for k, nome_n in enumerate((comp, atrav, prof)):       # eixo da normal -> os dois eixos do plano
        restantes = [e for e in (comp, atrav, prof) if e != nome_n]
        pares[nome_n] = trama(restantes[0], restantes[1], 3.0 * k)
    sepn = N.new("ShaderNodeSeparateXYZ")                  # normal em coordenadas de objeto
    Lk.new(R.tc.outputs["Normal"], sepn.inputs["Vector"])
    nx, ny, nz_ = (M("ABSOLUTE", sepn.outputs[i]) for i in range(3))
    an = {"x": nx, "y": ny, "z": nz_}
    ordem = ["x", "y", "z"]
    sx = M("MULTIPLY", M("GREATER_THAN", M("SUBTRACT", an["x"], an["y"]), 0.0),
           M("GREATER_THAN", M("SUBTRACT", an["x"], an["z"]), 0.0))
    sy = M("MULTIPLY", M("SUBTRACT", 1.0, sx), M("GREATER_THAN", M("SUBTRACT", an["y"], an["z"]), 0.0))
    sz = M("SUBTRACT", M("SUBTRACT", 1.0, sx), sy)
    peso = {"x": sx, "y": sy, "z": sz}
    fator = None
    for e in ordem:
        termo = M("MULTIPLY", pares[e], peso[e])
        fator = termo if fator is None else M("ADD", fator, termo)
    col = R.cor_base(cor)
    col = R.mult(col, fator)
    pen = R.ruido((900.0, 900.0, 900.0), detalhe=3.0, rugosidade=0.6)                  # penugem
    col = R.mult(col, R.rng(pen, 0.92, 1.07, 0.3, 0.7))
    fibr = R.ruido(R.esc(300.0, comp, 40.0), detalhe=2.0)                              # fibras soltas
    col = R.mult(col, R.rng(fibr, 0.96, 1.03, 0.3, 0.7))
    mid = R.ruido((26.0, 26.0, 26.0), detalhe=2.0)
    col = R.mult(col, R.rng(mid, 0.97, 1.03, 0.3, 0.7))                                # manchado leve
    big = R.ruido((2.5, 2.5, 2.5), detalhe=2.0)
    col = R.mult(col, R.rng(big, 0.94, 1.05, 0.3, 0.7))                                # uso em escala grande
    R.saida(col, 0.95)


# ------------------------------------------------------------------------------------------ liso
def _liso(R, cor):
    """Cor chapada de tinta/plástico com variação suave em escala grande e ruído fraco."""
    col = R.cor_base(cor)
    col = R.mult(col, R.rng(R.ruido((2.0, 2.0, 2.0), detalhe=2.0), 0.965, 1.03, 0.3, 0.7))
    col = R.mult(col, R.rng(R.ruido((14.0, 14.0, 14.0), detalhe=2.0), 0.985, 1.015, 0.3, 0.7))
    col = R.mult(col, R.rng(R.ruido((400.0, 400.0, 400.0), detalhe=1.0), 0.985, 1.012, 0.3, 0.7))
    R.saida(col, 0.5)


def _cinza_medio(cor):
    c = np.asarray(cor, float)
    return (c.max() - c.min()) <= 22 and c.mean() <= 205


def criar(nome, tipo, cor, eixos=("x", "y", "z"), faixa=(-0.5, 0.5), superficie=0.0, tabuas=0,
          semente=0, lado=1, acabamento=None):
    """Cria o material procedural `tipo` (madeira | metal | tecido | liso) com cor base `cor` (sRGB 0..255).

    eixos      = (comprimento, atravessado, profundidade): direção do veio/comprimento da peça, o eixo em que
                 as tábuas se enfileiram e a normal da face principal.
    faixa      = (mín, máx) da peça ao longo de `atravessado` (as tábuas dividem esse intervalo).
    superficie = coordenada da face principal ao longo de `profundidade` (o centro dos anéis fica atrás dela).
    tabuas     = número de tábuas (0 = peça única).
    semente    = faz peças diferentes ficarem diferentes.
    lado       = +1 se a face principal é a de maior coordenada em `profundidade`, -1 se é a de menor.
    acabamento = só metal: "pintado" ou "escovado"; se None, cinza médio -> escovado, o resto -> pintado.
    """
    if tipo not in ("madeira", "metal", "tecido", "liso"):
        raise ValueError(f"tipo de material desconhecido: {tipo}")
    comp, atrav, prof = eixos
    mat = bpy.data.materials.new(nome)
    R = _Rede(mat, semente)
    if tipo == "madeira":
        _madeira(R, cor, comp, atrav, prof, faixa, superficie, int(tabuas), lado)
    elif tipo == "metal":
        esc = (acabamento == "escovado") if acabamento else _cinza_medio(cor)
        _metal(R, cor, comp, atrav, prof, esc)
    elif tipo == "tecido":
        _tecido(R, cor, comp, atrav, prof)
    else:
        _liso(R, cor)
    return mat
