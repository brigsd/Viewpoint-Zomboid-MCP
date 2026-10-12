"""Folhas de imagem para o critico visual do porte 3D (ver CONTRATO.md).

Le a pasta de trabalho de um objeto (`entrada/`, `vistas/`, `pecas.json`) e escreve em `<pasta>/folhas/`:

  comparacao.png     jogo (frente/tras) | modelo arte | modelo realista, a 0 e a 180 graus
  giro_arte.png      os 8 angulos do nivel arte (4x2)
  giro_realista.png  os 8 angulos do nivel realista (4x2)
  fio.png            os 8 angulos do fio + fio sobre a arte (0 e 45) + legenda de cor de cada peca
  sobreposicao.png   contorno do jogo x modelo a 0 graus (verde/magenta/cinza) e mapa de diferenca de cor
  zoom.png           metade de cima e de baixo do objeto, ampliada, a 0 e 45 graus (arte x realista)
  giro_arte.gif, giro_realista.gif   os 8 angulos, 250 ms por quadro, fundo escuro
  medidas.json       {"contorno_0": IoU, "cor_0": diferenca media de cor}  (tambem copiado em `<pasta>/medidas.json`)

Uso:  python -m porte3d.folhas <pasta_objeto>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FW, FH = 128, 256                      # quadro do jogo
ANGULOS = tuple(range(0, 360, 45))
BG = (40, 42, 48, 255)                 # mesmo fundo dos experimentos antigos
BG_VAZIO = (52, 54, 62, 255)           # tile ausente
AMARELO = (255, 255, 0)                # rotulo do jogo
VERDE = (120, 255, 120)                # rotulo do modelo
BRANCO = (235, 235, 235)
LARANJA = (255, 170, 80)               # avisos
BARRA = 20                             # altura da faixa de rotulo de cada tile
MARGEM_TILE = 6                        # espaco entre tiles
NIVEIS = ("arte", "realista", "fio", "fio_sobre_arte")
AMPLIAR_SOBREPOSICAO = 4               # fator (NEAREST) da folha de sobreposicao
ZOOM_ALVO = 8                          # ampliacao-alvo do zoom em relacao ao pixel do jogo


# ---------------------------------------------------------------- utilidades

def _fonte(tam: int = 13):
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:                  # Pillow antigo: so a fonte fixa
        return ImageFont.load_default()


FONTE = _fonte(13)
FONTE_G = _fonte(15)


def _larg(texto: str, fonte=FONTE) -> int:
    return int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(texto, font=fonte)) + 1


def _abrir(caminho: Path) -> Image.Image | None:
    try:
        return Image.open(caminho).convert("RGBA")
    except (FileNotFoundError, OSError):
        return None


def _ajustar(im: Image.Image | None, tam: tuple[int, int]) -> Image.Image | None:
    if im is not None and im.size != tam:
        im = im.resize(tam, Image.NEAREST)
    return im


def _sobre_fundo(im: Image.Image) -> Image.Image:
    fundo = Image.new("RGBA", im.size, BG)
    fundo.alpha_composite(im)
    return fundo


def _bbox_alfa(imgs: list[Image.Image]) -> tuple[int, int, int, int] | None:
    """Uniao das caixas do conteudo nao transparente (alfa > 0)."""
    caixas = [b for b in (i.getchannel("A").getbbox() for i in imgs if i is not None) if b]
    if not caixas:
        return None
    return (min(b[0] for b in caixas), min(b[1] for b in caixas),
            max(b[2] for b in caixas), max(b[3] for b in caixas))


def _com_margem(caixa, tam, margem):
    if caixa is None:
        return (0, 0, tam[0], tam[1])
    x0, y0, x1, y1 = caixa
    return (max(0, x0 - margem), max(0, y0 - margem), min(tam[0], x1 + margem), min(tam[1], y1 + margem))


def _recorte(imgs: list[Image.Image | None], tam: tuple[int, int], margem: int):
    return _com_margem(_bbox_alfa([i for i in imgs if i is not None]), tam, margem)


def _tile(rotulo: str, cor, img: Image.Image | None, tam: tuple[int, int], largura: int | None = None,
          aviso: str | None = None) -> Image.Image:
    """Tile = faixa de rotulo + imagem (ja recortada, `tam`) sobre o fundo. Sem imagem, mostra 'ausente'."""
    largura = largura or tam[0]
    t = Image.new("RGBA", (largura, tam[1] + BARRA), BG)
    d = ImageDraw.Draw(t)
    d.text((4, 3), rotulo, fill=cor, font=FONTE)
    d.line([(0, BARRA - 1), (largura, BARRA - 1)], fill=(70, 72, 80))
    if img is None:
        d.rectangle([0, BARRA, largura - 1, tam[1] + BARRA - 1], fill=BG_VAZIO)
        txt = aviso or "ausente"
        d.text((8, BARRA + 10), txt, fill=LARANJA, font=FONTE)
    else:
        t.alpha_composite(img, ((largura - tam[0]) // 2, BARRA))
    return t


def _folha(tiles: list[Image.Image], colunas: int, titulo: list[tuple[str, tuple]] | None = None,
           rodape: Image.Image | None = None) -> Image.Image:
    """Cola os tiles em grade (todos do mesmo tamanho), com linhas de titulo opcionais e um rodape."""
    tw, th = tiles[0].size
    linhas = (len(tiles) + colunas - 1) // colunas
    larg = colunas * tw + (colunas + 1) * MARGEM_TILE
    if rodape is not None:
        larg = max(larg, rodape.width + 2 * MARGEM_TILE)
    alt_tit = (len(titulo) * 20 + 6) if titulo else 0
    alt = alt_tit + linhas * th + (linhas + 1) * MARGEM_TILE + (rodape.height + MARGEM_TILE if rodape is not None else 0)
    folha = Image.new("RGBA", (larg, alt), BG)
    d = ImageDraw.Draw(folha)
    for i, (txt, cor) in enumerate(titulo or []):
        d.text((MARGEM_TILE, 6 + i * 20), txt, fill=cor, font=FONTE_G)
    for k, t in enumerate(tiles):
        r, c = divmod(k, colunas)
        x = MARGEM_TILE + c * (tw + MARGEM_TILE) + (larg - (colunas * tw + (colunas + 1) * MARGEM_TILE)) // 2
        y = alt_tit + MARGEM_TILE + r * (th + MARGEM_TILE)
        folha.alpha_composite(t, (x, y))
    if rodape is not None:
        folha.alpha_composite(rodape, (MARGEM_TILE, alt - rodape.height - MARGEM_TILE))
    return folha


def _salvar(im: Image.Image, caminho: Path) -> None:
    im.convert("RGB").save(caminho)


def _largura_tile(cw: int, rotulos: list[str]) -> int:
    return max([cw] + [_larg(r) + 10 for r in rotulos])


# ---------------------------------------------------------------- entradas

class _Entradas:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        self.vistas: dict[tuple[str, int], Image.Image] = {}
        for nivel in NIVEIS:
            for a in ANGULOS:
                im = _abrir(pasta / "vistas" / f"{nivel}_{a:03d}.png")
                if im is not None:
                    self.vistas[(nivel, a)] = im
        self.E = 2
        for im in self.vistas.values():
            self.E = max(1, im.width // FW)
            break
        if ("arte", 0) in self.vistas:
            self.E = max(1, self.vistas[("arte", 0)].width // FW)
        self.tam = (FW * self.E, FH * self.E)
        for k in list(self.vistas):
            self.vistas[k] = _ajustar(self.vistas[k], self.tam)
        self.frente = _abrir(pasta / "entrada" / "frente_original.png")
        self.tras = _abrir(pasta / "entrada" / "tras_original.png") or _abrir(pasta / "entrada" / "tras.png")
        self.frente_g = _ajustar(self.frente, (FW, FH))   # 128x256 (para medidas)
        self.frente_e = self._ampliar(self.frente)         # E vezes, NEAREST (para exibir)
        self.tras_e = self._ampliar(self.tras)
        self.pecas = []
        try:
            self.pecas = json.loads((pasta / "pecas.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            pass

    def _ampliar(self, im):
        if im is None:
            return None
        return _ajustar(im, (FW, FH)).resize(self.tam, Image.NEAREST)

    def v(self, nivel: str, ang: int):
        return self.vistas.get((nivel, ang))


# ---------------------------------------------------------------- medidas

def _reduzir(im: Image.Image, E: int):
    """Reduz o modelo (FW*E x FH*E) para 128x256 com filtro de area e alfa pre-multiplicado.
    Devolve (rgb float (256,128,3), alfa float 0..255 (256,128))."""
    a = np.asarray(im, dtype=np.float32)
    al = a[..., 3:4] / 255.0
    pm = (a[..., :3] * al).reshape(FH, E, FW, E, 3).mean(axis=(1, 3))
    am = al.reshape(FH, E, FW, E, 1).mean(axis=(1, 3))
    rgb = pm / np.maximum(am, 1e-6)
    return rgb, am[..., 0] * 255.0


def _comparar(ent: _Entradas):
    """Contorno e cor a 0 graus. Devolve None se faltar o jogo ou o modelo arte 0, senao um dict."""
    arte = ent.v("arte", 0)
    if arte is None or ent.frente_g is None:
        return None
    g = np.asarray(ent.frente_g)
    mj = g[..., 3] >= 128
    rgb_m, al_m = _reduzir(arte, ent.E)
    mm = al_m >= 128
    ambos = mj & mm
    uniao = int((mj | mm).sum())
    iou = float(ambos.sum()) / uniao if uniao else 0.0
    dif = np.abs(g[..., :3].astype(np.float32) - rgb_m).mean(axis=2)   # por pixel, 0..255
    cor = float(dif[ambos].mean()) if ambos.any() else 0.0
    return {"mj": mj, "mm": mm, "ambos": ambos, "dif": dif, "iou": iou, "cor": cor}


# ---------------------------------------------------------------- folhas

def _folha_comparacao(ent: _Entradas, saida: Path) -> None:
    pares = [
        [("jogo frente (original)", AMARELO, ent.frente_e), ("modelo arte 0 graus", VERDE, ent.v("arte", 0)),
         ("modelo realista 0 graus", VERDE, ent.v("realista", 0))],
        [("jogo tras", AMARELO, ent.tras_e), ("modelo arte 180 graus", VERDE, ent.v("arte", 180)),
         ("modelo realista 180 graus", VERDE, ent.v("realista", 180))],
    ]
    todas = [im for linha in pares for _, _, im in linha]
    margem = 3 * ent.E
    cx = _recorte(todas, ent.tam, margem)
    cw, ch = cx[2] - cx[0], cx[3] - cx[1]
    largura = _largura_tile(cw, [r for linha in pares for r, _, _ in linha])
    tiles = []
    for linha in pares:
        for rot, cor, im in linha:
            tiles.append(_tile(rot, cor, im.crop(cx) if im is not None else None, (cw, ch), largura,
                               aviso="sem imagem (arquivo ausente)"))
    _salvar(_folha(tiles, 3), saida / "comparacao.png")


def _folha_giro(ent: _Entradas, nivel: str, saida: Path) -> None:
    imgs = [ent.v(nivel, a) for a in ANGULOS]
    if all(i is None for i in imgs):
        # nada deste nivel: folha pequena so com o aviso, para o critico saber
        f = Image.new("RGB", (460, 50), BG[:3])
        ImageDraw.Draw(f).text((10, 16), f"sem vistas do nivel {nivel} (pasta vistas/ sem {nivel}_*.png)",
                               fill=LARANJA, font=FONTE)
        f.save(saida / f"giro_{nivel}.png")
        return
    cx = _recorte(imgs, ent.tam, 3 * ent.E)
    cw, ch = cx[2] - cx[0], cx[3] - cx[1]
    largura = _largura_tile(cw, [f"{nivel} 315 graus"])
    tiles = [_tile(f"{nivel} {a:03d} graus", VERDE, i.crop(cx) if i is not None else None, (cw, ch), largura,
                   aviso="vista ausente") for a, i in zip(ANGULOS, imgs)]
    _salvar(_folha(tiles, 4), saida / f"giro_{nivel}.png")
    quadros = []
    for i in imgs:
        if i is None:
            continue
        q = _sobre_fundo(i.crop(cx))
        quadros.append(q.convert("RGB").convert("P", palette=Image.ADAPTIVE))
    quadros[0].save(saida / f"giro_{nivel}.gif", save_all=True, append_images=quadros[1:], duration=250, loop=0)


def _legenda(pecas: list[dict], largura: int) -> Image.Image | None:
    """Amostra de cor + nome de cada peca (a cor e a do fio no render)."""
    if not pecas:
        return None
    textos = [f"{p.get('indice', '?')} {p.get('nome', '?')}" for p in pecas]
    cel = max(_larg(t) for t in textos) + 16 + 8 + 18
    cols = max(1, (largura - 2 * MARGEM_TILE) // cel)
    linhas = (len(pecas) + cols - 1) // cols
    alt = 24 + linhas * 20
    im = Image.new("RGBA", (max(largura - 2 * MARGEM_TILE, cel), alt), BG)
    d = ImageDraw.Draw(im)
    d.text((0, 2), "legenda: cor do fio -> peca", fill=BRANCO, font=FONTE)
    for k, (p, t) in enumerate(zip(pecas, textos)):
        r, c = divmod(k, cols)
        x, y = c * cel, 24 + r * 20
        cor = tuple(int(v) for v in p.get("cor_fio", (128, 128, 128)))[:3]
        d.rectangle([x, y + 2, x + 15, y + 15], fill=cor, outline=(235, 235, 235))
        d.text((x + 22, y + 1), t, fill=BRANCO, font=FONTE)
    return im


def _folha_fio(ent: _Entradas, saida: Path) -> None:
    itens = [(f"fio {a:03d} graus", ent.v("fio", a)) for a in ANGULOS]
    itens += [("fio sobre arte 000 graus", ent.v("fio_sobre_arte", 0)),
              ("fio sobre arte 045 graus", ent.v("fio_sobre_arte", 45))]
    imgs = [i for _, i in itens]
    if all(i is None for i in imgs):
        f = Image.new("RGB", (460, 50), BG[:3])
        ImageDraw.Draw(f).text((10, 16), "sem vistas de fio (pasta vistas/ sem fio_*.png)", fill=LARANJA, font=FONTE)
        f.save(saida / "fio.png")
        return
    cx = _recorte(imgs, ent.tam, 3 * ent.E)
    cw, ch = cx[2] - cx[0], cx[3] - cx[1]
    largura = _largura_tile(cw, [r for r, _ in itens])
    tiles = [_tile(r, VERDE, i.crop(cx) if i is not None else None, (cw, ch), largura, aviso="vista ausente")
             for r, i in itens]
    colunas = 5
    larg_folha = colunas * largura + (colunas + 1) * MARGEM_TILE
    leg = _legenda(ent.pecas, larg_folha)
    if leg is None:
        leg = Image.new("RGBA", (larg_folha - 2 * MARGEM_TILE, 24), BG)
        ImageDraw.Draw(leg).text((0, 2), "sem pecas.json: legenda de cores indisponivel", fill=LARANJA, font=FONTE)
    _salvar(_folha(tiles, colunas, rodape=leg), saida / "fio.png")


def _mapa_calor(dif: np.ndarray, ambos: np.ndarray, teto: float = 64.0) -> np.ndarray:
    """Diferenca de cor (0..255) -> azul escuro (igual) / amarelo / vermelho (>= teto). Fora da sobreposicao: cinza escuro."""
    t = np.clip(dif / teto, 0, 1)[..., None]
    c0, c1, c2 = (np.array(c, np.float32) for c in ((30, 40, 130), (250, 220, 40), (255, 40, 40)))
    cor = np.where(t < 0.5, c0 + (c1 - c0) * (t / 0.5), c1 + (c2 - c1) * ((t - 0.5) / 0.5))
    out = np.empty(dif.shape + (3,), np.uint8)
    out[:] = (62, 62, 68)
    out[ambos] = cor[ambos].astype(np.uint8)
    return out


def _barra_calor(largura: int, teto: float = 64.0) -> Image.Image:
    n = 256
    im = Image.new("RGBA", (max(largura, n + 20 + _larg("diferenca de cor (0-255)")), 44), BG)
    d = ImageDraw.Draw(im)
    degr = _mapa_calor(np.linspace(0, teto, n)[None, :].repeat(14, 0), np.ones((14, n), bool), teto)
    im.paste(Image.fromarray(degr), (0, 4))
    d.text((0, 20), "0", fill=BRANCO, font=FONTE)
    d.text((n - _larg(f"{teto:.0f}+"), 20), f"{teto:.0f}+", fill=BRANCO, font=FONTE)
    d.text((n + 10, 4), "diferenca de cor (0-255)", fill=BRANCO, font=FONTE)
    return im


def _folha_sobreposicao(ent: _Entradas, cmp: dict | None, saida: Path) -> None:
    if cmp is None:
        f = Image.new("RGB", (560, 50), BG[:3])
        falta = "frente_original.png" if ent.frente_g is None else "vistas/arte_000.png"
        ImageDraw.Draw(f).text((10, 16), f"sem sobreposicao: falta {falta}", fill=LARANJA, font=FONTE)
        f.save(saida / "sobreposicao.png")
        return
    mj, mm, ambos = cmp["mj"], cmp["mm"], cmp["ambos"]
    z = AMPLIAR_SOBREPOSICAO
    ys, xs = np.nonzero(mj | mm)
    if len(xs):
        cx = (max(0, xs.min() - 4), max(0, ys.min() - 4), min(FW, xs.max() + 5), min(FH, ys.max() + 5))
    else:
        cx = (0, 0, FW, FH)
    ov = np.full((FH, FW, 3), BG[:3], np.uint8)
    ov[mj & ~mm] = (60, 220, 90)       # so no jogo
    ov[mm & ~mj] = (255, 40, 220)      # so no modelo
    ov[ambos] = (150, 150, 155)        # nos dois
    calor = _mapa_calor(cmp["dif"], ambos)

    def pronto(a):
        im = Image.fromarray(a).convert("RGBA").crop(cx)
        return im.resize((im.width * z, im.height * z), Image.NEAREST)

    t1, t2 = pronto(ov), pronto(calor)
    rotulos = ["contorno: verde=so jogo magenta=so modelo", "diferenca de cor onde os dois existem"]
    largura = _largura_tile(t1.width, rotulos)
    tiles = [_tile(rotulos[0], BRANCO, t1, t1.size, largura), _tile(rotulos[1], BRANCO, t2, t2.size, largura)]
    n_jogo, n_mod, n_amb = int((mj & ~mm).sum()), int((mm & ~mj).sum()), int(ambos.sum())
    titulo = [(f"0 graus   IoU do contorno = {cmp['iou'] * 100:.1f} %   |   diferenca media de cor = {cmp['cor']:.1f} (0-255)",
               BRANCO),
              (f"pixels: so jogo {n_jogo}   so modelo {n_mod}   nos dois {n_amb}   (modelo reduzido a 128x256, alfa >= 128)",
               (190, 190, 200))]
    rod = Image.new("RGBA", (2 * largura + MARGEM_TILE, 24), BG)
    d = ImageDraw.Draw(rod)
    for k, (cor, txt) in enumerate([((60, 220, 90), "so no jogo"), ((255, 40, 220), "so no modelo"),
                                    ((150, 150, 155), "nos dois")]):
        x = k * 150
        d.rectangle([x, 4, x + 14, 18], fill=cor, outline=BRANCO)
        d.text((x + 20, 4), txt, fill=BRANCO, font=FONTE)
    barra = _barra_calor(0)
    folha = _folha(tiles, 2, titulo, rodape=_empilhar([rod, barra]))
    _salvar(folha, saida / "sobreposicao.png")


def _empilhar(imgs: list[Image.Image]) -> Image.Image:
    w = max(i.width for i in imgs)
    out = Image.new("RGBA", (w, sum(i.height for i in imgs)), BG)
    y = 0
    for i in imgs:
        out.alpha_composite(i, (0, y))
        y += i.height
    return out


def _folha_zoom(ent: _Entradas, saida: Path) -> None:
    celulas = {(n, a): ent.v(n, a) for n in ("arte", "realista") for a in (0, 45)}
    if all(i is None for i in celulas.values()):
        f = Image.new("RGB", (460, 50), BG[:3])
        ImageDraw.Draw(f).text((10, 16), "sem vistas arte/realista a 0 e 45 graus para o zoom", fill=LARANJA, font=FONTE)
        f.save(saida / "zoom.png")
        return
    margem = 2 * ent.E
    x0, y0, x1, y1 = _recorte(list(celulas.values()), ent.tam, margem)
    meio = (y0 + y1) // 2
    z = max(2, -(-ZOOM_ALVO // ent.E))   # ceil: 2x no minimo; E=2 -> 4x, E=4 -> 2x, E=1 -> 8x
    metades = {"cima": (x0, y0, x1, meio), "baixo": (x0, meio, x1, y1)}
    tw, th = (x1 - x0) * z, max(meio - y0, y1 - meio) * z
    rotulos = [f"{n} {a:03d} graus - parte de {m}" for n in ("arte", "realista") for a in (0, 45) for m in metades]
    largura = _largura_tile(tw, rotulos)
    tiles = []
    for a in (0, 45):
        for m, caixa in metades.items():
            for n in ("arte", "realista"):
                im = celulas[(n, a)]
                rot = f"{n} {a:03d} graus - parte de {m} (x{z})"
                if im is None:
                    tiles.append(_tile(rot, VERDE, None, (tw, th), largura, aviso="vista ausente"))
                    continue
                c = _sobre_fundo(im).crop(caixa)
                c = c.resize((c.width * z, c.height * z), Image.BICUBIC)
                bloco = Image.new("RGBA", (tw, th), BG)
                bloco.paste(c, (0, 0))
                tiles.append(_tile(rot, VERDE, bloco, (tw, th), largura))
    _salvar(_folha(tiles, 2), saida / "zoom.png")


# ---------------------------------------------------------------- principal

def gerar(pasta_objeto: Path) -> dict:
    """Gera todas as folhas em `<pasta>/folhas/` e devolve `medidas` ({"contorno_0": IoU, "cor_0": dif})."""
    pasta = Path(pasta_objeto)
    saida = pasta / "folhas"
    saida.mkdir(parents=True, exist_ok=True)
    ent = _Entradas(pasta)

    _folha_comparacao(ent, saida)
    _folha_giro(ent, "arte", saida)
    _folha_giro(ent, "realista", saida)
    _folha_fio(ent, saida)
    cmp = _comparar(ent)
    _folha_sobreposicao(ent, cmp, saida)
    _folha_zoom(ent, saida)

    medidas = {"contorno_0": round(cmp["iou"], 3) if cmp else None,
               "cor_0": round(cmp["cor"], 1) if cmp else None}
    texto = json.dumps(medidas, indent=2)
    (saida / "medidas.json").write_text(texto, encoding="utf-8")
    (pasta / "medidas.json").write_text(texto, encoding="utf-8")
    return medidas


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python -m porte3d.folhas <pasta_objeto>", file=sys.stderr)
        return 2
    print(json.dumps(gerar(Path(argv[0])), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
