#!/usr/bin/env python3
"""
gerar_texturas_pixelart_vanilla.py
==================================
Módulo de Aplicação e Síntese de Texturas Pixel-Art Vanilla (Kentucky 1993)
para os modelos 3D do Project Zomboid (Viewpoint FPS Suite).

- Mapeia e copia texturas oficiais do jogo base (WorldItems e IsoObject).
- Sintetiza texturas pixel-art retrô autênticas para mobílias e eletrodomésticos
  usando paletas canônicas do Zomboid e dithering clássico.
- Ajusta mapeamentos UV em geometrias (.obj / .mtl) para exibição nítida.
"""

import os
import sys
import shutil
from pathlib import Path
from PIL import Image, ImageDraw

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPT_DIR.parent
READY_DIR = MODULE_DIR / "objetos-prontos-3d"

MOVEIS_DIR = READY_DIR / "Moveis-e-Caixas"
ELETRO_DIR = READY_DIR / "Eletrodomesticos"
LOOT_DIR = READY_DIR / "Itens-de-Chao-Loot"

MOVEIS_TEX = MOVEIS_DIR / "textures"
ELETRO_TEX = ELETRO_DIR / "textures"
LOOT_TEX = LOOT_DIR / "textures"

MOVEIS_TEX.mkdir(parents=True, exist_ok=True)
ELETRO_TEX.mkdir(parents=True, exist_ok=True)
LOOT_TEX.mkdir(parents=True, exist_ok=True)

PZ_BASE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\textures")
PZ_WORLDITEMS = PZ_BASE / "WorldItems"
PZ_ISOOBJECT = PZ_BASE / "IsoObject"


def dither_bayer(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
                 c1: tuple, c2: tuple, pattern: str = "checker"):
    """Aplica padrão de dithering de pixel art para transições graduais sem blur."""
    for y in range(y0, y1):
        for x in range(x0, x1):
            if pattern == "checker":
                fill = c1 if (x + y) % 2 == 0 else c2
            elif pattern == "sparse":
                fill = c1 if (x % 2 == 0 and y % 2 == 0) else c2
            else:
                fill = c1
            draw.point((x, y), fill=fill)


# ==============================================================================
# 1. TEXTURAS DE MÓVEIS (MADEIRA E METAL DE GÔNDOLA)
# ==============================================================================

def criar_textura_madeira_crate_vanilla() -> Image.Image:
    """Cria textura 128x128 pixel art de tábuas de madeira estilo carpintaria Zomboid.
    Paleta extraída de IsoObject/carpentry_01_49.png:
      - Sulco profundo: (53, 33, 24)
      - Sombra da madeira: (72, 57, 36)
      - Tom base de pinho: (87, 71, 47)
      - Tom médio quente: (95, 78, 54)
      - Destaque/veio: (112, 92, 65)
      - Beiral de luz: (128, 106, 76)
      - Cantoneiras de metal escuro: (42, 38, 35) e rebites (110, 105, 100)
    """
    size = 128
    img = Image.new("RGB", (size, size), (87, 71, 47))
    draw = ImageDraw.Draw(img)

    num_planks = 4
    plank_h = size // num_planks

    for i in range(num_planks):
        y0 = i * plank_h
        y1 = y0 + plank_h

        # Variação de tom por ripa
        base_color = (
            87 + (i * 7) % 15 - 5,
            71 + (i * 5) % 12 - 4,
            47 + (i * 3) % 9 - 3
        )
        draw.rectangle([0, y0, size - 1, y1 - 1], fill=base_color)

        # Veios de madeira horizontais em pixel-art com dithering sutil
        for y in range(y0 + 3, y1 - 3, 4):
            v_tone = (base_color[0] + 18, base_color[1] + 15, base_color[2] + 12)
            for x in range(0, size, 2):
                if (x + y * 3) % 5 in (0, 1):
                    draw.point((x, y), fill=v_tone)
                    draw.point((x + 1, y), fill=v_tone)

        # Nós de madeira esporádicos
        knot_x = 24 + (i * 37) % 75
        knot_y = y0 + 12
        draw.rectangle([knot_x - 3, knot_y - 2, knot_x + 3, knot_y + 2], fill=(65, 48, 29))
        draw.rectangle([knot_x - 2, knot_y - 1, knot_x + 2, knot_y + 1], fill=(53, 33, 24))
        draw.point((knot_x, knot_y), fill=(40, 24, 16))

        # Chanfro superior (luz) e sulco inferior (sombra) entre ripas
        if i > 0:
            draw.line([(0, y0 - 1), (size - 1, y0 - 1)], fill=(53, 33, 24), width=1)
            draw.line([(0, y0), (size - 1, y0)], fill=(128, 106, 76), width=1)

    # Moldura perimetral externa de reforço (battens de ripas de carvalho)
    border = 10
    frame_color = (78, 63, 38)
    draw.rectangle([0, 0, border - 1, size - 1], fill=frame_color)
    draw.rectangle([size - border, 0, size - 1, size - 1], fill=frame_color)
    draw.rectangle([0, 0, size - 1, border - 1], fill=frame_color)
    draw.rectangle([0, size - border, size - 1, size - 1], fill=frame_color)

    # Cantoneiras metálicas em "L" estilo Zomboid nos 4 cantos
    c_len = 22
    c_thick = 8
    metal_dark = (42, 38, 35)
    metal_hi = (75, 70, 65)

    def draw_l_bracket(bx, by, dx, dy):
        for step_x in range(c_len):
            for step_y in range(c_thick):
                px = bx + step_x * dx
                py = by + step_y * dy
                draw.point((px, py), fill=metal_dark)
        for step_y in range(c_len):
            for step_x in range(c_thick):
                px = bx + step_x * dx
                py = by + step_y * dy
                draw.point((px, py), fill=metal_dark)
        # Rebites com ponto de brilho
        draw.point((bx + 4 * dx, by + 4 * dy), fill=(25, 22, 20))
        draw.point((bx + 4 * dx + 1, by + 4 * dy), fill=metal_hi)
        draw.point((bx + 14 * dx, by + 4 * dy), fill=(25, 22, 20))
        draw.point((bx + 4 * dx, by + 14 * dy), fill=(25, 22, 20))

    draw_l_bracket(0, 0, 1, 1)
    draw_l_bracket(size - 1, 0, -1, 1)
    draw_l_bracket(0, size - 1, 1, -1)
    draw_l_bracket(size - 1, size - 1, -1, -1)

    return img


def criar_textura_gondola_supermercado_vanilla() -> Image.Image:
    """Cria textura 256x256 pixel art para gôndolas e prateleiras de loja.
    Paleta Zomboid:
      - Metal bege/creme: (195, 190, 175) com dithering (175, 170, 155)
      - Furos de pegboard: núcleo (65, 60, 52), borda (130, 125, 115)
      - Fita de preços vermelha: (195, 35, 35)
      - Etiquetas amarelas e brancas com código de barras pixelado
    Atlas:
      - Metade Esquerda (0..128 x 0..256): Painel perfurado e colunas com furos
      - Quadrante Superior Direito (128..256 x 0..128): Bandejas metálicas
      - Quadrante Inferior Direito (128..256 x 128..256): Fita de preços e rodapé
    """
    size = 256
    img = Image.new("RGB", (size, size), (195, 190, 175))
    draw = ImageDraw.Draw(img)

    # 1. Metade Esquerda: Pegboard perfurado com colunas metálicas
    draw.rectangle([0, 0, 127, 255], fill=(185, 180, 165))
    # Dithering de fundo
    dither_bayer(draw, 0, 0, 128, 256, (188, 183, 168), (180, 175, 160))

    # Coluna metálica esquerda (0..16) e direita (112..127)
    for col_x in [0, 112]:
        draw.rectangle([col_x, 0, col_x + 15, 255], fill=(160, 155, 142))
        # Rasgos de encaixe das bandejas
        for slot_y in range(12, 250, 14):
            draw.rectangle([col_x + 5, slot_y, col_x + 9, slot_y + 6], fill=(55, 52, 48))
            draw.line([(col_x + 5, slot_y + 7), (col_x + 9, slot_y + 7)], fill=(210, 205, 192), width=1)

    # Grade de furos perfurados (pegboard) no centro (18..110)
    for py in range(8, 250, 8):
        offset_x = 4 if (py // 8) % 2 == 0 else 0
        for px in range(20 + offset_x, 108, 8):
            draw.rectangle([px, py, px + 1, py + 1], fill=(65, 60, 52))
            draw.point((px + 2, py + 1), fill=(215, 210, 195))

    # 2. Quadrante Superior Direito (128..256 x 0..128): Superfície das bandejas
    draw.rectangle([128, 0, 255, 127], fill=(205, 200, 186))
    dither_bayer(draw, 128, 0, 256, 128, (208, 204, 190), (200, 196, 182))
    # Nervuras de reforço estampadas na chapa metálica
    for rib_x in range(144, 250, 24):
        draw.line([(rib_x, 6), (rib_x, 121)], fill=(165, 160, 148), width=2)
        draw.line([(rib_x + 2, 6), (rib_x + 2, 121)], fill=(225, 222, 210), width=1)

    # 3. Quadrante Inferior Direito (128..256 x 128..256): Fitas de preço e etiquetas
    draw.rectangle([128, 128, 255, 255], fill=(175, 170, 155))

    # 3 Faixas de trilho de preços (para os 3 níveis da gôndola)
    trilho_h = 36
    for i in range(3):
        ty0 = 132 + i * 40
        ty1 = ty0 + trilho_h - 1
        # Borda metálica superior do trilho
        draw.rectangle([132, ty0, 251, ty0 + 3], fill=(140, 136, 125))
        # Fita vermelha clássica de supermercado
        draw.rectangle([132, ty0 + 4, 251, ty1 - 4], fill=(195, 35, 35))
        draw.rectangle([132, ty0 + 4, 251, ty0 + 5], fill=(225, 60, 60))
        # Borda metálica inferior
        draw.rectangle([132, ty1 - 3, 251, ty1], fill=(120, 116, 106))

        # Etiquetas de preço pixeladas amarelas e brancas
        for tag_idx, tag_x in enumerate(range(136, 240, 32)):
            is_promo = (tag_idx % 2 == 1)
            tag_color = (245, 225, 65) if is_promo else (240, 240, 235)
            draw.rectangle([tag_x, ty0 + 8, tag_x + 26, ty1 - 8], fill=tag_color)
            # Código de barras / preço em pixels pretos
            for bar_x in range(tag_x + 3, tag_x + 23, 2):
                if (bar_x + tag_idx) % 3 != 0:
                    draw.line([(bar_x, ty0 + 10), (bar_x, ty1 - 10)], fill=(35, 30, 25), width=1)

    return img


# ==============================================================================
# 2. TEXTURAS DE ELETRODOMÉSTICOS (ESTILO ANOS 90 KENTUCKY)
# ==============================================================================

def criar_textura_fogao_vanilla() -> Image.Image:
    """Cria textura 256x256 pixel art para o fogão de cozinha (kitchen_stove_3d).
    Estilo clássico americano esmaltado almond/bege dos anos 90:
      - Frente (0..128 x 0..256): Porta de forno com visor escuro, puxador e painel de controle
      - Topo (128..256 x 128..256): 4 queimadores espirais elétricos com pratos de gotejamento
      - Laterais (128..256 x 0..128): Esmalte branco/almond
    """
    size = 256
    img = Image.new("RGB", (size, size), (220, 218, 208))
    draw = ImageDraw.Draw(img)

    # 1. Frente (0..128 x 0..256)
    draw.rectangle([0, 0, 127, 255], fill=(220, 218, 208))
    dither_bayer(draw, 0, 0, 128, 256, (222, 220, 210), (218, 216, 206))

    # Painel de controle superior (Y: 0..48)
    draw.rectangle([4, 4, 123, 46], fill=(195, 192, 184))
    draw.line([(4, 46), (123, 46)], fill=(120, 118, 112), width=2)
    # Visor digital LED verde (relógio)
    draw.rectangle([50, 12, 77, 26], fill=(25, 32, 28))
    # Dígitos 12:00 em verde LED pixelado
    draw.line([(55, 15), (55, 23)], fill=(50, 210, 80), width=1)
    draw.line([(60, 15), (66, 15)], fill=(50, 210, 80), width=1)
    draw.line([(63, 17), (63, 18)], fill=(50, 210, 80), width=1)
    draw.line([(63, 21), (63, 22)], fill=(50, 210, 80), width=1)
    # 4 Botões giratórios com ponto indicador vermelho
    for kx in [16, 34, 93, 111]:
        draw.rectangle([kx - 6, 12, kx + 6, 32], fill=(45, 45, 48))
        draw.rectangle([kx - 5, 13, kx + 5, 31], fill=(70, 70, 74))
        draw.point((kx, 15), fill=(220, 45, 35)) # Marcador vermelho

    # Porta do forno (Y: 52..205)
    draw.rectangle([6, 52, 121, 205], fill=(212, 210, 200))
    draw.rectangle([8, 54, 119, 203], fill=(224, 222, 214))

    # Puxador horizontal robusto
    draw.rectangle([18, 62, 109, 72], fill=(48, 48, 52))
    draw.rectangle([20, 64, 107, 70], fill=(85, 85, 90))
    draw.line([(20, 64), (107, 64)], fill=(150, 150, 155), width=1)

    # Visor de vidro escuro do forno com grelha
    draw.rectangle([20, 84, 107, 180], fill=(32, 34, 38))
    # Grelhas horizontais cromadas dentro do visor
    for gy in range(104, 168, 16):
        draw.line([(24, gy), (103, gy)], fill=(90, 95, 102), width=1)
        draw.line([(24, gy + 1), (103, gy + 1)], fill=(55, 58, 62), width=1)

    # Gaveta inferior de assadeiras (Y: 212..250)
    draw.rectangle([6, 212, 121, 248], fill=(210, 208, 198))
    draw.line([(6, 212), (121, 212)], fill=(120, 118, 110), width=1)
    # Recesso para puxar gaveta
    draw.rectangle([44, 224, 83, 230], fill=(55, 55, 58))

    # 2. Topo (128..256 x 0..128): 4 queimadores circulares espirais (Mapeado no Topo V: 0.5..1.0)
    draw.rectangle([128, 0, 255, 127], fill=(225, 223, 215))
    dither_bayer(draw, 128, 0, 256, 128, (228, 226, 218), (222, 220, 212))

    burners = [
        (160, 32, 24),  # Queimador traseiro esquerdo
        (224, 32, 20),  # Queimador traseiro direito
        (160, 96, 20),  # Queimador dianteiro esquerdo
        (224, 96, 26)   # Queimador dianteiro direito (grande)
    ]
    for cx, cy, rad in burners:
        # Prato de gotejamento prateado
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(168, 170, 174), outline=(100, 102, 106))
        # Espiral elétrica de ferro fundido escuro
        for r_step in range(rad - 4, 3, -5):
            draw.ellipse([cx - r_step, cy - r_step, cx + r_step, cy + r_step], outline=(38, 38, 42), width=2)
            draw.point((cx - r_step + 1, cy - r_step + 1), fill=(110, 112, 116))
        draw.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], fill=(45, 45, 48))

    # 3. Laterais (128..256 x 128..256): Esmalte almond com vinco de chapa (Mapeado nas Laterais V: 0.0..0.5)
    draw.rectangle([128, 128, 255, 255], fill=(218, 216, 206))
    dither_bayer(draw, 128, 128, 256, 256, (220, 218, 208), (215, 213, 203))
    # Rodapé inferior preto da lateral
    draw.rectangle([128, 246, 255, 255], fill=(42, 42, 45))

    return img


def criar_textura_geladeira_vanilla() -> Image.Image:
    """Cria textura 256x256 pixel art para a geladeira (kitchen_fridge_3d).
    Estilo anos 90 clássico americano:
      - Frente (0..128 x 0..256): Porta de freezer superior e porta de refrigerador com puxadores
      - Laterais/Topo (128..256 x 0..256): Gabinete esmaltado com textura de chapa
    """
    size = 256
    img = Image.new("RGB", (size, size), (222, 220, 210))
    draw = ImageDraw.Draw(img)

    # 1. Frente (0..128 x 0..256)
    draw.rectangle([0, 0, 127, 255], fill=(222, 220, 210))
    dither_bayer(draw, 0, 0, 128, 256, (224, 222, 212), (218, 216, 206))

    # Beirais chanfrados em relevo
    draw.line([(0, 0), (127, 0)], fill=(245, 243, 235), width=2)
    draw.line([(0, 0), (0, 255)], fill=(245, 243, 235), width=2)
    draw.line([(126, 0), (126, 255)], fill=(160, 158, 150), width=2)

    # Porta superior do Freezer (Y: 6..82)
    draw.rectangle([4, 6, 123, 82], fill=(220, 218, 208))
    # Puxador horizontal embutido do freezer
    draw.rectangle([16, 68, 64, 76], fill=(50, 50, 54))
    draw.line([(16, 68), (64, 68)], fill=(120, 120, 125), width=1)

    # Fresta preta de vedação de borracha (gasket) entre freezer e refrigerador
    draw.rectangle([0, 84, 127, 90], fill=(36, 36, 38))
    draw.line([(0, 91), (127, 91)], fill=(240, 238, 230), width=1)

    # Porta principal do Refrigerador (Y: 92..232)
    draw.rectangle([4, 92, 123, 232], fill=(220, 218, 208))
    # Puxador vertical embutido do refrigerador
    draw.rectangle([16, 102, 26, 172], fill=(50, 50, 54))
    draw.line([(16, 102), (16, 172)], fill=(120, 120, 125), width=1)
    draw.line([(26, 102), (26, 172)], fill=(30, 30, 32), width=1)

    # Grelha de ventilação do condensador no rodapé (Y: 236..255)
    draw.rectangle([0, 236, 127, 255], fill=(38, 38, 42))
    for gy in range(240, 254, 3):
        draw.line([(10, gy), (117, gy)], fill=(65, 65, 70), width=1)

    # 2. Laterais e Topo (128..256 x 0..256)
    draw.rectangle([128, 0, 255, 255], fill=(215, 213, 203))
    dither_bayer(draw, 128, 0, 256, 256, (218, 216, 206), (212, 210, 200))
    # Linha vertical de junção traseira
    draw.line([(254, 0), (254, 255)], fill=(140, 138, 130), width=2)
    # Rodapé preto contínuo na lateral
    draw.rectangle([128, 236, 255, 255], fill=(38, 38, 42))

    return img


def criar_textura_microondas_vanilla() -> Image.Image:
    """Cria textura 256x256 pixel art para o micro-ondas (microwave_oven_3d)."""
    size = 256
    img = Image.new("RGB", (size, size), (220, 218, 208))
    draw = ImageDraw.Draw(img)

    # Face Frontal (0..128 x 0..256)
    draw.rectangle([0, 0, 127, 255], fill=(215, 213, 203))
    dither_bayer(draw, 0, 0, 128, 256, (218, 216, 206), (212, 210, 200))

    # Porta de vidro fumê à esquerda (4..84 x 20..220)
    draw.rectangle([4, 20, 84, 220], fill=(35, 38, 42))
    draw.rectangle([12, 28, 76, 212], fill=(22, 24, 28))
    # Padrão pontilhado anti-radiação na janela do micro-ondas
    for py in range(32, 208, 4):
        for px in range(16, 72, 4):
            draw.point((px, py), fill=(60, 64, 70))

    # Puxador lateral da porta
    draw.rectangle([86, 40, 94, 200], fill=(55, 55, 60))
    draw.line([(86, 40), (86, 200)], fill=(140, 140, 145), width=1)

    # Painel de controle digital à direita (96..124 x 20..220)
    draw.rectangle([98, 20, 124, 220], fill=(42, 44, 48))
    # Visor LED verde fluorescente
    draw.rectangle([101, 26, 121, 46], fill=(12, 22, 16))
    draw.line([(104, 33), (118, 33)], fill=(45, 220, 75), width=1)
    draw.line([(111, 31), (111, 41)], fill=(45, 220, 75), width=1)

    # Teclas numéricas da membrana
    for row in range(4):
        for col in range(2):
            bx = 102 + col * 10
            by = 56 + row * 16
            draw.rectangle([bx, by, bx + 7, by + 10], fill=(70, 74, 80))
            draw.point((bx + 3, by + 4), fill=(210, 215, 220))

    # Botão de Start (verde) e Stop (vermelho)
    draw.rectangle([102, 130, 120, 142], fill=(35, 145, 55)) # Start
    draw.rectangle([102, 148, 120, 160], fill=(185, 40, 35))  # Stop

    # Laterais e topo do gabinete (128..256 x 0..256)
    draw.rectangle([128, 0, 255, 255], fill=(218, 216, 206))
    dither_bayer(draw, 128, 0, 256, 256, (222, 220, 210), (214, 212, 202))
    # Fendas de ventilação lateral
    for vy in range(30, 210, 12):
        draw.line([(140, vy), (245, vy)], fill=(65, 65, 70), width=2)

    return img


def criar_textura_balcao_pia_vanilla() -> Image.Image:
    """Cria textura 256x256 pixel art para o balcão com pia (counter_sink_3d)."""
    size = 256
    img = Image.new("RGB", (size, size), (87, 71, 47))
    draw = ImageDraw.Draw(img)

    # Frente: Portas de armário de madeira de carvalho (0..128 x 0..256)
    draw.rectangle([0, 0, 127, 255], fill=(87, 71, 47))
    dither_bayer(draw, 0, 0, 128, 256, (92, 75, 50), (82, 67, 44))

    # 2 Portas com molduras tipo Shaker
    for p_idx, px0 in enumerate([6, 66]):
        px1 = px0 + 55
        draw.rectangle([px0, 12, px1, 240], fill=(78, 63, 40), outline=(53, 33, 24))
        draw.rectangle([px0 + 6, 20, px1 - 6, 232], fill=(95, 78, 54), outline=(115, 95, 68))
        # Puxador de botão em latão escuro
        knob_x = px1 - 10 if p_idx == 0 else px0 + 10
        draw.rectangle([knob_x - 3, 116, knob_x + 3, 124], fill=(160, 130, 60))
        draw.point((knob_x, 118), fill=(230, 200, 100))

    # Topo: Bancada com cuba de inox embutida (128..256 x 0..128)
    draw.rectangle([128, 0, 255, 127], fill=(190, 185, 172)) # Tampo laminado
    # Cuba de aço inox escovado
    draw.rectangle([148, 16, 235, 111], fill=(155, 158, 164), outline=(100, 102, 108))
    draw.rectangle([154, 22, 229, 105], fill=(130, 133, 140))
    # Ralo da pia no centro da cuba
    draw.ellipse([186, 58, 197, 69], fill=(45, 48, 52), outline=(180, 184, 190))

    # Laterais (128..256 x 128..256)
    draw.rectangle([128, 128, 255, 255], fill=(83, 68, 45))
    dither_bayer(draw, 128, 128, 256, 256, (87, 71, 47), (79, 64, 42))

    return img


# ==============================================================================
# 3. MAPEAMENTO DE GEOMETRIAS OBJ/MTL
# ==============================================================================

def atualizar_shotgun_ammo_box():
    """Gera OBJ e MTL com mapeamento UV preciso da textura BoxOfShotGunShells.png."""
    obj_path = LOOT_DIR / "shotgun_ammo_box_3d.obj"
    mtl_path = LOOT_DIR / "shotgun_ammo_box_3d.mtl"

    mtl_content = """# Material Template Library - Shotgun Ammo Box (Vanilla B42)
newmtl Material
Ka 1.000 1.000 1.000
Kd 1.000 1.000 1.000
Ks 0.150 0.150 0.150
Ns 20.0
d 1.0
illum 2
map_Kd textures/shotgun_ammo_box_3d_diffuse.png
"""
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write(mtl_content)

    # Box dimensions: 0.35m W x 0.22m H x 0.18m D
    hw = 0.35 / 2.0
    hh = 0.22
    hd = 0.18 / 2.0

    obj_content = f"""# Model: shotgun_ammo_box_3d (BoxOfShotGunShells 1993)
# Dimensions (m): 0.350 W x 0.220 H x 0.180 D
mtllib shotgun_ammo_box_3d.mtl
o shotgun_ammo_box_3d

# Vértices (v)
v {-hw:.4f} 0.0000 {-hd:.4f}
v  {hw:.4f} 0.0000 {-hd:.4f}
v  {hw:.4f} {hh:.4f} {-hd:.4f}
v {-hw:.4f} {hh:.4f} {-hd:.4f}
v {-hw:.4f} 0.0000  {hd:.4f}
v  {hw:.4f} 0.0000  {hd:.4f}
v  {hw:.4f} {hh:.4f}  {hd:.4f}
v {-hw:.4f} {hh:.4f}  {hd:.4f}

# Normais (vn)
vn  0.0  0.0 -1.0
vn  0.0  0.0  1.0
vn -1.0  0.0  0.0
vn  1.0  0.0  0.0
vn  0.0  1.0  0.0
vn  0.0 -1.0  0.0

# UVs - Mapeamento para BoxOfShotGunShells.png (64x128):
# Topo da caixa (Tampa Verde 12 Gauge Shells, V: 0.5..1.0, U: 0.5..1.0)
vt 0.5000 0.5000
vt 1.0000 0.5000
vt 1.0000 1.0000
vt 0.5000 1.0000

# Frente (Rótulo SHOTGUN SHELL Verde, V: 0.0..0.5, U: 0.5..1.0)
vt 0.5000 0.0000
vt 1.0000 0.0000
vt 1.0000 0.5000
vt 0.5000 0.5000

# Lateral Direita (Conchas de Espingarda Douradas, V: 0.0..1.0, U: 0.0..0.5)
vt 0.0000 0.0000
vt 0.5000 0.0000
vt 0.5000 1.0000
vt 0.0000 1.0000

# Fundo / Traseira (Papelão neutro, V: 0.0..0.3, U: 0.0..0.5)
vt 0.0000 0.0000
vt 0.5000 0.0000
vt 0.5000 0.3000
vt 0.0000 0.3000

s 1
usemtl Material
# Frente (Rótulo verde)
f 5/5/2 6/6/2 7/7/2 8/8/2
# Traseira
f 2/5/1 1/6/1 4/7/1 3/8/1
# Topo (Tampa com arte oficial)
f 8/1/5 7/2/5 3/3/5 4/4/5
# Fundo
f 1/13/6 2/14/6 6/15/6 5/16/6
# Esquerda
f 1/5/3 5/6/3 8/7/3 4/8/3
# Direita (Conchas douradas)
f 6/9/4 2/10/4 3/11/4 7/12/4
"""
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(obj_content)
    print(f"  [OK] shotgun_ammo_box_3d atualizado com UVs de BoxOfShotGunShells.png")


def atualizar_medical_box():
    """Gera OBJ e MTL com mapeamento UV da maleta FirstAid_Camping.png."""
    obj_path = LOOT_DIR / "medical_box_3d.obj"
    mtl_path = LOOT_DIR / "medical_box_3d.mtl"

    mtl_content = """# Material Template Library - Medical First Aid Box (Vanilla B42)
newmtl Material
Ka 1.000 1.000 1.000
Kd 1.000 1.000 1.000
Ks 0.200 0.200 0.200
Ns 30.0
d 1.0
illum 2
map_Kd textures/medical_box_3d_diffuse.png
"""
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write(mtl_content)

    hw = 0.32 / 2.0
    hh = 0.15
    hd = 0.24 / 2.0

    obj_content = f"""# Model: medical_box_3d (FirstAid_Camping 1993)
# Dimensions (m): 0.320 W x 0.150 H x 0.240 D
mtllib medical_box_3d.mtl
o medical_box_3d

v {-hw:.4f} 0.0000 {-hd:.4f}
v  {hw:.4f} 0.0000 {-hd:.4f}
v  {hw:.4f} {hh:.4f} {-hd:.4f}
v {-hw:.4f} {hh:.4f} {-hd:.4f}
v {-hw:.4f} 0.0000  {hd:.4f}
v  {hw:.4f} 0.0000  {hd:.4f}
v  {hw:.4f} {hh:.4f}  {hd:.4f}
v {-hw:.4f} {hh:.4f}  {hd:.4f}

vn  0.0  0.0 -1.0
vn  0.0  0.0  1.0
vn -1.0  0.0  0.0
vn  1.0  0.0  0.0
vn  0.0  1.0  0.0
vn  0.0 -1.0  0.0

vt 0.0000 0.0000
vt 1.0000 0.0000
vt 1.0000 1.0000
vt 0.0000 1.0000

s 1
usemtl Material
f 5/1/2 6/2/2 7/3/2 8/4/2
f 2/1/1 1/2/1 4/3/1 3/4/1
f 8/1/5 7/2/5 3/3/5 4/4/5
f 1/1/6 2/2/6 6/3/6 5/4/6
f 1/1/3 5/2/3 8/3/3 4/4/3
f 6/1/4 2/2/4 3/3/4 7/4/4
"""
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(obj_content)
    print(f"  [OK] medical_box_3d atualizado com FirstAid_Camping.png")


def atualizar_canned_sardines():
    """Gera OBJ e MTL para a lata de sardinhas CannedSardines.png."""
    obj_path = LOOT_DIR / "canned_sardines_3d.obj"
    mtl_path = LOOT_DIR / "canned_sardines_3d.mtl"

    mtl_content = """# Material Template Library - Canned Sardines (Vanilla B42)
newmtl Material
Ka 1.000 1.000 1.000
Kd 1.000 1.000 1.000
Ks 0.300 0.300 0.300
Ns 45.0
d 1.0
illum 2
map_Kd textures/canned_sardines_diffuse.png
"""
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write(mtl_content)

    hw = 0.110 / 2.0
    hh = 0.040
    hd = 0.065 / 2.0

    obj_content = f"""# Model: canned_sardines_3d (CannedSardines 1993)
# Dimensions (m): 0.110 W x 0.040 H x 0.065 D
mtllib canned_sardines_3d.mtl
o canned_sardines_3d

v {-hw:.4f} 0.0000 {-hd:.4f}
v  {hw:.4f} 0.0000 {-hd:.4f}
v  {hw:.4f} {hh:.4f} {-hd:.4f}
v {-hw:.4f} {hh:.4f} {-hd:.4f}
v {-hw:.4f} 0.0000  {hd:.4f}
v  {hw:.4f} 0.0000  {hd:.4f}
v  {hw:.4f} {hh:.4f}  {hd:.4f}
v {-hw:.4f} {hh:.4f}  {hd:.4f}

vn  0.0  0.0 -1.0
vn  0.0  0.0  1.0
vn -1.0  0.0  0.0
vn  1.0  0.0  0.0
vn  0.0  1.0  0.0
vn  0.0 -1.0  0.0

# Topo da lata com anel pull-tab (V: 0.5..1.0)
vt 0.0000 0.5000
vt 1.0000 0.5000
vt 1.0000 1.0000
vt 0.0000 1.0000

# Lateral metálica da lata (V: 0.0..0.25)
vt 0.0000 0.0000
vt 1.0000 0.0000
vt 1.0000 0.2500
vt 0.0000 0.2500

s 1
usemtl Material
# Frente
f 5/5/2 6/6/2 7/7/2 8/8/2
# Traseira
f 2/5/1 1/6/1 4/7/1 3/8/1
# Topo (Tampa com anel)
f 8/1/5 7/2/5 3/3/5 4/4/5
# Fundo
f 1/5/6 2/6/6 6/7/6 5/8/6
# Esquerda
f 1/5/3 5/6/3 8/7/3 4/8/3
# Direita
f 6/5/4 2/6/4 3/7/4 7/8/4
"""
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(obj_content)
    print(f"  [OK] canned_sardines_3d atualizado com CannedSardines.png")


def atualizar_cilindros_loot():
    """Gera modelos cilíndricos com desdobramento UV contínuo 360° para latas e garrafas."""
    import math

    itens = [
        {
            "name": "canned_beans_3d",
            "tex": "canned_beans_diffuse.png",
            "radius": 0.0425,
            "height": 0.120,
            "segments": 16
        },
        {
            "name": "canned_food_can_3d",
            "tex": "canned_food_can_diffuse.png",
            "radius": 0.0425,
            "height": 0.120,
            "segments": 16
        },
        {
            "name": "water_bottle_3d",
            "tex": "water_bottle_diffuse.png",
            "radius": 0.040,
            "height": 0.240,
            "segments": 16
        }
    ]

    for item in itens:
        name = item["name"]
        radius = item["radius"]
        height = item["height"]
        segs = item["segments"]
        tex = item["tex"]

        obj_file = LOOT_DIR / f"{name}.obj"
        mtl_file = LOOT_DIR / f"{name}.mtl"

        mtl_lines = [
            f"# Material Template Library - {name}",
            "newmtl Material",
            "Ka 1.0 1.0 1.0",
            "Kd 1.0 1.0 1.0",
            "Ks 0.2 0.2 0.2",
            "Ns 30.0",
            "d 1.0",
            "illum 2",
            f"map_Kd textures/{tex}"
        ]
        with open(mtl_file, "w", encoding="utf-8") as f:
            f.write("\n".join(mtl_lines) + "\n")

        vertices = []
        normals = []
        uvs = []

        # Gera vértices e normais
        for i in range(segs):
            angle = (2 * math.pi * i) / segs
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            vertices.append((x, 0.0, z))        # v 2*i + 1
            vertices.append((x, height, z))     # v 2*i + 2
            normals.append((math.cos(angle), 0.0, math.sin(angle)))

        center_bot = len(vertices) + 1
        vertices.append((0.0, 0.0, 0.0))
        center_top = len(vertices) + 1
        vertices.append((0.0, height, 0.0))

        normals.append((0.0, -1.0, 0.0)) # bot normal
        normals.append((0.0, 1.0, 0.0))  # top normal
        bot_norm_idx = len(normals) - 1
        top_norm_idx = len(normals)

        # UVs do manto lateral (desdobramento 360°)
        for i in range(segs + 1):
            u = i / segs
            uvs.append((u, 0.0)) # vt 2*i + 1
            uvs.append((u, 1.0)) # vt 2*i + 2

        center_uv_idx = len(uvs) + 1
        uvs.append((0.5, 0.5))

        lines = [
            f"# Model: {name}",
            f"# Dimensions: Radius {radius:.3f}m, Height {height:.3f}m",
            f"mtllib {name}.mtl",
            f"o {name}",
            ""
        ]

        for v in vertices:
            lines.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
        lines.append("")
        for n in normals:
            lines.append(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}")
        lines.append("")
        for uv in uvs:
            lines.append(f"vt {uv[0]:.4f} {uv[1]:.4f}")
        lines.append("")
        lines.append("s 1")
        lines.append("usemtl Material")

        # Faces laterais com coordenadas contínuas
        for i in range(segs):
            next_i = (i + 1) % segs
            v1 = 2 * i + 1
            v2 = 2 * i + 2
            v3 = 2 * next_i + 2
            v4 = 2 * next_i + 1

            uv1 = 2 * i + 1
            uv2 = 2 * i + 2
            uv3 = 2 * (i + 1) + 2
            uv4 = 2 * (i + 1) + 1

            n1 = i + 1
            n2 = next_i + 1
            lines.append(f"f {v1}/{uv1}/{n1} {v2}/{uv2}/{n1} {v3}/{uv3}/{n2} {v4}/{uv4}/{n2}")

        # Tampo superior e inferior
        for i in range(segs):
            next_i = (i + 1) % segs
            # Topo
            vt1 = 2 * i + 2
            vt2 = 2 * next_i + 2
            lines.append(f"f {center_top}/{center_uv_idx}/{top_norm_idx} {vt1}/{center_uv_idx}/{top_norm_idx} {vt2}/{center_uv_idx}/{top_norm_idx}")
            # Fundo
            vb1 = 2 * i + 1
            vb2 = 2 * next_i + 1
            lines.append(f"f {center_bot}/{center_uv_idx}/{bot_norm_idx} {vb2}/{center_uv_idx}/{bot_norm_idx} {vb1}/{center_uv_idx}/{bot_norm_idx}")

        with open(obj_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  [OK] Cilindro {name} atualizado com UV wrapping contínuo.")


# ==============================================================================
# PIPELINE PRINCIPAL DE EXECUÇÃO
# ==============================================================================

def main():
    print("=================================================================")
    print("  Síntese e Aplicação de Texturas Pixel-Art Vanilla (1993)")
    print("=================================================================")

    # 1. Copiar Texturas Oficiais do Jogo Base
    print("\n[1/3] Copiando e mapeando texturas oficiais do Project Zomboid...")

    # Shotgun Ammo
    shotgun_src = PZ_WORLDITEMS / "BoxOfShotGunShells.png"
    if shotgun_src.exists():
        shutil.copy2(shotgun_src, LOOT_TEX / "shotgun_ammo_box_3d_diffuse.png")
        shutil.copy2(shotgun_src, LOOT_TEX / "military_ammo_can_3d_diffuse.png")
        shutil.copy2(shotgun_src, LOOT_TEX / "BoxOfShotGunShells.png")
        print(f"  [V] Shotgun Shells mapeado: {shotgun_src.name}")

    # First Aid / Medical
    firstaid_src = PZ_WORLDITEMS / "FirstAid_Camping.png"
    if firstaid_src.exists():
        shutil.copy2(firstaid_src, LOOT_TEX / "medical_box_3d_diffuse.png")
        shutil.copy2(firstaid_src, LOOT_TEX / "medical_firstaid_kit_3d_diffuse.png")
        shutil.copy2(firstaid_src, LOOT_TEX / "FirstAid_Camping.png")
        print(f"  [V] First Aid Kit mapeado: {firstaid_src.name}")

    # Canned Sardines
    sardines_src = PZ_WORLDITEMS / "CannedSardines.png"
    if sardines_src.exists():
        shutil.copy2(sardines_src, LOOT_TEX / "canned_sardines_diffuse.png")
        shutil.copy2(sardines_src, LOOT_TEX / "canned_sardines_3d_diffuse.png")
        shutil.copy2(sardines_src, LOOT_TEX / "CannedSardines.png")
        print(f"  [V] Canned Sardines mapeado: {sardines_src.name}")

    # Canned Beans & Food Cans
    beans_src = PZ_WORLDITEMS / "RefriedBeans.png"
    catfood_src = PZ_WORLDITEMS / "CatFood.png"
    if beans_src.exists():
        shutil.copy2(beans_src, LOOT_TEX / "canned_beans_diffuse.png")
        shutil.copy2(beans_src, LOOT_TEX / "canned_beans_3d_diffuse.png")
        print(f"  [V] Canned Beans mapeado: {beans_src.name}")
    if catfood_src.exists():
        shutil.copy2(catfood_src, LOOT_TEX / "canned_food_can_diffuse.png")
        shutil.copy2(catfood_src, LOOT_TEX / "canned_food_can_3d_diffuse.png")
        print(f"  [V] Canned Food Can mapeado: {catfood_src.name}")

    # Water Bottle
    bottle_src = PZ_WORLDITEMS / "WaterBottleFull.png"
    if bottle_src.exists():
        shutil.copy2(bottle_src, LOOT_TEX / "water_bottle_diffuse.png")
        shutil.copy2(bottle_src, LOOT_TEX / "water_bottle_3d_diffuse.png")
        shutil.copy2(bottle_src, LOOT_TEX / "WaterBottleFull.png")
        print(f"  [V] Water Bottle mapeado: {bottle_src.name}")

    # Referência de Carpintaria
    carp_src = PZ_ISOOBJECT / "carpentry_01_49.png"
    if carp_src.exists():
        shutil.copy2(carp_src, MOVEIS_TEX / "carpentry_01_49.png")
        print(f"  [V] Referência de carpintaria copiada: {carp_src.name}")

    # 2. Sintetizar Texturas Pixel-Art com Paleta Vanilla
    print("\n[2/3] Sintetizando texturas pixel-art retrô autênticas...")

    # Crate de madeira
    crate_img = criar_textura_madeira_crate_vanilla()
    crate_img.save(MOVEIS_TEX / "wooden_crate_3d_diffuse.png")
    print(f"  [V] Gerado: wooden_crate_3d_diffuse.png ({crate_img.size})")

    # Gôndola e prateleiras
    shelves_img = criar_textura_gondola_supermercado_vanilla()
    shelves_img.save(MOVEIS_TEX / "store_shelves_3d_diffuse.png")
    shelves_img.save(MOVEIS_TEX / "store_shelf_gondola_diffuse.png")
    shelves_img.save(MOVEIS_TEX / "metal_store_shelf_diffuse.png")
    print(f"  [V] Gerado: store_shelves_3d_diffuse.png ({shelves_img.size})")

    # Fogão
    stove_img = criar_textura_fogao_vanilla()
    stove_img.save(ELETRO_TEX / "kitchen_stove_3d_diffuse.png")
    print(f"  [V] Gerado: kitchen_stove_3d_diffuse.png ({stove_img.size})")

    # Geladeira
    fridge_img = criar_textura_geladeira_vanilla()
    fridge_img.save(ELETRO_TEX / "kitchen_fridge_3d_diffuse.png")
    fridge_img.save(ELETRO_TEX / "refrigerator_3d_diffuse.png")
    print(f"  [V] Gerado: kitchen_fridge_3d_diffuse.png ({fridge_img.size})")

    # Micro-ondas
    micro_img = criar_textura_microondas_vanilla()
    micro_img.save(ELETRO_TEX / "microwave_oven_3d_diffuse.png")
    print(f"  [V] Gerado: microwave_oven_3d_diffuse.png ({micro_img.size})")

    # Balcão com pia
    sink_img = criar_textura_balcao_pia_vanilla()
    sink_img.save(MOVEIS_TEX / "counter_sink_3d_diffuse.png")
    sink_img.save(MOVEIS_TEX / "counter_sink_diffuse.png")
    print(f"  [V] Gerado: counter_sink_3d_diffuse.png ({sink_img.size})")

    # 3. Atualizar Geometrias e UVs
    print("\n[3/3] Atualizando modelos OBJ e MTL com mapeamentos otimizados...")
    atualizar_shotgun_ammo_box()
    atualizar_medical_box()
    atualizar_canned_sardines()
    atualizar_cilindros_loot()

    print("\n[SUCESSO] Todas as texturas vanilla e pixel-art foram geradas e vinculadas!")


if __name__ == "__main__":
    main()
