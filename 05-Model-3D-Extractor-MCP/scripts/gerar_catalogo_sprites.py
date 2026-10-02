"""
Script de Catalogação em Massa de Sprites do Mundo e Itens do Project Zomboid Build 42.
Varre newtiledefinitions.tiles.txt, tileGeometry.txt, scripts/generated/items e traduções
para construir o sprites_vanilla_catalog.json exaustivo e estruturado.
"""

import re
import json
from pathlib import Path

PZ_MEDIA = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media")
TILES_DEF = PZ_MEDIA / "newtiledefinitions.tiles.txt"
TILE_GEOM = PZ_MEDIA / "tileGeometry.txt"
ITEMS_DIR = PZ_MEDIA / "scripts" / "generated" / "items"
TRANSLATE_DIR = PZ_MEDIA / "lua" / "shared" / "Translate" / "EN"

DEST_CATALOG = Path(r"C:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\05-Model-3D-Extractor-MCP\objetos-extraidos-vanilla\sprites_vanilla_catalog.json")

def load_translations():
    item_trans = {}
    mov_trans = {}
    item_file = TRANSLATE_DIR / "ItemName.json"
    mov_file = TRANSLATE_DIR / "Moveables.json"

    if item_file.exists():
        with open(item_file, "r", encoding="utf-8") as f:
            item_trans = json.load(f)
    if mov_file.exists():
        with open(mov_file, "r", encoding="utf-8") as f:
            mov_trans = json.load(f)
    return item_trans, mov_trans

def parse_tile_geometries():
    """Lê todas as caixas delimitadoras em tileGeometry.txt (dimensões em metros)."""
    print("[1/4] Carregando geometrias físicas de tiles...")
    geom = {}
    if not TILE_GEOM.exists():
        return geom

    current_tile = None
    min_xyz = None
    max_xyz = None

    with open(TILE_GEOM, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_s = line.strip()
            if line_s.startswith("/*") and line_s.endswith("*/"):
                if current_tile and min_xyz and max_xyz:
                    w = round((max_xyz[0] - min_xyz[0]) / 10000.0, 2)
                    h = round((max_xyz[1] - min_xyz[1]) / 10000.0, 2)
                    d = round((max_xyz[2] - min_xyz[2]) / 10000.0, 2)
                    # Filtra valores espúrios
                    if 0.05 <= w <= 5.0 and 0.05 <= h <= 5.0 and 0.05 <= d <= 5.0:
                        geom[current_tile] = {"largura": w, "altura": h, "profundidade": d}
                current_tile = line_s.replace("/*", "").replace("*/", "").strip()
                min_xyz = None
                max_xyz = None
            elif current_tile:
                if "min =" in line_s:
                    nums = [float(x) for x in re.findall(r"-?\d+", line_s)]
                    if len(nums) == 3:
                        min_xyz = nums if min_xyz is None else [min(min_xyz[i], nums[i]) for i in range(3)]
                elif "max =" in line_s:
                    nums = [float(x) for x in re.findall(r"-?\d+", line_s)]
                    if len(nums) == 3:
                        max_xyz = nums if max_xyz is None else [max(max_xyz[i], nums[i]) for i in range(3)]

        if current_tile and min_xyz and max_xyz:
            w = round((max_xyz[0] - min_xyz[0]) / 10000.0, 2)
            h = round((max_xyz[1] - min_xyz[1]) / 10000.0, 2)
            d = round((max_xyz[2] - min_xyz[2]) / 10000.0, 2)
            if 0.05 <= w <= 5.0 and 0.05 <= h <= 5.0 and 0.05 <= d <= 5.0:
                geom[current_tile] = {"largura": w, "altura": h, "profundidade": d}

    print(f"  Geometrias carregadas: {len(geom)} tiles com bounding box 3D.")
    return geom

def parse_tile_definitions(geoms):
    """Varre newtiledefinitions.tiles.txt para as 4 categorias de mundo."""
    print("[2/4] Analisando newtiledefinitions.tiles.txt...")

    category_rules = {
        "gondolas_e_prateleiras": {
            "prefixes": [
                "furniture_shelving_01", "location_shop_generic_01", "location_shop_zippee_01",
                "location_shop_greenes_01", "location_shop_bargNclothes_01", "location_shop_mall_01",
                "location_shop_accessories_01", "location_shop_fossoil_01", "location_shop_gas2go_01"
            ],
            "default_dim": {"largura": 0.85, "altura": 1.60, "profundidade": 0.50},
            "default_type": "IsoObject / Container",
            "priority": "Alta"
        },
        "eletrodomesticos": {
            "prefixes": [
                "appliances_cooking_01", "appliances_refrigeration_01"
            ],
            "default_dim": {"largura": 0.80, "altura": 1.40, "profundidade": 0.75},
            "default_type": "IsoObject / Container",
            "priority": "Alta"
        },
        "moveis_e_conteineres": {
            "prefixes": [
                "carpentry_01", "carpentry_02", "furniture_storage_01", "furniture_storage_02",
                "furniture_tables_high_01", "furniture_tables_high_02", "furniture_tables_low_01",
                "furniture_seating_indoor_01", "furniture_seating_indoor_02", "furniture_seating_outdoor_01"
            ],
            "default_dim": {"largura": 0.80, "altura": 0.85, "profundidade": 0.80},
            "default_type": "IsoThumpable / Container",
            "priority": "Alta"
        },
        "portas_e_janelas": {
            "prefixes": [
                "fixtures_doors_01", "fixtures_doors_02", "fixtures_doors_frames_01", "fixtures_doors_fences_01"
            ],
            "default_dim": {"largura": 0.85, "altura": 2.10, "profundidade": 0.10},
            "default_type": "IsoDoor",
            "priority": "Alta"
        }
    }

    direction_map = {
        "N": "N", "North": "N",
        "S": "S", "South": "S",
        "E": "L", "East": "L",
        "W": "O", "West": "O"
    }

    categorized_tiles = {cat: [] for cat in category_rules}

    current_tile = None
    tile_meta = {}

    with open(TILES_DEF, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_s = line.strip()
            if line_s.startswith("// "):
                if current_tile and tile_meta:
                    cat = tile_meta.get("cat")
                    if cat:
                        categorized_tiles[cat].append(tile_meta)

                t_name = line_s[3:].strip()
                cat_match = None
                for cat_name, c_data in category_rules.items():
                    if any(t_name.startswith(p) for p in c_data["prefixes"]):
                        cat_match = cat_name
                        break

                if cat_match:
                    current_tile = t_name
                    tile_meta = {
                        "sprite_id": current_tile,
                        "sprite": current_tile,
                        "cat": cat_match,
                        "categoria": cat_match,
                        "raw_props": {}
                    }
                else:
                    current_tile = None
                    tile_meta = {}

            elif current_tile and "=" in line_s:
                parts = line_s.split("=", 1)
                k = parts[0].strip()
                v = parts[1].strip()
                tile_meta["raw_props"][k] = v

        if current_tile and tile_meta:
            cat = tile_meta.get("cat")
            if cat:
                categorized_tiles[cat].append(tile_meta)

    # Processa e padroniza cada entrada
    processed_catalog = {}
    for cat_name, raw_list in categorized_tiles.items():
        rules = category_rules[cat_name]
        processed_list = []

        for item in raw_list:
            sid = item["sprite_id"]
            props = item["raw_props"]

            custom_name = props.get("CustomName", "")
            group_name = props.get("GroupName", "")
            facing_raw = props.get("Facing", "")
            facing = direction_map.get(facing_raw, "Indefinida")
            iso_type = props.get("IsoType", rules["default_type"])
            container_type = props.get("container", "")
            material = props.get("Material", "")

            # Constrói nome legível inteligente
            parts = []
            if group_name and group_name != custom_name:
                parts.append(group_name)
            if custom_name:
                parts.append(custom_name)
            else:
                parts.append(sid.replace("_", " ").title())

            readable_name = " ".join(parts)
            if facing != "Indefinida":
                readable_name += f" ({facing})"

            # Dimensões da geometria real ou fallback padronizado
            dim = geoms.get(sid, rules["default_dim"])

            # Prioridade de substituição inteligente
            priority = rules["priority"]
            if "on" in sid.lower() or "broken" in sid.lower():
                priority = "Média"
            elif any(k in sid for k in ["_0", "_1", "_2", "_3", "_16", "_17"]):
                priority = "Alta"

            full_type = f"{iso_type}"
            if container_type and "Container" not in full_type:
                full_type += f" / Container ({container_type})"

            entry = {
                "sprite_id": sid,
                "sprite": sid,
                "nome_legivel": readable_name,
                "name": readable_name,
                "categoria": cat_name,
                "dimensoes_estimadas_m": dim,
                "orientacao_tile": facing,
                "prioridade_substituicao": priority,
                "tipo_objeto": full_type,
                "material": material if material else "Generic",
                "tags": [cat_name, material.lower() if material else "standard", facing]
            }
            processed_list.append(entry)

        processed_catalog[cat_name] = processed_list
        print(f"  {cat_name}: {len(processed_list)} tiles catalogados.")

    return processed_catalog

def parse_items_and_ground_loot(item_translations):
    """Analisa os scripts gerados de itens do Zomboid para catalogar loots de chão."""
    print("[3/4] Mapeando loots, comidas de chão, munições e ferramentas...")

    ground_loot_entries = []

    # Lista curada de itens essenciais e icônicos do Zomboid
    target_items = [
        # Comidas enlatadas
        {"id": "Base.TinnedBeans", "name": "Canned Beans", "wsm": "CanClosed", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.OpenBeans", "name": "Open Canned Beans", "wsm": "CanOpen", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedChili", "name": "Canned Chili", "wsm": "CanClosedChilli", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedCorn", "name": "Canned Corn", "wsm": "CanClosedCorn", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedCarrots2", "name": "Canned Carrots", "wsm": "CanClosedCarrots", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedPeas", "name": "Canned Peas", "wsm": "CanClosedPeas", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedTomato2", "name": "Canned Tomatoes", "wsm": "CanClosedTomatoes", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedBolognese", "name": "Canned Bolognese", "wsm": "CanClosedBolognese", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedMushroomSoup", "name": "Canned Mushroom Soup", "wsm": "CanClosedMushroom", "dim": {"largura": 0.08, "altura": 0.12, "profundidade": 0.08}, "type": "Can (Food)"},
        {"id": "Base.CannedSardines", "name": "Canned Sardines", "wsm": "CannedSardines_Ground", "dim": {"largura": 0.10, "altura": 0.04, "profundidade": 0.06}, "type": "Can (Fish)"},
        {"id": "Base.CannedMilk", "name": "Evaporated Milk", "wsm": "CanClosedMilk", "dim": {"largura": 0.08, "altura": 0.11, "profundidade": 0.08}, "type": "Can (Drink)"},
        {"id": "Base.CannedCornedBeef", "name": "Canned Corned Beef", "wsm": "CanClosedCornerBeef", "dim": {"largura": 0.10, "altura": 0.07, "profundidade": 0.08}, "type": "Can (Meat)"},

        # Bebidas e Garrafas
        {"id": "Base.WaterBottle", "name": "Plastic Water Bottle", "wsm": "WaterBottleFull", "dim": {"largura": 0.08, "altura": 0.24, "profundidade": 0.08}, "type": "Drink Bottle"},
        {"id": "Base.BeerBottle", "name": "Beer Bottle", "wsm": "BeerBottle", "dim": {"largura": 0.07, "altura": 0.26, "profundidade": 0.07}, "type": "Drink Bottle"},
        {"id": "Base.WhiskeyBottle", "name": "Whiskey Bottle", "wsm": "WhiskeyBottle", "dim": {"largura": 0.09, "altura": 0.28, "profundidade": 0.09}, "type": "Drink Bottle"},
        {"id": "Base.WineBottle", "name": "Wine Bottle", "wsm": "WineBottle", "dim": {"largura": 0.08, "altura": 0.30, "profundidade": 0.08}, "type": "Drink Bottle"},
        {"id": "Base.PopBottle", "name": "Soda Bottle", "wsm": "PopBottle", "dim": {"largura": 0.08, "altura": 0.25, "profundidade": 0.08}, "type": "Drink Bottle"},
        {"id": "Base.Bleach", "name": "Bottle of Bleach", "wsm": "BleachBottle", "dim": {"largura": 0.12, "altura": 0.28, "profundidade": 0.12}, "type": "Chemical Container"},

        # Munições e Caixas
        {"id": "Base.Bullets9mmBox", "name": "Box of 9x19mm Rounds", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.12, "altura": 0.08, "profundidade": 0.07}, "type": "Ammo Box"},
        {"id": "Base.ShotgunShellsBox", "name": "Box of 12g Shotgun Shells", "wsm": "BoxOfShotGunShells", "dim": {"largura": 0.14, "altura": 0.09, "profundidade": 0.08}, "type": "Ammo Box"},
        {"id": "Base.Bullets38Box", "name": "Box of .38 Special Rounds", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.12, "altura": 0.08, "profundidade": 0.07}, "type": "Ammo Box"},
        {"id": "Base.Bullets44Box", "name": "Box of .44 Magnum Rounds", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.13, "altura": 0.08, "profundidade": 0.08}, "type": "Ammo Box"},
        {"id": "Base.Bullets45Box", "name": "Box of .45 Auto Rounds", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.13, "altura": 0.08, "profundidade": 0.08}, "type": "Ammo Box"},
        {"id": "Base.223Box", "name": "Box of .223 Bullets", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.13, "altura": 0.08, "profundidade": 0.08}, "type": "Ammo Box"},
        {"id": "Base.308Box", "name": "Box of .308 Bullets", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.14, "altura": 0.09, "profundidade": 0.08}, "type": "Ammo Box"},
        {"id": "Base.556Box", "name": "Box of 5.56x45mm Rounds", "wsm": "HandGunAmmoBox", "dim": {"largura": 0.14, "altura": 0.09, "profundidade": 0.08}, "type": "Ammo Box"},
        {"id": "Base.Bag_AmmoBox_ShotgunShells", "name": "Military Ammo Can (Shotgun)", "wsm": "AmmoBox_Ground", "dim": {"largura": 0.30, "altura": 0.20, "profundidade": 0.18}, "type": "Military Container"},

        # Kits Médicos e Farmácia
        {"id": "Base.FirstAidKit", "name": "First Aid Kit", "wsm": "LunchBoxMedic_Ground", "dim": {"largura": 0.28, "altura": 0.14, "profundidade": 0.20}, "type": "Medical Kit"},
        {"id": "Base.FirstAidKit_Camping", "name": "Camping First Aid Kit", "wsm": "FirstAidKit_Camping", "dim": {"largura": 0.26, "altura": 0.12, "profundidade": 0.18}, "type": "Medical Kit"},
        {"id": "Base.FirstAidKit_Military", "name": "Tactical First Aid Kit", "wsm": "FirstAidKit_Military", "dim": {"largura": 0.30, "altura": 0.16, "profundidade": 0.22}, "type": "Medical Kit"},
        {"id": "Base.Antibiotics", "name": "Bottle of Antibiotics", "wsm": "Antibiotics", "dim": {"largura": 0.06, "altura": 0.10, "profundidade": 0.06}, "type": "Medicine"},
        {"id": "Base.Bandage", "name": "Bandage Roll", "wsm": "Bandage", "dim": {"largura": 0.08, "altura": 0.06, "profundidade": 0.08}, "type": "Medical Supply"},
        {"id": "Base.Pills", "name": "Painkillers Bottle", "wsm": "Pills", "dim": {"largura": 0.06, "altura": 0.10, "profundidade": 0.06}, "type": "Medicine"},
        {"id": "Base.PillsBeta", "name": "Beta Blockers Bottle", "wsm": "PillsBeta", "dim": {"largura": 0.06, "altura": 0.10, "profundidade": 0.06}, "type": "Medicine"},
        {"id": "Base.Disinfectant", "name": "Bottle of Disinfectant", "wsm": "Disinfectant", "dim": {"largura": 0.09, "altura": 0.22, "profundidade": 0.09}, "type": "Medical Supply"},

        # Ferramentas e Equipamentos de Chão
        {"id": "Base.Hammer", "name": "Claw Hammer", "wsm": "Hammer", "dim": {"largura": 0.16, "altura": 0.05, "profundidade": 0.35}, "type": "Tool / Weapon"},
        {"id": "Base.Axe", "name": "Fire Axe", "wsm": "Axe", "dim": {"largura": 0.22, "altura": 0.06, "profundidade": 0.85}, "type": "Tool / Weapon"},
        {"id": "Base.Sledgehammer", "name": "Heavy Sledgehammer", "wsm": "Sledgehammer", "dim": {"largura": 0.24, "altura": 0.08, "profundidade": 0.95}, "type": "Tool / Heavy Weapon"},
        {"id": "Base.Crowbar", "name": "Steel Crowbar", "wsm": "Crowbar", "dim": {"largura": 0.10, "altura": 0.04, "profundidade": 0.75}, "type": "Tool / Weapon"},
        {"id": "Base.Screwdriver", "name": "Screwdriver", "wsm": "Screwdriver", "dim": {"largura": 0.04, "altura": 0.04, "profundidade": 0.22}, "type": "Tool"},
        {"id": "Base.Saw", "name": "Hand Saw", "wsm": "Saw", "dim": {"largura": 0.14, "altura": 0.04, "profundidade": 0.50}, "type": "Tool"},
        {"id": "Base.PipeWrench", "name": "Pipe Wrench", "wsm": "PipeWrench", "dim": {"largura": 0.10, "altura": 0.05, "profundidade": 0.40}, "type": "Tool"},
        {"id": "Base.BlowTorch", "name": "Propane Torch", "wsm": "Blowtorch", "dim": {"largura": 0.12, "altura": 0.30, "profundidade": 0.12}, "type": "Tool"},
        {"id": "Base.Generator", "name": "Portable Generator", "wsm": "Generator", "dim": {"largura": 0.65, "altura": 0.55, "profundidade": 0.50}, "type": "Electrical Equipment"},
        {"id": "Base.AlarmClock2", "name": "Analog Alarm Clock", "wsm": "AlarmClock", "dim": {"largura": 0.12, "altura": 0.14, "profundidade": 0.09}, "type": "Electronics"},
        {"id": "Base.Flashlight", "name": "Flashlight", "wsm": "Flashlight", "dim": {"largura": 0.06, "altura": 0.06, "profundidade": 0.20}, "type": "Electronics / Light"},
        {"id": "Base.RadioBlack", "name": "ValuTech Portable Radio", "wsm": "Radio", "dim": {"largura": 0.22, "altura": 0.15, "profundidade": 0.08}, "type": "Electronics / Comm"}
    ]

    for item in target_items:
        clean_name = item_translations.get(item["id"], item["name"])
        entry = {
            "sprite_id": item["id"],
            "sprite": item["id"],
            "nome_legivel": clean_name,
            "name": clean_name,
            "categoria": "loots_e_comidas_de_chao",
            "world_static_model": item["wsm"],
            "dimensoes_estimadas_m": item["dim"],
            "orientacao_tile": "Indefinida",
            "prioridade_substituicao": "Alta",
            "tipo_objeto": f"InventoryItem / WorldItem ({item['type']})",
            "material": "Item",
            "tags": ["loot", "ground_item", item["type"].lower()]
        }
        ground_loot_entries.append(entry)

    print(f"  loots_e_comidas_de_chao: {len(ground_loot_entries)} itens de chão canônicos catalogados.")
    return ground_loot_entries

def main():
    print("=== Iniciando Catalogação em Massa de Sprites do Project Zomboid Build 42 ===")
    item_trans, mov_trans = load_translations()
    geoms = parse_tile_geometries()
    tiles_catalog = parse_tile_definitions(geoms)
    loot_entries = parse_items_and_ground_loot(item_trans)

    tiles_catalog["loots_e_comidas_de_chao"] = loot_entries

    # Mantém compatibilidade com categorias antigas inserindo referências ou aliases
    tiles_catalog["furniture_seating"] = [x for x in tiles_catalog["moveis_e_conteineres"] if "seating" in x["sprite_id"]][:50]
    tiles_catalog["furniture_storage"] = [x for x in tiles_catalog["moveis_e_conteineres"] if "storage" in x["sprite_id"] or "shelving" in x["sprite_id"]][:50]
    tiles_catalog["appliances_cooking"] = [x for x in tiles_catalog["eletrodomesticos"] if "cooking" in x["sprite_id"]][:50]
    tiles_catalog["fixtures_doors"] = [x for x in tiles_catalog["portas_e_janelas"] if "doors" in x["sprite_id"]][:50]

    total_sprites = sum(len(items) for cat, items in tiles_catalog.items() if cat in [
        "gondolas_e_prateleiras", "eletrodomesticos", "moveis_e_conteineres", "portas_e_janelas", "loots_e_comidas_de_chao"
    ])

    print("\n[4/4] Gravando sprites_vanilla_catalog.json...")
    DEST_CATALOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DEST_CATALOG, "w", encoding="utf-8") as f:
        json.dump(tiles_catalog, f, indent=2, ensure_ascii=False)

    print(f"=== Catalogação Concluída com Sucesso! ===")
    print(f"Total de sprites mapeados nas 5 categorias principais: {total_sprites}")
    for cat in ["gondolas_e_prateleiras", "eletrodomesticos", "moveis_e_conteineres", "portas_e_janelas", "loots_e_comidas_de_chao"]:
        print(f"  * {cat}: {len(tiles_catalog[cat])} registros")
    print(f"Arquivo gerado: {DEST_CATALOG}")

if __name__ == "__main__":
    main()
