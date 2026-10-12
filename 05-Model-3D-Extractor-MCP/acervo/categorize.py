"""Regras de categoria do acervo (tiles.category).

A tabela RULES é lida de cima para baixo e vale a PRIMEIRA regra que casa, então a ordem é a prioridade.
Cada regra é (categoria, tipo, padrão), com o tipo sendo:

  tileset  regex aplicada com re.match no nome do tileset (ex. 'furniture_bedding_01')
  prop     o tile tem essa propriedade (chave), com qualquer valor
  value    (chave, regex): o valor da propriedade casa com a regex (re.fullmatch, sem diferenciar maiúsculas)
  name     regex (re.fullmatch, sem diferenciar maiúsculas) sobre CustomName

Para ajustar: acrescentar ou reordenar linhas; rodar `python categorize.py` mostra a tabela de contagens
(precisa do jogo instalado) e os maiores tilesets que ainda caem em 'outros'.
"""
from __future__ import annotations

import re

CATEGORIES = [
    "moveis", "eletrodomesticos", "containers", "construcao", "portas_janelas",
    "decoracao", "vegetacao", "iluminacao", "banheiro", "cozinha", "outros",
]

# (categoria, tipo, padrão)
RULES: list[tuple[str, str, object]] = [
    # --- decoração que mora em tilesets de piso/parede/janela: precisa vir antes de construção e janelas ---
    ("decoracao", "tileset", r"overlay_|floors_overlay|floors_rugs|floor_carpet|rugs_"),
    ("decoracao", "tileset", r"fixtures_windows_(curtains|detailing)|fixtures_overlay_counters"),
    ("decoracao", "tileset", r"d_(streetcracks|wallcracks|floorleaves|generic|trash)|object_snow_overlay|brokenglass|damaged_objects"),

    # --- portas e janelas ---
    ("construcao", "tileset", r"fixtures_doors_fences"),
    ("portas_janelas", "tileset", r"fixtures_(doors|windows)_|walls_garage_door"),
    ("portas_janelas", "prop", "doorN"),
    ("portas_janelas", "prop", "doorW"),
    ("portas_janelas", "prop", "windowN"),
    ("portas_janelas", "prop", "windowW"),
    ("portas_janelas", "prop", "GarageDoor"),
    ("portas_janelas", "name", r"door|window|doorframe|windowframe|garage door"),

    # --- construção: estrutura do edifício e do terreno ---
    ("construcao", "tileset", r"walls_|floors_|floor_|roofs_|fencing_|ceilings_|ramps_|construction_|underground_|invisible_"),
    ("construcao", "tileset", r"fixtures_(stairs|railings|escalators|fireplaces)|street_(curbs|trafficlines)|blends_"),
    ("construcao", "tileset", r"e_(roof_snow|exterior|newsnow|newgrass)|industry_|electricity_pylon|radio_tower|water_tank|steamboat"),
    ("construcao", "prop", "wall"),
    ("construcao", "prop", "WallN"),
    ("construcao", "prop", "WallW"),
    ("construcao", "prop", "FloorOverlay"),
    ("construcao", "prop", "FenceTypeHigh"),
    ("construcao", "prop", "FenceTypeLow"),
    ("construcao", "prop", "RoofGroup"),
    ("construcao", "prop", "solidfloor"),
    ("construcao", "prop", "WestRoofT"),
    ("construcao", "prop", "isEave"),

    # --- vegetação e natureza ---
    ("vegetacao", "tileset", r"vegetation_|e_.*(JUMBO|_1$)|e_stumps|f_|d_plants|boulders|jumbo_|crafting_ore"),
    ("vegetacao", "prop", "tree"),
    ("vegetacao", "prop", "vegitation"),  # sic: grafia do jogo
    ("vegetacao", "prop", "Bush"),

    # --- iluminação ---
    ("iluminacao", "tileset", r"lighting_|signs_one-off_lights"),
    ("iluminacao", "prop", "lightswitch"),
    ("iluminacao", "name", r".*(lamp|light|lights|chandelier)"),

    # --- banheiro ---
    ("banheiro", "tileset", r"fixtures_bathroom_"),
    ("banheiro", "name", r"toilet|bath|shower|bathroom rug"),

    # --- eletrodomésticos (antes de containers: geladeira e fogão também têm 'container') ---
    ("eletrodomesticos", "tileset", r"appliances_"),
    ("eletrodomesticos", "value", ("container", r"fridge|stove|woodstove|microwave|dishwasher|clothing(washer|dryer|dryerbasic)|vending.*|barbecue.*")),
    ("eletrodomesticos", "prop", "IsoType"),
    ("eletrodomesticos", "name", r"fridge|freezer|oven|television|radio|walkie talkie|microwave|dishwasher|conditioner|generator|computer|phone"),

    # --- cozinha ---
    ("cozinha", "tileset", r"fixtures_(counters|sinks)_"),
    ("cozinha", "value", ("container", r"counter|overhead")),
    ("cozinha", "name", r"counter|sink|bar|hood"),

    # --- móveis de uso (assento, cama, mesa, mesa de trabalho) ---
    ("moveis", "tileset", r"furniture_(seating|bedding|tables)|desks_|seating_|office_01|recreational_01"),
    ("moveis", "prop", "bed"),
    ("moveis", "prop", "BedType"),
    ("moveis", "prop", "IsTable"),
    ("moveis", "prop", "chairN"),
    ("moveis", "prop", "chairS"),
    ("moveis", "prop", "chairE"),
    ("moveis", "prop", "chairW"),
    ("moveis", "name", r"chair|chairs|couch|bed|beds|bench|seat|seating|table|low table|desk|stool|pew|picknic table|sleeping bag|mattress|workbench"),

    # --- containers (qualquer coisa que guarda itens) ---
    ("containers", "prop", "container"),
    ("containers", "prop", "ContainerCapacity"),
    ("containers", "tileset", r"storage_|trashcontainers_|trash_walls|furniture_(storage|shelving)"),
    ("containers", "name", r"shelves|shelf|wardrobe|cabinet|drawers|locker|crate|bin|box|trash|dumpster|barrel|chest|rack|stack"),

    # --- móveis, demais ---
    ("moveis", "tileset", r"furniture_|rooftop_furniture|carpentry_|crafted_"),

    # --- decoração ---
    ("decoracao", "tileset", r".*signs|advertising_|papernotices_|street_(decoration|roadsigns)|rugs_|trash_|camping_|recreational_|animaltracks_"),
    ("decoracao", "tileset", r"location_(community_(cemetary|park)|entertainment_gallery|military_tent)|constructedobjects_"),
    ("moveis", "name", r"organ|piano|grand piano|pew|cubicle"),
    ("decoracao", "prop", "WallOverlay"),
    ("decoracao", "prop", "TileOverlay"),
    ("decoracao", "name", r"sign|poster|painting|paintings|mirror|curtain|notices|banner|flag|statue|clock|rug|carpet|whiteboard|board|menu"),
]

_compiled: list[tuple[str, str, object]] = []


def _compile() -> None:
    if _compiled:
        return
    for cat, kind, pat in RULES:
        if kind == "tileset":
            _compiled.append((cat, kind, re.compile(pat)))
        elif kind == "name":
            _compiled.append((cat, kind, re.compile(pat, re.I)))
        elif kind == "value":
            key, rx = pat  # type: ignore[misc]
            _compiled.append((cat, kind, (key, re.compile(rx, re.I))))
        else:
            _compiled.append((cat, kind, pat))


def categorize(tileset: str, props: dict[str, str]) -> str:
    """Categoria de um tile a partir do tileset e das propriedades (dict chave -> valor)."""
    _compile()
    custom = props.get("CustomName", "")
    for cat, kind, pat in _compiled:
        if kind == "tileset":
            if pat.match(tileset):  # type: ignore[union-attr]
                return cat
        elif kind == "prop":
            if pat in props:
                return cat
        elif kind == "value":
            key, rx = pat  # type: ignore[misc]
            if key in props and rx.fullmatch(props[key]):
                return cat
        elif kind == "name":
            if custom and pat.fullmatch(custom):  # type: ignore[union-attr]
                return cat
    return "outros"


if __name__ == "__main__":
    # Relatório rápido sobre o jogo instalado: contagens por categoria e maiores tilesets em 'outros'.
    import collections
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import extract_tiles

    game = sys.argv[1] if len(sys.argv) > 1 else extract_tiles.DEFAULT_GAME_DIR
    defs = extract_tiles.load_definitions(extract_tiles.media_dir(game))
    per_cat: collections.Counter = collections.Counter()
    outros: collections.Counter = collections.Counter()
    for d in defs.values():
        c = categorize(d["tileset"], d["props"])
        per_cat[c] += 1
        if c == "outros":
            outros[d["tileset"]] += 1
    for c in CATEGORIES:
        print(f"{c:18s} {per_cat[c]:6d}")
    print("\nmaiores tilesets em 'outros':")
    for ts, n in outros.most_common(20):
        print(f"  {n:5d}  {ts}")
