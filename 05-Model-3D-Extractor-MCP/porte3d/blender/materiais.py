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
def _madeira(R, cor, comp, atrav, prof, faixa, superficie, tabuas, lado, espacamento=0.0055, veio=1.0, borda=0.0, limites=None):
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
        e.color = (*(base * max(0.05, 1.0 - (1.0 - f) * veio)), 1)   # `veio` escala o contraste dos anéis
    Lk.new(aneis, ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    # poros/fibras: ruído fino esticado no comprimento
    fib = R.ruido(R.esc(140.0, comp, 3.0), detalhe=2.0)
    col = R.mult(col, R.rng(fib, 1.0 - 0.10 * veio, 1.0 + 0.07 * veio, 0.3, 0.7))
    col = R.mult(col, R.rng(r5, 0.88, 1.08))              # tom próprio de cada tábua
    if borda > 0 and limites is not None:               # biselado cartoon: borda clara fina, miolo escuro (por tábua/face)
        lo3, hi3 = limites
        ia, ic, ip = _AX[atrav], _AX[comp], _AX[prof]
        tam = [float(hi3[k] - lo3[k]) for k in range(3)]
        wt = tam[ia] / tabuas if tabuas else tam[ia]
        bw = max(0.003, min(0.03, 0.35 * min(wt, tam[ic], tam[ip])))
        def _dist(c, k):
            return M("MINIMUM", M("SUBTRACT", c, float(lo3[k])), M("SUBTRACT", float(hi3[k]), c))
        if tabuas:
            da_ = M("MULTIPLY", M("PINGPONG", M("MULTIPLY", M("SUBTRACT", pa, lo), tabuas / larg), 0.5), wt)
        else:
            da_ = _dist(pa, ia)
        dc_, dp_ = _dist(pl, ic), _dist(pb, ip)
        # mediana das 3 distancias = distancia a aresta mais proxima DENTRO da face (a normal da face da ~0)
        med = M("MAXIMUM", M("MINIMUM", da_, dc_), M("MINIMUM", M("MAXIMUM", da_, dc_), dp_))
        col = R.mult(col, R.rng(med, 1.0 + 0.4 * borda, 1.0 - 0.2 * borda, 0.0, bw, suave=True))
    if tabuas:                                           # junta entre tábuas
        fr = M("PINGPONG", M("MULTIPLY", M("SUBTRACT", pa, lo), tabuas / larg), 0.5)
        col = R.mult(col, R.rng(fr, 0.4 if not borda else 0.22, 1.0, 0.0, 0.015 if not borda else 0.045))
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


# ------------------------------------------------------------------------------------------ desgaste
def _ao(R, distancia, dentro=False):
    """Oclusão calculada no próprio material (vale no bake do Cycles): perto de 0 nas frestas e cantos internos;
    com `dentro`, perto de 0 nas quinas (arestas vivas para fora)."""
    n = R.N.new("ShaderNodeAmbientOcclusion")
    n.samples = 16
    n.inside = dentro
    n.only_local = True
    n.inputs["Distance"].default_value = distancia
    return n.outputs["AO"]


def _quina(R, limites, largura=0.035):
    """1 perto das arestas da caixa envolvente da peça, 0 no meio das faces: perto de duas faces ao mesmo tempo
    (a segunda menor distância às faces é pequena). Não depende da espessura da peça nem da malha."""
    M = R.M
    lo, hi = limites
    d = [M("MINIMUM", M("SUBTRACT", R.coord(e), float(lo[i])), M("SUBTRACT", float(hi[i]), R.coord(e)))
         for i, e in enumerate("xyz")]
    soma = M("ADD", M("ADD", d[0], d[1]), d[2])
    menor = M("MINIMUM", M("MINIMUM", d[0], d[1]), d[2])
    maior = M("MAXIMUM", M("MAXIMUM", d[0], d[1]), d[2])
    segunda = M("SUBTRACT", M("SUBTRACT", soma, menor), maior)
    return R.rng(segunda, 1.0, 0.0, 0.0, largura, suave=True)


def _aplicar_desgaste(R, nivel, limites=None, ferrugem=0.0):
    """Camada de uso por cima de qualquer material: tinta amarelada, encardido (embaixo, nas frestas e em manchas),
    escorridos verticais, tinta lascada nas quinas e em pontos soltos (mostrando chapa escura), e ferrugem em
    manchas irregulares com auréola e escorrido para baixo. `nivel` 0..1."""
    M = R.M
    lk = R.bsdf.inputs["Base Color"].links[0]
    col = lk.from_socket
    R.Lk.remove(lk)
    z = R.coord("z")
    k = float(nivel)
    # tinta envelhecida: amarelada e desigual
    tom = R.rng(R.ruido((3.0, 3.0, 3.0), detalhe=2.0), 0.5, 1.0, 0.3, 0.7)
    col = R.misturar(col, R.mult(col, (0.97, 0.91, 0.76)), M("MULTIPLY", tom, 0.7 * k))
    # encardido
    fresta = R.rng(_ao(R, 0.06), 1.0, 0.0, 0.45, 1.0)
    fe = float(ferrugem)
    baixo = R.rng(z, 1.0, 0.0, 0.0, 0.30 + 0.12 * fe, suave=True)
    escorre = R.rng(R.ruido(R.esc(30.0, "z", 1.8), detalhe=3.0), 0.0, 1.0, 0.48, 0.72)
    mancha = R.rng(R.ruido((6.0, 6.0, 6.0), detalhe=5.0, rugosidade=0.6), 0.0, 1.0, 0.45, 0.72)
    sujo = M("MAXIMUM", fresta, M("MULTIPLY", baixo, 0.9))
    sujo = M("MAXIMUM", sujo, M("MULTIPLY", escorre, 0.45))
    sujo = M("MAXIMUM", sujo, M("MULTIPLY", mancha, 0.35))
    col = R.misturar(col, R.mult(col, (0.58, 0.50, 0.40)), M("MINIMUM", M("MULTIPLY", sujo, 0.8 * k), 0.9))
    # campo de ferrugem: manchas grandes irregulares + pontos pequenos espalhados, puxados para quinas/frestas/baixo
    quina = _quina(R, limites) if limites is not None else R.rng(_ao(R, 0.01, dentro=True), 1.0, 0.0, 0.80, 0.99)
    grande = R.rng(R.ruido((3.5, 3.5, 3.5), detalhe=6.0, rugosidade=0.7), 0.0, 1.0, 0.40, 0.75)
    pontos = R.rng(R.ruido((30.0, 30.0, 30.0), detalhe=4.0, rugosidade=0.7), 0.0, 1.0, 0.66, 0.86)
    pressao = M("MAXIMUM", M("MAXIMUM", quina, M("MULTIPLY", baixo, 0.85 + 0.5 * fe)), M("MULTIPLY", fresta, 0.6 + 0.3 * fe))
    f = M("ADD", M("MULTIPLY", grande, 0.55), M("MULTIPLY", pressao, 0.5))
    f = M("ADD", f, M("MULTIPLY", pontos, 0.25))
    limiar = 1.0 - 0.45 * k - 0.22 * fe
    ferr = R.rng(f, 0.0, 1.0, limiar, limiar + 0.06, suave=True)
    aureola = R.rng(f, 0.0, 1.0, limiar - 0.14, limiar, suave=True)
    # escorrido de ferrugem: riscos verticais finos onde o campo é alto
    risco = R.rng(R.ruido(R.esc(90.0, "z", 2.5), detalhe=3.0), 0.0, 1.0, 0.55, 0.75)
    escorrido = M("MULTIPLY", risco, R.rng(f, 0.0, 1.0, limiar - 0.30, limiar - 0.05))
    # tinta lascada: nas quinas e em pontinhos, borda irregular
    rasgo = R.rng(R.ruido((70.0, 70.0, 70.0), detalhe=5.0, rugosidade=0.75), 0.0, 1.0, 0.40, 0.60)
    lasca = M("GREATER_THAN", M("ADD", M("MULTIPLY", quina, rasgo), M("MULTIPLY", pontos, 0.3)), 1.0 - 0.5 * k)
    tons = R.N.new("ShaderNodeValToRGB")
    els = tons.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*_lin((52, 30, 20)), 1)
    els[1].position, els[1].color = 1.0, (*_lin((150, 86, 48)), 1)
    e = els.new(0.5)
    e.color = (*_lin((104, 54, 30)), 1)
    R.Lk.new(R.ruido((120.0, 120.0, 120.0), detalhe=6.0, rugosidade=0.75), tons.inputs["Fac"])
    col = R.misturar(col, R.mult(col, (0.70, 0.56, 0.42)), M("MULTIPLY", M("MAXIMUM", aureola, escorrido), 0.65 * k))
    col = R.misturar(col, R.mult(tons.outputs["Color"], (0.55, 0.55, 0.55)), M("MULTIPLY", lasca, 0.9))
    col = R.misturar(col, tons.outputs["Color"], M("MULTIPLY", ferr, 0.95))
    R.Lk.new(col, R.bsdf.inputs["Base Color"])

def _aplicar_trancado(R, escala, comp, atrav, prof):
    """Trança de cestaria (palha/taquara): tiras de ~1,6 cm / `escala` que se cruzam alternadas (por cima/por baixo),
    com a diagonal em dobro (sarja) para dar losangos; frestas escuras entre as tiras, tom próprio por tira e
    nervura fina no sentido de cada tira. Como só a cor base é assada, o relevo (Bump) vira sombreado na cor.
    Calculada nos dois eixos do plano de cada face (escolhidos pela normal), como o tecido."""
    M, N, Lk = R.M, R.N, R.Lk
    lk = R.bsdf.inputs["Base Color"].links[0]
    col = lk.from_socket
    R.Lk.remove(lk)
    w = 0.016 / max(0.05, float(escala))

    def tom_tira(i, k):
        wn = N.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "1D"
        Lk.new(M("ADD", i, R.semente * 7.1 + k), wn.inputs["W"])
        sc = N.new("ShaderNodeSeparateColor")
        Lk.new(wn.outputs["Color"], sc.inputs["Color"])
        return R.rng(sc.outputs[0], 0.78, 1.16)

    def trama(eu, ev, k):
        pu, pv = R.coord(eu), R.coord(ev)
        ond = R.ruido((30.0, 30.0, 30.0), detalhe=1.0)
        uu = M("ADD", M("MULTIPLY", pu, 1.0 / w), M("MULTIPLY", M("SUBTRACT", ond, 0.5), 0.35))
        vv = M("ADD", M("MULTIPLY", pv, 1.0 / w), M("MULTIPLY", M("SUBTRACT", ond, 0.5), 0.35))
        iu, iv = M("FLOOR", uu), M("FLOOR", vv)
        fu, fv = M("FRACT", uu), M("FRACT", vv)
        # sarja 2x2: a tira que fica por cima muda a cada 2 casas na diagonal -> losangos
        soma = M("FLOOR", M("MULTIPLY", M("ADD", iu, iv), 0.5))
        par = M("SUBTRACT", soma, M("MULTIPLY", M("FLOOR", M("MULTIPLY", soma, 0.5)), 2.0))
        su = M("POWER", M("SINE", M("MULTIPLY", fu, math.pi)), 0.55)
        sv = M("POWER", M("SINE", M("MULTIPLY", fv, math.pi)), 0.55)
        em_cima = M("ADD", sv, M("MULTIPLY", par, M("SUBTRACT", su, sv)))     # relevo da tira por cima
        por_baixo = M("ADD", su, M("MULTIPLY", par, M("SUBTRACT", sv, su)))
        fundo = M("MULTIPLY", por_baixo, 0.55)                                  # a tira de baixo aparece afundada
        alt = M("MAXIMUM", em_cima, fundo)
        t = M("ADD", tom_tira(iu, 0.13 + k), M("MULTIPLY", par, M("SUBTRACT", tom_tira(iv, 0.61 + k), tom_tira(iu, 0.13 + k))))
        nerv = R.rng(R.ruido(R.esc(18.0, eu, 220.0), detalhe=1.0), 0.90, 1.08, 0.3, 0.7)
        return M("MULTIPLY", M("MULTIPLY", R.rng(alt, 0.38, 1.30), t), nerv)

    pares = {}
    for k, nome_n in enumerate((comp, atrav, prof)):
        restantes = [e for e in (comp, atrav, prof) if e != nome_n]
        pares[nome_n] = trama(restantes[0], restantes[1], 3.0 * k)
    sepn = N.new("ShaderNodeSeparateXYZ")
    Lk.new(R.tc.outputs["Normal"], sepn.inputs["Vector"])
    nx, ny, nz_ = (M("ABSOLUTE", sepn.outputs[i]) for i in range(3))
    sx = M("MULTIPLY", M("GREATER_THAN", M("SUBTRACT", nx, ny), 0.0), M("GREATER_THAN", M("SUBTRACT", nx, nz_), 0.0))
    sy = M("MULTIPLY", M("SUBTRACT", 1.0, sx), M("GREATER_THAN", M("SUBTRACT", ny, nz_), 0.0))
    sz = M("SUBTRACT", M("SUBTRACT", 1.0, sx), sy)
    peso = {"x": sx, "y": sy, "z": sz}
    fator = None
    for e in "xyz":
        termo = M("MULTIPLY", pares[e], peso[e])
        fator = termo if fator is None else M("ADD", fator, termo)
    R.Lk.new(R.mult(col, fator), R.bsdf.inputs["Base Color"])


def _aplicar_listras(R, forca, periodo):
    """Listras verticais (tecido listrado): alternam tom claro e escuro a cada `periodo` metros, em x + y, para que
    valham na frente e nas laterais. `forca` 0..1 é a diferença de tom."""
    M = R.M
    lk = R.bsdf.inputs["Base Color"].links[0]
    col = lk.from_socket
    R.Lk.remove(lk)
    fase = M("MULTIPLY", M("ADD", R.coord("x"), R.coord("y")), 6.2832 / max(0.01, float(periodo)))
    onda = M("SINE", fase)
    tom = R.rng(onda, 1.0 - 0.22 * forca, 1.0 + 0.12 * forca, -1.0, 1.0)
    R.Lk.new(R.mult(col, tom), R.bsdf.inputs["Base Color"])


def _aplicar_desenho(R, d, nome):
    """Linhas pintadas na cor base (sem relevo): `d` = {"linhas": [[(x,y), ...], ...] polígonos fechados em metros no
    plano xy, "largura": m, "cor": [r,g,b], "forca": 0..1}. Só vale nas faces voltadas para cima (topo)."""
    geo = R.N.new("ShaderNodeNewGeometry")
    nsep = R.N.new("ShaderNodeSeparateXYZ")
    R.Lk.new(geo.outputs["Normal"], nsep.inputs["Vector"])
    topo = R.M("GREATER_THAN", nsep.outputs["Z"], 0.9)
    if not d.get("linhas"):
        return
    pol = [np.asarray(q, float) for q in d["linhas"]]
    larg = float(d.get("largura", 0.0045))
    forca = float(d.get("forca", 0.85))
    ppm = float(d.get("pixels_por_metro", 2500.0))
    todos = np.vstack(pol)
    marg = 2 * larg
    x0, y0 = todos.min(0) - marg
    x1, y1 = todos.max(0) + marg
    W, H = max(8, int((x1 - x0) * ppm)), max(8, int((y1 - y0) * ppm))
    xs = x0 + (np.arange(W) + 0.5) / ppm
    ys = y0 + (np.arange(H) + 0.5) / ppm
    gx, gy = np.meshgrid(xs, ys)
    dist = np.full((H, W), 1e9)
    for q in pol:
        for i in range(len(q)):
            a, b = q[i], q[(i + 1) % len(q)]
            ab = b - a
            t = np.clip(((gx - a[0]) * ab[0] + (gy - a[1]) * ab[1]) / max(1e-9, ab @ ab), 0, 1)
            dist = np.minimum(dist, np.hypot(gx - (a[0] + t * ab[0]), gy - (a[1] + t * ab[1])))
    alfa = np.clip((larg / 2 - dist) * ppm + 0.5, 0.0, 1.0)      # borda suavizada de ~1 pixel
    img = bpy.data.images.new(f"desenho_{nome}", W, H, alpha=True)
    dentro = np.zeros((H, W), bool)                  # canal R = interior dos polígonos (para escurecer)
    for q in pol:
        ins = np.zeros((H, W), bool)
        for i in range(len(q)):
            a, b = q[i], q[(i + 1) % len(q)]
            if a[1] == b[1]:
                continue
            cruza = (a[1] > gy) != (b[1] > gy)
            xi = a[0] + (gy - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            ins ^= cruza & (gx < xi)
        dentro |= ins
    px = np.ones((H, W, 4), np.float32)
    px[..., 0] = dentro.astype(np.float32)
    px[..., 3] = alfa
    img.pixels.foreach_set(px.ravel())
    img.alpha_mode = "CHANNEL_PACKED"
    img.pack()
    mp = R.N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0 / (x1 - x0), 1.0 / (y1 - y0), 1.0)
    mp.inputs["Location"].default_value = (-x0 / (x1 - x0), -y0 / (y1 - y0), 0.0)
    R.Lk.new(R.tc.outputs["Object"], mp.inputs["Vector"])
    tx = R.N.new("ShaderNodeTexImage")
    tx.image, tx.extension, tx.interpolation = img, "CLIP", "Linear"
    R.Lk.new(mp.outputs["Vector"], tx.inputs["Vector"])
    csep = R.N.new("ShaderNodeSeparateXYZ")          # X = interior dos polígonos (canal R da imagem)
    R.Lk.new(tx.outputs["Color"], csep.inputs["Vector"])
    if d.get("escurecer"):       # escurece só a face de cima, só dentro dos polígonos
        lk0 = R.bsdf.inputs["Base Color"].links[0]
        col0 = lk0.from_socket
        R.Lk.remove(lk0)
        esc = R.M("MULTIPLY", R.M("MULTIPLY", csep.outputs["X"], topo), float(d["escurecer"]))
        R.Lk.new(R.mult(col0, R.M("SUBTRACT", 1.0, esc)), R.bsdf.inputs["Base Color"])
    if d.get("ferrugem_dentro"):  # manchas de ferrugem (marrom alaranjado) só dentro dos polígonos, na face de cima
        f = float(d["ferrugem_dentro"])
        ruido = R.ruido((9, 9, 9), detalhe=4.0, rugosidade=0.6)
        fino = R.ruido((38, 38, 38), detalhe=2.0, rugosidade=0.5)
        mancha = R.rng(R.M("ADD", ruido, R.M("MULTIPLY", fino, 0.35)), 0.0, 1.0, 0.80 - 0.12 * f, 0.92 - 0.12 * f, suave=True)
        fr = R.M("MULTIPLY", R.M("MULTIPLY", mancha, csep.outputs["X"]), topo)
        lk1 = R.bsdf.inputs["Base Color"].links[0]
        col1 = lk1.from_socket
        R.Lk.remove(lk1)
        ferr = tuple(float(v) for v in _lin(d.get("cor_ferrugem", [92, 56, 30])))
        R.Lk.new(R.misturar(col1, ferr, R.M("MULTIPLY", fr, 0.7)), R.bsdf.inputs["Base Color"])
    fac = R.M("MULTIPLY", R.M("MULTIPLY", tx.outputs["Alpha"], topo), forca)
    lk = R.bsdf.inputs["Base Color"].links[0]
    col = lk.from_socket
    R.Lk.remove(lk)
    cor = tuple(float(v) for v in _lin(d.get("cor", [14, 20, 16])))
    R.Lk.new(R.misturar(col, cor, fac), R.bsdf.inputs["Base Color"])


def _aplicar_estrago(R, comp, atrav, manchas=0.0, rasgos=0.0, podre=0.0):
    """Estrago procedural por cima do material: manchas irregulares com auréola (tecido ou qualquer), rasgos finos
    com enchimento claro (tecido) e apodrecimento escuro com fibras (madeira). Tudo 0..1; zero desliga."""
    M = R.M
    lk = R.bsdf.inputs["Base Color"].links[0]
    col = lk.from_socket
    R.Lk.remove(lk)
    if manchas > 0:
        v = R.ruido((4.5, 4.5, 4.5), detalhe=5.0, rugosidade=0.68)
        lim = 0.64 - 0.10 * manchas
        nucleo = R.rng(v, 0.0, 1.0, lim, lim + 0.05, suave=True)
        aureola = R.rng(v, 0.0, 1.0, lim - 0.07, lim, suave=True)
        col = R.misturar(col, R.mult(col, (0.84, 0.74, 0.56)), M("MULTIPLY", aureola, 0.7))      # halo amarelado de umidade
        col = R.misturar(col, R.mult(col, (0.46, 0.36, 0.25)), M("MULTIPLY", nucleo, 0.85))     # miolo escuro
    if podre > 0:
        v = R.ruido((3.2, 3.2, 3.2), detalhe=6.0, rugosidade=0.72)
        lim = 0.62 - 0.12 * podre
        nucleo = R.rng(v, 0.0, 1.0, lim, lim + 0.045, suave=True)
        borda = R.rng(v, 0.0, 1.0, lim - 0.08, lim, suave=True)
        fibra = R.rng(R.ruido(R.esc(2.0, comp, 90.0), detalhe=3.0), 0.55, 1.15, 0.3, 0.7)       # fibras no sentido da madeira
        escuro = R.mult(R.mult(col, (0.30, 0.23, 0.15)), fibra)
        col = R.misturar(col, R.mult(col, (0.62, 0.52, 0.38)), M("MULTIPLY", borda, 0.8))        # madeira amolecida em volta
        col = R.misturar(col, escuro, M("MULTIPLY", nucleo, 0.95))                                # miolo podre
    if rasgos > 0:
        zona = R.rng(R.ruido((2.2, 2.2, 2.2), detalhe=2.0), 0.0, 1.0, 0.60 - 0.06 * rasgos, 0.66 - 0.06 * rasgos, suave=True)
        for eixo in (comp, atrav):
            fenda = R.ruido(R.esc(1.5, eixo, 55.0), detalhe=1.0)
            d = M("ABSOLUTE", M("SUBTRACT", fenda, 0.5))
            miolo = R.rng(d, 1.0, 0.0, 0.0, 0.010 + 0.004 * rasgos)
            enchi = R.rng(d, 1.0, 0.0, 0.0, 0.030 + 0.008 * rasgos)
            col = R.misturar(col, R.mult(R.cor_base((205, 195, 160)), 0.9), M("MULTIPLY", M("MULTIPLY", enchi, zona), 0.9))   # enchimento claro
            col = R.misturar(col, R.cor_base((20, 14, 18)), M("MULTIPLY", M("MULTIPLY", miolo, zona), 0.95))                  # fundo da fenda
    R.Lk.new(col, R.bsdf.inputs["Base Color"])


def _cinza_medio(cor):
    c = np.asarray(cor, float)
    return (c.max() - c.min()) <= 22 and c.mean() <= 205


def criar(nome, tipo, cor, eixos=("x", "y", "z"), faixa=(-0.5, 0.5), superficie=0.0, tabuas=0,
          semente=0, lado=1, acabamento=None, desgaste=0.0, limites=None, ferrugem=0.0, veio=1.0,
          manchas=0.0, rasgos=0.0, podre=0.0, listras=0.0, listras_periodo=0.07, trancado=0.0, borda=0.0, desenho=None):
    """Cria o material procedural `tipo` (madeira | metal | tecido | liso) com cor base `cor` (sRGB 0..255).

    eixos      = (comprimento, atravessado, profundidade): direção do veio/comprimento da peça, o eixo em que
                 as tábuas se enfileiram e a normal da face principal.
    faixa      = (mín, máx) da peça ao longo de `atravessado` (as tábuas dividem esse intervalo).
    superficie = coordenada da face principal ao longo de `profundidade` (o centro dos anéis fica atrás dela).
    tabuas     = número de tábuas (0 = peça única).
    semente    = faz peças diferentes ficarem diferentes.
    lado       = +1 se a face principal é a de maior coordenada em `profundidade`, -1 se é a de menor.
    acabamento = só metal: "pintado" ou "escovado"; se None, cinza médio -> escovado, o resto -> pintado.
    limites    = ((x0,y0,z0), (x1,y1,z1)) da caixa envolvente da peça: marca as quinas para o desgaste.
    ferrugem   = 0..1: quanto da camada de uso vira ferrugem (embaixo, nas frestas e escorrendo).
    veio       = só madeira: força do veio (1 = padrão; 2 a 3 deixa os anéis e as fibras bem visíveis).
    manchas    = 0..1: manchas irregulares com auréola amarelada (umidade, sujeira).
    rasgos     = 0..1: fendas finas com enchimento claro (tecido).
    podre      = 0..1: apodrecimento escuro com fibras (madeira).
    listras    = 0..1: listras verticais (tecido listrado); `listras_periodo` é a largura de um par de listras, em metros.
    trancado   = escala (>0) da trança de cestaria (tiras cruzadas/losangos), para tipo tecido ou liso; 1 = tira de 1,6 cm.
    borda      = só madeira, 0..1: biselado cartoon por tábua/face (borda mais clara e fina, miolo mais escuro); 0 = desligado.
    desenho    = linhas pintadas na cor (sem relevo) nas faces voltadas para cima: {"linhas": [[[x,y],...],...],
                 "largura": m, "cor": [r,g,b], "forca": 0..1, "escurecer": 0..1 (escurece só a face de cima, dentro dos polígonos), "ferrugem_dentro": 0..1 (manchas de ferrugem dentro dos polígonos)}.
    desgaste   = 0..1: camada de uso (amarelado, encardido, tinta lascada nas quinas, ferrugem com escorrido).
    """
    if tipo not in ("madeira", "metal", "tecido", "liso"):
        raise ValueError(f"tipo de material desconhecido: {tipo}")
    comp, atrav, prof = eixos
    mat = bpy.data.materials.new(nome)
    R = _Rede(mat, semente)
    if tipo == "madeira":
        _madeira(R, cor, comp, atrav, prof, faixa, superficie, int(tabuas), lado, veio=float(veio),
                 borda=float(borda), limites=limites)
    elif tipo == "metal":
        esc = (acabamento == "escovado") if acabamento else _cinza_medio(cor)
        _metal(R, cor, comp, atrav, prof, esc)
    elif tipo == "tecido":
        _tecido(R, cor, comp, atrav, prof)
    else:
        _liso(R, cor)
    if trancado and trancado > 0 and tipo in ("tecido", "liso"):
        _aplicar_trancado(R, float(trancado), comp, atrav, prof)
    if desenho:
        _aplicar_desenho(R, desenho, nome)
    if listras > 0:
        _aplicar_listras(R, float(listras), float(listras_periodo))
    if desgaste > 0:
        _aplicar_desgaste(R, desgaste, limites, ferrugem)
    if manchas > 0 or rasgos > 0 or podre > 0:
        _aplicar_estrago(R, comp, atrav, float(manchas), float(rasgos), float(podre))
    return mat
