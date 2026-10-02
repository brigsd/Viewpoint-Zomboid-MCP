#!/usr/bin/env python3
"""
gerar_texturas_e_modelos.py
===========================
Gerador de Texturas PBR Diffuse em Alta Definição (512x512) com Pillow
e Modelador da Gôndola de Supermercado (store_shelves_3d).

Gera texturas ricas com veios de madeira, metais escovados, vidros fumê,
queimadores, estênceis militares, cruzes médicas e fitas de preços de gôndola.
"""

import os
import sys
import math
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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


def get_font(size: int):
    """Obtém fonte padrão do sistema ou default."""
    try:
        # Tenta fontes padrão do Windows
        font_paths = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/consola.ttf",
            "C:/Windows/Fonts/segoeuib.ttf"
        ]
        for p in font_paths:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    except Exception:
        pass
    return ImageFont.load_default()


def criar_textura_madeira_crate() -> Image.Image:
    """1. wooden_crate_3d_diffuse.png (512x512)
    Tábuas de madeira rústica, veios, pregos e cantoneiras de reforço em metal.
    """
    img = Image.new("RGBA", (512, 512), (180, 134, 78, 255))
    draw = ImageDraw.Draw(img)

    # 4 Tábuas horizontais com gradiente e veios
    num_planks = 4
    plank_h = 512 // num_planks

    for i in range(num_planks):
        y0 = i * plank_h
        y1 = y0 + plank_h
        # Variação de tom por tábua
        base_r = 160 + (i * 13) % 25
        base_g = 115 + (i * 11) % 20
        base_b = 65 + (i * 7) % 15
        draw.rectangle([0, y0, 512, y1], fill=(base_r, base_g, base_b, 255))

        # Veios de madeira (linhas finas com variações sutis)
        for y in range(y0 + 2, y1 - 2, 4):
            tone = (base_r - 18, base_g - 15, base_b - 12, 255)
            draw.line([(0, y), (512, y + (y % 3 - 1))], fill=tone, width=1)

        # Sulco escuro entre tábuas
        draw.line([(0, y1 - 1), (512, y1 - 1)], fill=(50, 32, 16, 255), width=3)
        draw.line([(0, y1 + 1), (512, y1 + 1)], fill=(210, 165, 105, 255), width=1)

    # Moldura de reforço perimetral em madeira escura
    border_w = 40
    # Batentes verticais
    draw.rectangle([0, 0, border_w, 512], fill=(140, 95, 52, 255))
    draw.rectangle([512 - border_w, 0, 512, 512], fill=(140, 95, 52, 255))
    # Batentes horizontais
    draw.rectangle([0, 0, 512, border_w], fill=(132, 90, 48, 255))
    draw.rectangle([0, 512 - border_w, 512, 512], fill=(132, 90, 48, 255))

    # Cantoneiras de metal escuro (L-brackets) nos 4 cantos
    c_size = 70
    bracket_col = (45, 48, 52, 255)
    bracket_hi = (90, 94, 100, 255)

    cantos = [
        (0, 0, 1, 1),
        (512 - c_size, 0, -1, 1),
        (0, 512 - c_size, 1, -1),
        (512 - c_size, 512 - c_size, -1, -1)
    ]
    for x, y, dx, dy in cantos:
        # L-shape
        draw.rectangle([x, y, x + c_size, y + 24], fill=bracket_col)
        draw.rectangle([x, y, x + 24, y + c_size], fill=bracket_col)
        # Highlight
        draw.line([(x, y), (x + c_size, y)], fill=bracket_hi, width=1)
        draw.line([(x, y), (x, y + c_size)], fill=bracket_hi, width=1)

    # Pregos / Rebites de aço nos batentes e cantoneiras
    pontos_pregos = [
        (12, 12), (50, 12), (12, 50),
        (500, 12), (462, 12), (500, 50),
        (12, 500), (50, 500), (12, 462),
        (500, 500), (462, 500), (500, 462),
        (256, 18), (256, 494), (18, 256), (494, 256)
    ]
    for px, py in pontos_pregos:
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(25, 27, 30, 255))
        draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(70, 74, 80, 255))
        draw.point((px - 1, py - 1), fill=(180, 185, 190, 255))

    # Carimbo estêncil militar / carga no centro
    font = get_font(28)
    draw.text((256, 230), "CARGO-42", font=font, fill=(40, 26, 12, 180), anchor="mm")
    font_sub = get_font(18)
    draw.text((256, 265), "SURVIVAL STOCK - U.S.", font=font_sub, fill=(45, 30, 15, 160), anchor="mm")

    return img


def criar_textura_fogao_stove() -> Image.Image:
    """2. kitchen_stove_3d_diffuse.png (512x512)
    Atlas inteligente:
    - Metade Esquerda (0..256): Painel Frontal (Porta de vidro fumê do forno, puxador inox, botões)
    - Quadrante Superior Direito (256..512, 0..256): Topo com 4 queimadores circulares pretos
    - Quadrante Inferior Direito (256..512, 256..512): Laterais e traseira em esmalte branco
    """
    img = Image.new("RGBA", (512, 512), (242, 244, 247, 255))
    draw = ImageDraw.Draw(img)

    # Separador sutil do atlas
    draw.line([(256, 0), (256, 512)], fill=(200, 204, 210, 255), width=2)
    draw.line([(256, 256), (512, 256)], fill=(200, 204, 210, 255), width=2)

    # -------------------------------------------------------------
    # 1. PAINEL FRONTAL DO FOGÃO (0..256 x 0..512)
    # -------------------------------------------------------------
    # Faixa superior de controle (0..256, 0..85)
    draw.rectangle([0, 0, 256, 85], fill=(230, 233, 238, 255))
    draw.line([(0, 85), (256, 85)], fill=(170, 175, 182, 255), width=2)

    # Display digital do forno (centro superior)
    draw.rectangle([98, 18, 158, 48], fill=(15, 18, 22, 255))
    font_clock = get_font(18)
    draw.text((128, 33), "350°F", font=font_clock, fill=(0, 230, 118, 255), anchor="mm")

    # 4 Botões rotativos dos queimadores
    botoes_x = [30, 68, 188, 226]
    for bx in botoes_x:
        draw.ellipse([bx - 14, 18, bx + 14, 46], fill=(40, 44, 50, 255))
        draw.ellipse([bx - 10, 22, bx + 10, 42], fill=(195, 200, 208, 255))
        draw.line([(bx, 22), (bx, 30)], fill=(30, 32, 35, 255), width=2)

    # Puxador horizontal tubular de inox da porta do forno
    draw.rectangle([35, 105, 221, 120], fill=(170, 175, 182, 255))
    draw.rectangle([35, 107, 221, 115], fill=(235, 238, 242, 255))
    draw.rectangle([30, 102, 42, 123], fill=(110, 115, 122, 255))
    draw.rectangle([214, 102, 226, 123], fill=(110, 115, 122, 255))

    # Janela de Vidro Fumê Escuro da porta do forno
    draw.rectangle([28, 135, 228, 415], fill=(28, 32, 38, 255))
    # Borda interna e reflexo diagonal no vidro
    draw.rectangle([32, 139, 224, 411], outline=(55, 62, 72, 255), width=2)
    # Gradiente/grelhas internas visíveis através do vidro
    for gy in range(180, 390, 45):
        draw.line([(45, gy), (211, gy)], fill=(45, 50, 58, 255), width=2)
    # Brilho diagonal
    draw.line([(50, 380), (190, 160)], fill=(75, 88, 105, 180), width=4)

    # Gaveta inferior / rodapé do forno (430..512)
    draw.line([(0, 430), (256, 430)], fill=(160, 165, 172, 255), width=2)
    draw.rectangle([20, 455, 236, 465], fill=(200, 205, 212, 255))
    draw.rectangle([0, 495, 256, 512], fill=(35, 38, 42, 255))

    # -------------------------------------------------------------
    # 2. TOPO DO FOGÃO COM 4 BOCAS CIRCULARES (256..512 x 0..256)
    # -------------------------------------------------------------
    draw.rectangle([256, 0, 512, 256], fill=(245, 247, 250, 255))
    draw.rectangle([258, 2, 510, 254], outline=(205, 210, 216, 255), width=3)

    queimadores = [
        (320, 64, 42),   # Traseiro esquerdo (médio)
        (448, 64, 34),   # Traseiro direito (pequeno)
        (320, 192, 48),  # Frontal esquerdo (grande)
        (448, 192, 42),  # Frontal direito (médio)
    ]
    for qx, qy, r in queimadores:
        # Bacia rebaixada
        draw.ellipse([qx - r - 4, qy - r - 4, qx + r + 4, qy + r + 4], fill=(210, 214, 220, 255))
        # Grade/queimador ferro fundido preto
        draw.ellipse([qx - r, qy - r, qx + r, qy + r], fill=(30, 33, 37, 255))
        # Espiral / queimador interno
        draw.ellipse([qx - r + 8, qy - r + 8, qx + r - 8, qy + r - 8], outline=(65, 70, 78, 255), width=4)
        draw.ellipse([qx - r + 18, qy - r + 18, qx + r - 18, qy + r - 18], fill=(22, 24, 27, 255))
        # Ponto central
        draw.ellipse([qx - 6, qy - 6, qx + 6, qy + 6], fill=(90, 95, 105, 255))

    # -------------------------------------------------------------
    # 3. LATERAIS / TRASEIRA EM ESMALTE BRANCO (256..512 x 256..512)
    # -------------------------------------------------------------
    draw.rectangle([256, 256, 512, 512], fill=(240, 242, 246, 255))
    # Parafusos sutis e costura de chapa esmaltada
    draw.line([(260, 260), (260, 508)], fill=(215, 220, 226, 255), width=1)
    draw.line([(508, 260), (508, 508)], fill=(215, 220, 226, 255), width=1)
    draw.rectangle([256, 500, 512, 512], fill=(35, 38, 42, 255)) # Rodapé

    return img


def criar_textura_geladeira_fridge() -> Image.Image:
    """3. kitchen_fridge_3d_diffuse.png (512x512)
    Geladeira branca/inox:
    - Metade Esquerda (0..256): Painel Frontal com porta superior (freezer),
      divisória com borracha de vedação, porta inferior e puxadores inox verticais.
    - Metade Direita (256..512): Laterais e topo em inox/esmalte escovado.
    """
    img = Image.new("RGBA", (512, 512), (238, 241, 245, 255))
    draw = ImageDraw.Draw(img)

    # Linha divisória do atlas
    draw.line([(256, 0), (256, 512)], fill=(195, 200, 208, 255), width=2)

    # -------------------------------------------------------------
    # 1. FRENTE DA GELADEIRA (0..256 x 0..512)
    # -------------------------------------------------------------
    # Porta do Freezer Superior (0..256 x 0..170)
    draw.rectangle([0, 0, 256, 170], fill=(244, 246, 250, 255))
    draw.rectangle([4, 4, 252, 166], outline=(218, 223, 230, 255), width=2)

    # Emblema / Logotipo da marca ("POLAR-TECH B42")
    font_logo = get_font(13)
    draw.text((128, 22), "❄ POLAR-TECH 42", font=font_logo, fill=(90, 110, 135, 255), anchor="mm")

    # Puxador vertical do Freezer (lado direito)
    draw.rectangle([228, 40, 240, 140], fill=(160, 166, 174, 255))
    draw.rectangle([230, 42, 238, 138], fill=(225, 230, 238, 255))

    # Divisória entre Freezer e Refrigerador com vedação preta (170..184)
    draw.rectangle([0, 170, 256, 184], fill=(32, 35, 40, 255))
    draw.line([(0, 170), (256, 170)], fill=(150, 155, 162, 255), width=1)
    draw.line([(0, 184), (256, 184)], fill=(150, 155, 162, 255), width=1)

    # Porta Inferior do Refrigerador (184..490)
    draw.rectangle([0, 184, 256, 490], fill=(244, 246, 250, 255))
    draw.rectangle([4, 188, 252, 486], outline=(218, 223, 230, 255), width=2)

    # Puxador vertical longo do Refrigerador (lado direito)
    draw.rectangle([228, 205, 240, 395], fill=(160, 166, 174, 255))
    draw.rectangle([230, 207, 238, 393], fill=(225, 230, 238, 255))

    # Rodapé preto / grade do compressor (490..512)
    draw.rectangle([0, 490, 256, 512], fill=(25, 28, 32, 255))
    for gx in range(15, 245, 12):
        draw.line([(gx, 495), (gx, 507)], fill=(50, 54, 60, 255), width=2)

    # -------------------------------------------------------------
    # 2. LATERAIS / TOPO DA GELADEIRA (256..512 x 0..512)
    # -------------------------------------------------------------
    draw.rectangle([256, 0, 512, 512], fill=(235, 238, 242, 255))
    # Efeito sutil de aço escovado
    for y in range(0, 512, 3):
        shade = 230 + (y % 11)
        draw.line([(258, y), (512, y)], fill=(shade, shade + 2, shade + 5, 255), width=1)

    # Rodapé lateral
    draw.rectangle([256, 490, 512, 512], fill=(25, 28, 32, 255))

    return img


def criar_textura_microondas() -> Image.Image:
    """4. microwave_oven_3d_diffuse.png (512x512)
    Atlas inteligente:
    - Metade Superior (0..512 x 0..256): Painel Frontal (porta com visor fumê, display LED 12:00, teclado numérico)
    - Metade Inferior Esquerda (0..256 x 256..512): Topo (chassi escuro escovado com nervuras)
    - Metade Inferior Direita (256..512 x 256..512): Lateral com aletas de ventilação e grelha
    """
    img = Image.new("RGBA", (512, 512), (36, 39, 45, 255))
    draw = ImageDraw.Draw(img)

    # -------------------------------------------------------------
    # 1. PAINEL FRONTAL DO MICRO-ONDAS (0..512 x 0..256)
    # -------------------------------------------------------------
    draw.rectangle([0, 0, 512, 256], fill=(32, 35, 40, 255))
    draw.rectangle([4, 4, 508, 252], outline=(65, 70, 78, 255), width=2)

    # Porta com visor fumê no lado esquerdo (12..350 x 10..246)
    draw.rectangle([12, 10, 350, 246], fill=(18, 20, 24, 255), outline=(75, 80, 90, 255), width=2)
    # Visor interno com malha de blindagem contra micro-ondas
    draw.rectangle([35, 25, 325, 230], fill=(10, 12, 15, 255))
    for my in range(30, 226, 6):
        for mx in range(40, 320, 6):
            draw.point((mx, my), fill=(35, 38, 44, 255))

    # Puxador embutido / alça da porta
    draw.rectangle([335, 60, 343, 195], fill=(170, 175, 185, 255))

    # Painel de controle no lado direito (358..504 x 10..246)
    draw.rectangle([358, 10, 504, 246], fill=(22, 24, 28, 255), outline=(50, 55, 62, 255), width=1)

    # Display digital LED "12:00"
    draw.rectangle([366, 18, 496, 58], fill=(5, 8, 10, 255))
    draw.rectangle([367, 19, 495, 57], outline=(0, 200, 83, 120), width=1)
    font_clock = get_font(20)
    draw.text((431, 38), "12:00", font=font_clock, fill=(0, 230, 118, 255), anchor="mm")

    # Funções rápidas
    font_fn = get_font(9)
    draw.rectangle([368, 66, 428, 82], fill=(40, 44, 52, 255))
    draw.text((398, 74), "POPCORN", font=font_fn, fill=(210, 215, 225, 255), anchor="mm")

    draw.rectangle([434, 66, 494, 82], fill=(40, 44, 52, 255))
    draw.text((464, 74), "DEFROST", font=font_fn, fill=(210, 215, 225, 255), anchor="mm")

    # Teclado numérico compacto (90..185)
    font_num = get_font(10)
    nums = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["PWR", "0", "START"]
    ]
    for r_idx, row in enumerate(nums):
        ny = 92 + r_idx * 22
        for c_idx, val in enumerate(row):
            nx = 372 + c_idx * 42
            col_bg = (0, 150, 136, 255) if val == "START" else (45, 48, 56, 255)
            draw.rectangle([nx, ny, nx + 38, ny + 18], fill=col_bg)
            draw.text((nx + 19, ny + 9), val, font=font_num, fill=(255, 255, 255, 255), anchor="mm")

    # Botão de Abertura mecânica
    draw.rectangle([368, 195, 494, 238], fill=(58, 62, 70, 255))
    draw.rectangle([372, 199, 490, 234], fill=(44, 48, 54, 255))
    font_open = get_font(12)
    draw.text((431, 216), "OPEN / PUSH", font=font_open, fill=(220, 225, 235, 255), anchor="mm")

    # -------------------------------------------------------------
    # 2. TOPO DO CHASSI (0..256 x 256..512)
    # -------------------------------------------------------------
    draw.rectangle([0, 256, 256, 512], fill=(40, 44, 50, 255))
    for y in range(256, 512, 3):
        shade = 38 + (y % 6)
        draw.line([(0, y), (256, y)], fill=(shade, shade + 3, shade + 6, 255), width=1)
    draw.rectangle([10, 266, 246, 502], outline=(30, 33, 38, 255), width=2)

    # -------------------------------------------------------------
    # 3. LATERAIS COM ALETAS DE VENTILAÇÃO (256..512 x 256..512)
    # -------------------------------------------------------------
    draw.rectangle([256, 256, 512, 512], fill=(38, 42, 48, 255))
    # Grelha de refrigeração
    for ly in range(280, 480, 10):
        draw.line([(280, ly), (488, ly)], fill=(20, 22, 26, 255), width=4)
        draw.line([(280, ly - 1), (488, ly - 1)], fill=(55, 60, 68, 255), width=1)

    return img


def criar_textura_maleta_medica() -> Image.Image:
    """5. medical_box_3d_diffuse.png (512x512)
    Maleta médica de primeiros socorros branca com cruz vermelha e fechos metálicos.
    """
    img = Image.new("RGBA", (512, 512), (246, 248, 250, 255))
    draw = ImageDraw.Draw(img)

    # Borda emborrachada / perfil de proteção da maleta
    draw.rectangle([0, 0, 512, 512], fill=(245, 247, 250, 255))
    draw.rectangle([10, 10, 502, 502], outline=(205, 212, 220, 255), width=8)

    # Cantos arredondados de proteção de impacto
    c_rad = 35
    for cx, cy in [(10, 10), (502 - c_rad, 10), (10, 502 - c_rad), (502 - c_rad, 502 - c_rad)]:
        draw.rectangle([cx, cy, cx + c_rad, cy + c_rad], fill=(215, 220, 228, 255))

    # Círculo branco de destaque para a cruz
    draw.ellipse([140, 140, 372, 372], fill=(255, 255, 255, 255), outline=(220, 225, 232, 255), width=3)

    # Cruz Vermelha Médica Proeminente
    cross_col = (211, 47, 47, 255) # Vermelho Cruz Vermelha oficial (#d32f2f)
    # Braço Vertical
    draw.rectangle([226, 160, 286, 352], fill=cross_col)
    # Braço Horizontal
    draw.rectangle([160, 226, 352, 286], fill=cross_col)

    # Textos Oficiais
    font_title = get_font(28)
    draw.text((256, 75), "FIRST AID KIT", font=font_title, fill=(35, 40, 48, 255), anchor="mm")

    font_sub = get_font(15)
    draw.text((256, 430), "EMERGENCY MEDICAL RESPONSE", font=font_sub, fill=(211, 47, 47, 255), anchor="mm")
    draw.text((256, 455), "TRAUMA & FIELD TREATMENT UNIT", font=get_font(12), fill=(100, 108, 118, 255), anchor="mm")

    # Fechos de trava metálicos nas bordas
    fechos = [(120, 8), (392, 8), (120, 488), (392, 488)]
    for fx, fy in fechos:
        draw.rectangle([fx - 25, fy, fx + 25, fy + 16], fill=(120, 126, 135, 255))
        draw.rectangle([fx - 20, fy + 2, fx + 20, fy + 14], fill=(190, 195, 202, 255))
        draw.rectangle([fx - 8, fy + 4, fx + 8, fy + 12], fill=(50, 54, 60, 255))

    return img


def criar_textura_caixa_municao() -> Image.Image:
    """6. shotgun_ammo_box_3d_diffuse.png (512x512)
    Caixa de munição militar verde-oliva com estêncil amarelo autêntico.
    """
    img = Image.new("RGBA", (512, 512), (60, 72, 44, 255)) # Verde oliva militar (#3c482c)
    draw = ImageDraw.Draw(img)

    # Borda em relevo de estampagem de chapa de aço da ammo can
    draw.rectangle([8, 8, 504, 504], outline=(40, 50, 28, 255), width=8)
    draw.rectangle([16, 16, 496, 496], outline=(85, 100, 65, 255), width=3)

    # Nervuras de reforço estrutural da chapa de aço
    draw.rectangle([45, 100, 467, 120], fill=(46, 56, 32, 255))
    draw.line([(45, 100), (467, 100)], fill=(88, 104, 68, 255), width=2)

    draw.rectangle([45, 390, 467, 410], fill=(46, 56, 32, 255))
    draw.line([(45, 390), (467, 390)], fill=(88, 104, 68, 255), width=2)

    # Estêncil Amarelo Militar
    yellow_stencil = (253, 216, 53, 240) # #fdd835

    font_huge = get_font(34)
    draw.text((256, 175), "12 GA 00 BUCKSHOT", font=font_huge, fill=yellow_stencil, anchor="mm")

    font_med = get_font(22)
    draw.text((256, 230), "2-3/4 IN.  •  9 PELLETS", font=font_med, fill=yellow_stencil, anchor="mm")

    font_reg = get_font(18)
    draw.text((256, 280), "250 SHOTSHELLS  •  PLASTIC CASES", font=font_reg, fill=yellow_stencil, anchor="mm")

    font_small = get_font(15)
    draw.text((256, 325), "LOT WCC-93K-001  •  ORDNANCE CORPS U.S.", font=font_small, fill=yellow_stencil, anchor="mm")

    # Ícone militar de munição / bomba incendiária no topo
    draw.ellipse([240, 45, 272, 77], outline=yellow_stencil, width=3)
    draw.line([(256, 35), (256, 87)], fill=yellow_stencil, width=3)
    draw.line([(240, 61), (272, 61)], fill=yellow_stencil, width=3)

    # Parafusos / rebites da trava da tampa
    draw.rectangle([216, 450, 296, 490], fill=(42, 50, 30, 255))
    draw.rectangle([220, 454, 292, 486], fill=(75, 88, 58, 255))
    draw.ellipse([230, 465, 242, 477], fill=(25, 30, 18, 255))
    draw.ellipse([270, 465, 282, 477], fill=(25, 30, 18, 255))

    return img


def criar_textura_balcao_pia() -> Image.Image:
    """7. counter_sink_3d_diffuse.png (512x512)
    Atlas inteligente:
    - Metade Esquerda (0..256 x 0..512): Portas de armário de madeira com puxadores
    - Quadrante Superior Direito (256..512 x 0..256): Cuba de pia em aço inox com ralo e torneira
    - Quadrante Inferior Direito (256..512 x 256..512): Laterais do balcão de madeira
    """
    img = Image.new("RGBA", (512, 512), (120, 80, 45, 255))
    draw = ImageDraw.Draw(img)

    # -------------------------------------------------------------
    # 1. FRENTE DO ARMÁRIO DE MADEIRA (0..256 x 0..512)
    # -------------------------------------------------------------
    # Tom base de madeira nobre
    draw.rectangle([0, 0, 256, 512], fill=(125, 82, 42, 255))
    # Veios de madeira verticais
    for x in range(0, 256, 4):
        tone = 115 + (x * 7) % 20
        draw.line([(x, 0), (x, 512)], fill=(tone, tone - 40, tone - 75, 255), width=1)

    # Rodapé inferior preto (470..512)
    draw.rectangle([0, 470, 256, 512], fill=(40, 28, 18, 255))

    # Gaveta superior falsa (0..95)
    draw.rectangle([12, 12, 244, 85], fill=(110, 72, 35, 255), outline=(60, 38, 18, 255), width=2)
    # Puxador horizontal da gaveta
    draw.rectangle([98, 44, 158, 54], fill=(195, 200, 208, 255))
    draw.rectangle([94, 42, 102, 56], fill=(110, 115, 122, 255))
    draw.rectangle([154, 42, 162, 56], fill=(110, 115, 122, 255))

    # Duas portas de armário (porta esquerda: 12..124, porta direita: 132..244)
    # Porta Esquerda
    draw.rectangle([12, 105, 124, 455], fill=(110, 72, 35, 255), outline=(60, 38, 18, 255), width=2)
    draw.rectangle([24, 117, 112, 443], fill=(120, 78, 38, 255), outline=(75, 48, 24, 255), width=2)
    # Puxador vertical da porta esquerda
    draw.rectangle([106, 210, 114, 270], fill=(210, 215, 222, 255))

    # Porta Direita
    draw.rectangle([132, 105, 244, 455], fill=(110, 72, 35, 255), outline=(60, 38, 18, 255), width=2)
    draw.rectangle([144, 117, 232, 443], fill=(120, 78, 38, 255), outline=(75, 48, 24, 255), width=2)
    # Puxador vertical da porta direita
    draw.rectangle([142, 210, 150, 270], fill=(210, 215, 222, 255))

    # -------------------------------------------------------------
    # 2. TOPO: CUBA DE PIA EM AÇO INOX (256..512 x 0..256)
    # -------------------------------------------------------------
    # Bancada em inox escovado
    draw.rectangle([256, 0, 512, 256], fill=(185, 192, 200, 255))
    draw.rectangle([258, 2, 510, 254], outline=(140, 146, 155, 255), width=3)

    # Cuba retangular rebaixada
    draw.rectangle([285, 40, 483, 225], fill=(95, 102, 112, 255))
    draw.rectangle([289, 44, 479, 221], fill=(130, 138, 148, 255))
    draw.rectangle([295, 50, 473, 215], fill=(110, 117, 126, 255))

    # Ralo com grelha metálica no centro da cuba
    draw.ellipse([372, 120, 404, 152], fill=(45, 48, 52, 255))
    draw.ellipse([376, 124, 400, 148], fill=(180, 185, 192, 255))
    draw.ellipse([384, 132, 392, 140], fill=(20, 22, 25, 255))

    # Torneira e registros no topo da bancada (Y: 10..35)
    draw.ellipse([378, 14, 398, 34], fill=(230, 235, 240, 255), outline=(130, 136, 145, 255), width=2)
    # Registro água quente (vermelho) e fria (azul)
    draw.ellipse([345, 18, 357, 30], fill=(211, 47, 47, 255))
    draw.ellipse([419, 18, 431, 30], fill=(25, 118, 210, 255))

    # -------------------------------------------------------------
    # 3. LATERAL DO BALCÃO EM MADEIRA (256..512 x 256..512)
    # -------------------------------------------------------------
    draw.rectangle([256, 256, 512, 512], fill=(120, 78, 40, 255))
    for x in range(256, 512, 4):
        tone = 112 + (x * 5) % 18
        draw.line([(x, 256), (x, 512)], fill=(tone, tone - 40, tone - 75, 255), width=1)
    # Moldura de painel lateral
    draw.rectangle([268, 268, 500, 470], outline=(75, 48, 24, 255), width=3)
    draw.rectangle([256, 470, 512, 512], fill=(40, 28, 18, 255)) # Rodapé

    return img


def criar_textura_gondola_mercado() -> Image.Image:
    """8. store_shelves_3d_diffuse.png (512x512)
    Acabamento em aço esmaltado creme/branco, perfurações de gôndola nas laterais
    e fita vermelha/azul de preços na borda das bandejas.
    Atlas:
    - Metade Esquerda (0..256 x 0..512): Painel traseiro e colunas com furos
    - Quadrante Superior Direito (256..512 x 0..256): Superfície horizontal das bandejas
    - Quadrante Inferior Direito (256..512 x 256..512): Fitas de preços (vermelha e azul) com códigos de barra
    """
    img = Image.new("RGBA", (512, 512), (236, 233, 224, 255)) # Creme esmaltado (#ece9e0)
    draw = ImageDraw.Draw(img)

    # -------------------------------------------------------------
    # 1. PAINEL TRASEIRO E COLUNAS DE SUSTENTAÇÃO (0..256 x 0..512)
    # -------------------------------------------------------------
    draw.rectangle([0, 0, 256, 512], fill=(232, 229, 220, 255))

    # Coluna vertical de encaixe da esquerda (0..35)
    draw.rectangle([0, 0, 35, 512], fill=(215, 211, 200, 255))
    draw.line([(35, 0), (35, 512)], fill=(175, 170, 160, 255), width=2)

    # Coluna vertical de encaixe da direita (221..256)
    draw.rectangle([221, 0, 256, 512], fill=(215, 211, 200, 255))
    draw.line([(221, 0), (221, 512)], fill=(175, 170, 160, 255), width=2)

    # Furos retangulares para encaixe dos suportes das prateleiras (gondola slots)
    for y in range(20, 500, 16):
        # Slots coluna esquerda
        draw.rectangle([14, y, 22, y + 8], fill=(60, 62, 65, 255))
        # Slots coluna direita
        draw.rectangle([234, y, 242, y + 8], fill=(60, 62, 65, 255))

    # Grade perfurada (pegboard) no centro do painel traseiro
    for py in range(25, 495, 22):
        for px in range(50, 210, 22):
            draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(130, 126, 118, 255))

    # -------------------------------------------------------------
    # 2. BANDEJAS HORIZONTAIS DE AÇO (256..512 x 0..256)
    # -------------------------------------------------------------
    draw.rectangle([256, 0, 512, 256], fill=(240, 238, 231, 255))
    draw.rectangle([258, 2, 510, 254], outline=(195, 190, 180, 255), width=2)

    # Nervuras de reforço estrutural da chapa de aço das bandejas
    for ry in range(20, 240, 28):
        draw.line([(265, ry), (501, ry)], fill=(215, 210, 200, 255), width=2)
        draw.line([(265, ry + 1), (501, ry + 1)], fill=(255, 255, 255, 255), width=1)

    # -------------------------------------------------------------
    # 3. FITAS DE PREÇOS (256..512 x 256..512)
    # -------------------------------------------------------------
    draw.rectangle([256, 256, 512, 512], fill=(225, 222, 214, 255))

    # FITA 1: AZUL (Canaleta de preço de gôndola)
    draw.rectangle([256, 265, 512, 335], fill=(21, 101, 192, 255)) # Azul (#1565c0)
    draw.line([(256, 265), (512, 265)], fill=(13, 71, 161, 255), width=2)
    draw.line([(256, 335), (512, 335)], fill=(100, 181, 246, 255), width=2)

    # Etiquetas de preços brancas na fita azul
    etiquetas_azul = [
        ("CANNED SOUP", "$ 1.89", 265),
        ("SODA CAN", "$ 0.99", 345),
        ("CEREAL BOX", "$ 3.49", 425)
    ]
    font_item = get_font(9)
    font_price = get_font(12)

    for item, preco, ex in etiquetas_azul:
        draw.rectangle([ex, 273, ex + 72, 327], fill=(255, 255, 255, 255))
        draw.text((ex + 36, 283), item, font=font_item, fill=(20, 20, 20, 255), anchor="mm")
        draw.text((ex + 36, 303), preco, font=font_price, fill=(180, 20, 20, 255), anchor="mm")
        # Mini código de barras
        for bx in range(ex + 10, ex + 62, 3):
            if (bx % 2 == 0):
                draw.line([(bx, 314), (bx, 323)], fill=(0, 0, 0, 255), width=1)

    # FITA 2: VERMELHA (Canaleta promocional de gôndola)
    draw.rectangle([256, 360, 512, 430], fill=(198, 40, 40, 255)) # Vermelho (#c62828)
    draw.line([(256, 360), (512, 360)], fill=(140, 25, 25, 255), width=2)
    draw.line([(256, 430), (512, 430)], fill=(239, 154, 154, 255), width=2)

    etiquetas_red = [
        ("POTATO CHIPS", "$ 2.19", 265),
        ("CHOCOLATE", "$ 1.49", 345),
        ("WATER BOTTLE", "$ 0.89", 425)
    ]
    for item, preco, ex in etiquetas_red:
        draw.rectangle([ex, 368, ex + 72, 422], fill=(255, 255, 255, 255))
        draw.text((ex + 36, 378), item, font=font_item, fill=(20, 20, 20, 255), anchor="mm")
        draw.text((ex + 36, 398), preco, font=font_price, fill=(180, 20, 20, 255), anchor="mm")
        # Mini código de barras
        for bx in range(ex + 10, ex + 62, 3):
            if (bx % 2 == 0):
                draw.line([(bx, 409), (bx, 418)], fill=(0, 0, 0, 255), width=1)

    # Rodapé frontal da gôndola (460..512)
    draw.rectangle([256, 460, 512, 512], fill=(45, 48, 52, 255))

    return img


def gerar_todas_as_texturas():
    """Gera todas as texturas em seus diretórios canônicos."""
    print("[*] Gerando Coleção de Texturas PBR Diffuse em Alta Definição (512x512)...")

    # 1. Wooden Crate
    crate = criar_textura_madeira_crate()
    crate.save(MOVEIS_TEX / "wooden_crate_3d_diffuse.png")
    print(f"  ✓ {MOVEIS_TEX / 'wooden_crate_3d_diffuse.png'}")

    # 2. Kitchen Stove
    stove = criar_textura_fogao_stove()
    stove.save(ELETRO_TEX / "kitchen_stove_3d_diffuse.png")
    print(f"  ✓ {ELETRO_TEX / 'kitchen_stove_3d_diffuse.png'}")

    # 3. Kitchen Fridge
    fridge = criar_textura_geladeira_fridge()
    fridge.save(ELETRO_TEX / "kitchen_fridge_3d_diffuse.png")
    fridge.save(ELETRO_TEX / "refrigerator_3d_diffuse.png")
    print(f"  ✓ {ELETRO_TEX / 'kitchen_fridge_3d_diffuse.png'} (e réplica refrigerator)")

    # 4. Microwave Oven
    micro = criar_textura_microondas()
    micro.save(ELETRO_TEX / "microwave_oven_3d_diffuse.png")
    print(f"  ✓ {ELETRO_TEX / 'microwave_oven_3d_diffuse.png'}")

    # 5. Medical Box
    med = criar_textura_maleta_medica()
    med.save(LOOT_TEX / "medical_box_3d_diffuse.png")
    med.save(LOOT_TEX / "medical_firstaid_kit_3d_diffuse.png")
    print(f"  ✓ {LOOT_TEX / 'medical_box_3d_diffuse.png'} (e réplica firstaid)")

    # 6. Shotgun Ammo Box
    ammo = criar_textura_caixa_municao()
    ammo.save(LOOT_TEX / "shotgun_ammo_box_3d_diffuse.png")
    ammo.save(LOOT_TEX / "military_ammo_can_3d_diffuse.png")
    print(f"  ✓ {LOOT_TEX / 'shotgun_ammo_box_3d_diffuse.png'} (e réplica ammo can)")

    # 7. Counter Sink
    sink = criar_textura_balcao_pia()
    sink.save(MOVEIS_TEX / "counter_sink_3d_diffuse.png")
    sink.save(MOVEIS_TEX / "counter_sink_diffuse.png")
    print(f"  ✓ {MOVEIS_TEX / 'counter_sink_3d_diffuse.png'}")

    # 8. Store Shelves (NOVO)
    shelves = criar_textura_gondola_mercado()
    shelves.save(MOVEIS_TEX / "store_shelves_3d_diffuse.png")
    print(f"  ✓ {MOVEIS_TEX / 'store_shelves_3d_diffuse.png'}")


def criar_modelo_store_shelves_3d():
    """3. Modelar store_shelves_3d.obj e store_shelves_3d.mtl
    - Largura: 1.0m (X: -0.50 a +0.50)
    - Altura: 1.4m (Y: 0.00 a 1.40)
    - Profundidade: 0.55m (Z: -0.275 a +0.275)
    - 3 Níveis de prateleiras horizontais com abas de contenção (fitas de preço)
    - Colunas de sustentação e painel traseiro perfurado
    """
    obj_path = MOVEIS_DIR / "store_shelves_3d.obj"
    mtl_path = MOVEIS_DIR / "store_shelves_3d.mtl"

    mtl_content = """# Material Template Library - Store Shelves 3D
newmtl Material
Ka 1.000 1.000 1.000
Kd 1.000 1.000 1.000
Ks 0.200 0.200 0.200
Ns 40.0
d 1.0
illum 2
map_Kd textures/store_shelves_3d_diffuse.png
"""
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write(mtl_content)

    # Geometria sólida detalhada da gôndola
    # Coordenadas:
    # X: -0.50 a +0.50
    # Y: 0.00 a 1.40
    # Z: -0.275 (fundo) a +0.275 (frente)
    obj_content = """# Model: store_shelves_3d (Gôndola de Supermercado B42)
mtllib store_shelves_3d.mtl
o store_shelves_3d

# Vértices Geométricos (v)
# Base e Rodapé frontal (Y: 0.00 a 0.12)
v -0.5000 0.0000 -0.2750
v  0.5000 0.0000 -0.2750
v  0.5000 1.4000 -0.2750
v -0.5000 1.4000 -0.2750

# Frente total delimitação
v -0.5000 0.0000  0.2750
v  0.5000 0.0000  0.2750
v  0.5000 0.1200  0.2750
v -0.5000 0.1200  0.2750

# Topo do Painel Traseiro
v -0.5000 1.4000 -0.2500
v  0.5000 1.4000 -0.2500

# Colunas Laterais / Uprights
v -0.5000 0.0000 -0.2500
v -0.5000 1.4000  0.2750
v  0.5000 0.0000 -0.2500
v  0.5000 1.4000  0.2750

# Nível 1: Prateleira da Base (Deck Y: 0.12)
v -0.5000 0.1200 -0.2500
v  0.5000 0.1200 -0.2500

# Nível 2: Prateleira Intermediária (Y: 0.65 a 0.70, Z: -0.25 a +0.25)
v -0.4800 0.6600 -0.2500
v  0.4800 0.6600 -0.2500
v  0.4800 0.6600  0.2500
v -0.4800 0.6600  0.2500
v -0.4800 0.7000  0.2500
v  0.4800 0.7000  0.2500

# Nível 3: Prateleira Superior (Y: 1.05 a 1.10, Z: -0.25 a +0.25)
v -0.4800 1.0600 -0.2500
v  0.4800 1.0600 -0.2500
v  0.4800 1.0600  0.2500
v -0.4800 1.0600  0.2500
v -0.4800 1.1000  0.2500
v  0.4800 1.1000  0.2500

# Normais (vn)
vn  0.0  0.0 -1.0
vn  0.0  0.0  1.0
vn -1.0  0.0  0.0
vn  1.0  0.0  0.0
vn  0.0  1.0  0.0
vn  0.0 -1.0  0.0

# Coordenadas de Textura UV (vt)
# vt 1..4: Painel Traseiro / Pegboard (Atlas X: 0.05..0.45, Y: 0.0..1.0)
vt 0.05 0.00
vt 0.45 0.00
vt 0.45 1.00
vt 0.05 1.00

# vt 5..8: Bandejas Horizontais / Prateleiras (Atlas X: 0.52..0.98, Y: 0.52..0.98)
vt 0.52 0.52
vt 0.98 0.52
vt 0.98 0.98
vt 0.52 0.98

# vt 9..12: Fita de Preço Azul (Atlas X: 0.52..0.98, Y: 0.35..0.48)
vt 0.52 0.35
vt 0.98 0.35
vt 0.98 0.48
vt 0.52 0.48

# vt 13..16: Fita de Preço Vermelha (Atlas X: 0.52..0.98, Y: 0.15..0.28)
vt 0.52 0.15
vt 0.98 0.15
vt 0.98 0.28
vt 0.52 0.28

# vt 17..20: Colunas de Encaixe Gondola Lateral (Atlas X: 0.00..0.08, Y: 0.0..1.0)
vt 0.00 0.00
vt 0.08 0.00
vt 0.08 1.00
vt 0.00 1.00

s 1
usemtl Material

# 1. Painel Traseiro (fundo -Z)
f 1/1/1 2/2/1 3/3/1 4/4/1

# 2. Painel Traseiro Interno (frente +Z interno)
f 15/1/2 16/2/2 10/3/2 9/4/2

# 3. Rodapé frontal da base (Z = +0.275, Y: 0.00 a 0.12)
f 5/13/2 6/14/2 7/15/2 8/16/2

# 4. Bandeja da Base Horizontal (Y = 0.12)
f 8/5/5 7/6/5 16/7/5 15/8/5

# 5. Coluna Lateral Esquerda (-X)
f 1/17/3 5/18/3 12/19/3 4/20/3

# 6. Coluna Lateral Direita (+X)
f 6/17/4 2/18/4 3/19/4 14/20/4

# 7. Prateleira Intermediária (Nível 2) - Deck Superior
f 20/5/5 19/6/5 18/7/5 17/8/5

# 8. Prateleira Intermediária - Borda Frontal com Fita de Preços Azul
f 20/9/2 19/10/2 22/11/2 21/12/2

# 9. Prateleira Superior (Nível 3) - Deck Superior
f 26/5/5 25/6/5 24/7/5 23/8/5

# 10. Prateleira Superior - Borda Frontal com Fita de Preços Vermelha
f 26/13/2 25/14/2 28/15/2 27/16/2

# 11. Topo da Gôndola (+Y)
f 4/5/5 3/6/5 10/7/5 9/8/5

# 12. Fundo da base (-Y)
f 1/1/6 2/2/6 6/3/6 5/4/6
"""
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(obj_content)

    print(f"  ✓ Modelo gerado: {obj_path}")
    print(f"  ✓ MTL gerado: {mtl_path}")


def otimizar_uvs_modelos_existentes():
    """Otimiza as coordenadas UV dos modelos de caixa para casarem com as áreas dos atlas diffuse."""
    print("[*] Ajustando mapeamento UV inteligente para fogão, geladeira, pia e micro-ondas...")

    # 1. KITCHEN STOVE (Fogão)
    stove_obj = ELETRO_DIR / "kitchen_stove_3d.obj"
    stove_mtl = ELETRO_DIR / "kitchen_stove_3d.mtl"
    with open(stove_mtl, "w", encoding="utf-8") as f:
        f.write("""newmtl Material
Ka 1.0 1.0 1.0
Kd 1.0 1.0 1.0
Ks 0.2 0.2 0.2
d 1.0
illum 2
map_Kd textures/kitchen_stove_3d_diffuse.png
""")
    # OBJ com UVs específicas para Frontal (forno), Topo (4 bocas) e Laterais (esmalte branco)
    stove_content = """# Model: kitchen_stove_3d
mtllib kitchen_stove_3d.mtl
o kitchen_stove_3d
v -0.3750 0.0000 -0.3750
v 0.3750 0.0000 -0.3750
v 0.3750 0.9000 -0.3750
v -0.3750 0.9000 -0.3750
v -0.3750 0.0000 0.3750
v 0.3750 0.0000 0.3750
v 0.3750 0.9000 0.3750
v -0.3750 0.9000 0.3750
vn 0.0 0.0 -1.0
vn 0.0 0.0 1.0
vn -1.0 0.0 0.0
vn 1.0 0.0 0.0
vn 0.0 1.0 0.0
vn 0.0 -1.0 0.0
# Frontal (Porta do Forno)
vt 0.00 0.00
vt 0.50 0.00
vt 0.50 1.00
vt 0.00 1.00
# Topo (4 Queimadores circulares)
vt 0.50 0.50
vt 1.00 0.50
vt 1.00 1.00
vt 0.50 1.00
# Laterais / Traseira (Esmalte branco)
vt 0.50 0.00
vt 1.00 0.00
vt 1.00 0.50
vt 0.50 0.50
s 1
usemtl Material
f 5/1/2 6/2/2 7/3/2 8/4/2
f 2/9/1 1/10/1 4/11/1 3/12/1
f 8/5/5 7/6/5 3/7/5 4/8/5
f 1/9/6 2/10/6 6/11/6 5/12/6
f 1/9/3 5/10/3 8/11/3 4/12/3
f 6/9/4 2/10/4 3/11/4 7/12/4
"""
    with open(stove_obj, "w", encoding="utf-8") as f:
        f.write(stove_content)
    print("  ✓ kitchen_stove_3d UVs otimizadas")

    # 2. KITCHEN FRIDGE (Geladeira)
    fridge_obj = ELETRO_DIR / "kitchen_fridge_3d.obj"
    fridge_mtl = ELETRO_DIR / "kitchen_fridge_3d.mtl"
    with open(fridge_mtl, "w", encoding="utf-8") as f:
        f.write("""newmtl Material
Ka 1.0 1.0 1.0
Kd 1.0 1.0 1.0
Ks 0.2 0.2 0.2
d 1.0
illum 2
map_Kd textures/kitchen_fridge_3d_diffuse.png
""")
    fridge_content = """# Model: kitchen_fridge_3d
mtllib kitchen_fridge_3d.mtl
o kitchen_fridge_3d
v -0.3750 0.0000 -0.3750
v 0.3750 0.0000 -0.3750
v 0.3750 1.8000 -0.3750
v -0.3750 1.8000 -0.3750
v -0.3750 0.0000 0.3750
v 0.3750 0.0000 0.3750
v 0.3750 1.8000 0.3750
v -0.3750 1.8000 0.3750
vn 0.0 0.0 -1.0
vn 0.0 0.0 1.0
vn -1.0 0.0 0.0
vn 1.0 0.0 0.0
vn 0.0 1.0 0.0
vn 0.0 -1.0 0.0
# Frontal (Portas Duplas e Puxadores)
vt 0.00 0.00
vt 0.50 0.00
vt 0.50 1.00
vt 0.00 1.00
# Laterais / Topo (Aço escovado / esmalte)
vt 0.50 0.00
vt 1.00 0.00
vt 1.00 1.00
vt 0.50 1.00
s 1
usemtl Material
f 5/1/2 6/2/2 7/3/2 8/4/2
f 2/5/1 1/6/1 4/7/1 3/8/1
f 8/5/5 7/6/5 3/7/5 4/8/5
f 1/5/6 2/6/6 6/7/6 5/8/6
f 1/5/3 5/6/3 8/7/3 4/8/3
f 6/5/4 2/6/4 3/7/4 7/8/4
"""
    with open(fridge_obj, "w", encoding="utf-8") as f:
        f.write(fridge_content)
    # Também atualiza refrigerator_3d
    shutil.copyfile(fridge_obj, ELETRO_DIR / "refrigerator_3d.obj")
    shutil.copyfile(fridge_mtl, ELETRO_DIR / "refrigerator_3d.mtl")
    print("  ✓ kitchen_fridge_3d e refrigerator_3d UVs otimizadas")

    # 3. COUNTER SINK (Balcão com pia)
    sink_obj = MOVEIS_DIR / "counter_sink_3d.obj"
    sink_mtl = MOVEIS_DIR / "counter_sink_3d.mtl"
    with open(sink_mtl, "w", encoding="utf-8") as f:
        f.write("""newmtl Material
Ka 1.0 1.0 1.0
Kd 1.0 1.0 1.0
Ks 0.2 0.2 0.2
d 1.0
illum 2
map_Kd textures/counter_sink_3d_diffuse.png
""")
    sink_content = """# Model: counter_sink_3d
mtllib counter_sink_3d.mtl
o counter_sink_3d
v -0.4000 0.0000 -0.3250
v 0.4000 0.0000 -0.3250
v 0.4000 0.8500 -0.3250
v -0.4000 0.8500 -0.3250
v -0.4000 0.0000 0.3250
v 0.4000 0.0000 0.3250
v 0.4000 0.8500 0.3250
v -0.4000 0.8500 0.3250
vn 0.0 0.0 -1.0
vn 0.0 0.0 1.0
vn -1.0 0.0 0.0
vn 1.0 0.0 0.0
vn 0.0 1.0 0.0
vn 0.0 -1.0 0.0
# Frontal (Portas de madeira do armário)
vt 0.00 0.00
vt 0.50 0.00
vt 0.50 1.00
vt 0.00 1.00
# Topo (Cuba de Pia Inox com torneira e ralo)
vt 0.50 0.50
vt 1.00 0.50
vt 1.00 1.00
vt 0.50 1.00
# Laterais (Madeira)
vt 0.50 0.00
vt 1.00 0.00
vt 1.00 0.50
vt 0.50 0.50
s 1
usemtl Material
f 5/1/2 6/2/2 7/3/2 8/4/2
f 2/9/1 1/10/1 4/11/1 3/12/1
f 8/5/5 7/6/5 3/7/5 4/8/5
f 1/9/6 2/10/6 6/11/6 5/12/6
f 1/9/3 5/10/3 8/11/3 4/12/3
f 6/9/4 2/10/4 3/11/4 7/12/4
"""
    with open(sink_obj, "w", encoding="utf-8") as f:
        f.write(sink_content)
    print("  ✓ counter_sink_3d UVs otimizadas")

    # 4. MICROWAVE OVEN (Micro-ondas)
    micro_obj = ELETRO_DIR / "microwave_oven_3d.obj"
    micro_mtl = ELETRO_DIR / "microwave_oven_3d.mtl"
    with open(micro_mtl, "w", encoding="utf-8") as f:
        f.write("""newmtl Material
Ka 1.0 1.0 1.0
Kd 1.0 1.0 1.0
Ks 0.2 0.2 0.2
d 1.0
illum 2
map_Kd textures/microwave_oven_3d_diffuse.png
""")
    micro_content = """# Model: microwave_oven_3d
mtllib microwave_oven_3d.mtl
o microwave_oven_3d
v -0.2750 0.0000 -0.2000
v 0.2750 0.0000 -0.2000
v 0.2750 0.3500 -0.2000
v -0.2750 0.3500 -0.2000
v -0.2750 0.0000 0.2000
v 0.2750 0.0000 0.2000
v 0.2750 0.3500 0.2000
v -0.2750 0.3500 0.2000
vn 0.0 0.0 -1.0
vn 0.0 0.0 1.0
vn -1.0 0.0 0.0
vn 1.0 0.0 0.0
vn 0.0 1.0 0.0
vn 0.0 -1.0 0.0
# Frontal (Porta de vidro fumê + Painel digital)
vt 0.00 0.50
vt 1.00 0.50
vt 1.00 1.00
vt 0.00 1.00
# Topo do chassi escuro
vt 0.00 0.00
vt 0.50 0.00
vt 0.50 0.50
vt 0.00 0.50
# Laterais com aletas de ventilação
vt 0.50 0.00
vt 1.00 0.00
vt 1.00 0.50
vt 0.50 0.50
s 1
usemtl Material
f 5/1/2 6/2/2 7/3/2 8/4/2
f 2/5/1 1/6/1 4/7/1 3/8/1
f 8/5/5 7/6/5 3/7/5 4/8/5
f 1/5/6 2/6/6 6/7/6 5/8/6
f 1/9/3 5/10/3 8/11/3 4/12/3
f 6/9/4 2/10/4 3/11/4 7/12/4
"""
    with open(micro_obj, "w", encoding="utf-8") as f:
        f.write(micro_content)
    print("  ✓ microwave_oven_3d UVs otimizadas")

    # 4. Atualiza MTLs restantes para apontar para textures/<name>_diffuse.png
    mtls_to_fix = [
        (LOOT_DIR / "medical_box_3d.mtl", "textures/medical_box_3d_diffuse.png"),
        (LOOT_DIR / "medical_firstaid_kit_3d.mtl", "textures/medical_firstaid_kit_3d_diffuse.png"),
        (LOOT_DIR / "shotgun_ammo_box_3d.mtl", "textures/shotgun_ammo_box_3d_diffuse.png"),
        (LOOT_DIR / "military_ammo_can_3d.mtl", "textures/military_ammo_can_3d_diffuse.png"),
        (ELETRO_DIR / "microwave_oven_3d.mtl", "textures/microwave_oven_3d_diffuse.png"),
        (MOVEIS_DIR / "wooden_crate_3d.mtl", "textures/wooden_crate_3d_diffuse.png")
    ]
    for mtl_p, tex_rel in mtls_to_fix:
        if mtl_p.exists():
            with open(mtl_p, "w", encoding="utf-8") as f:
                f.write(f"""newmtl Material
Ka 1.0 1.0 1.0
Kd 1.0 1.0 1.0
Ks 0.2 0.2 0.2
d 1.0
illum 2
map_Kd {tex_rel}
""")
    print("  ✓ Arquivos MTL canônicos alinhados.")


def atualizar_pack_manifest():
    """Registra store_shelves_3d no pack.manifest."""
    manifest_path = READY_DIR / "pack.manifest"
    content = manifest_path.read_text(encoding="utf-8")

    if "store_shelves_3d" not in content:
        adicao = """
# Gôndola de Mercado (Moveis-e-Caixas)
model.store_shelves_3d = Moveis-e-Caixas/store_shelves_3d.obj
bind.furniture_shelving_01_0 = store_shelves_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_shelving_01_1 = store_shelves_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_shelving_01_2 = store_shelves_3d 0.0 0.00 0.00 0.00 1.00
"""
        manifest_path.write_text(content + adicao, encoding="utf-8")
        print(f"  ✓ store_shelves_3d registrado em {manifest_path}")
    else:
        print(f"  ✓ store_shelves_3d já estava em {manifest_path}")


def main():
    gerar_todas_as_texturas()
    criar_modelo_store_shelves_3d()
    otimizar_uvs_modelos_existentes()
    atualizar_pack_manifest()
    print("\n[+] Geração de Texturas PBR e Modelagem 3D concluída com êxito!")


if __name__ == "__main__":
    main()
