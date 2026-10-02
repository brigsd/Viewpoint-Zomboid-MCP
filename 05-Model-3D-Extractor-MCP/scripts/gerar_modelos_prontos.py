"""
Script de Síntese de Geometrias 3D (.obj e .mtl) e Atualização do pack.manifest.
Gera modelos métricos para gôndolas de loja, balcões, freezers, latas de comida,
garrafas de água e portas interiores.
"""

import math
from pathlib import Path

READY_DIR = Path(r"C:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\05-Model-3D-Extractor-MCP\objetos-prontos-3d")
ELETRO_DIR = READY_DIR / "Eletrodomesticos"
LOOT_DIR = READY_DIR / "Itens-de-Chao-Loot"
MOVEIS_DIR = READY_DIR / "Moveis-e-Caixas"

def generate_box_obj(model_name: str, width: float, height: float, depth: float, texture_name: str):
    """Gera um modelo de paralelepípedo com dimensões métricas, UVs e normais."""
    hw = width / 2.0
    hh = height
    hd = depth / 2.0

    obj_lines = [
        f"# Model: {model_name}",
        f"# Dimensions (m): {width:.3f} W x {height:.3f} H x {depth:.3f} D",
        f"mtllib {model_name}.mtl",
        f"o {model_name}",
        "",
        # Vértices (v x y z)
        f"v {-hw:.4f} 0.0000 {-hd:.4f}",
        f"v {hw:.4f} 0.0000 {-hd:.4f}",
        f"v {hw:.4f} {hh:.4f} {-hd:.4f}",
        f"v {-hw:.4f} {hh:.4f} {-hd:.4f}",
        f"v {-hw:.4f} 0.0000 {hd:.4f}",
        f"v {hw:.4f} 0.0000 {hd:.4f}",
        f"v {hw:.4f} {hh:.4f} {hd:.4f}",
        f"v {-hw:.4f} {hh:.4f} {hd:.4f}",
        "",
        # Normais (vn x y z)
        "vn 0.0000 0.0000 -1.0000",
        "vn 0.0000 0.0000 1.0000",
        "vn -1.0000 0.0000 0.0000",
        "vn 1.0000 0.0000 0.0000",
        "vn 0.0000 1.0000 0.0000",
        "vn 0.0000 -1.0000 0.0000",
        "",
        # UVs (vt u v)
        "vt 0.0000 0.0000",
        "vt 1.0000 0.0000",
        "vt 1.0000 1.0000",
        "vt 0.0000 1.0000",
        "",
        # Faces
        "s 1",
        "usemtl Material",
        "f 5/1/2 6/2/2 7/3/2 8/4/2", # Frente
        "f 2/1/1 1/2/1 4/3/1 3/4/1", # Traseira
        "f 8/1/5 7/2/5 3/3/5 4/4/5", # Topo
        "f 1/1/6 2/2/6 6/3/6 5/4/6", # Fundo
        "f 1/1/3 5/2/3 8/3/3 4/4/3", # Esquerda
        "f 6/1/4 2/2/4 3/3/4 7/4/4"  # Direita
    ]

    mtl_lines = [
        "newmtl Material",
        "Ka 1.0 1.0 1.0",
        "Kd 1.0 1.0 1.0",
        "Ks 0.1 0.1 0.1",
        "d 1.0",
        "illum 2",
        f"map_Kd textures/{texture_name}"
    ]

    return "\n".join(obj_lines), "\n".join(mtl_lines)

def generate_cylinder_obj(model_name: str, radius: float, height: float, segments: int, texture_name: str):
    """Gera um modelo cilíndrico (latas, garrafas)."""
    vertices = []
    normals = []
    uvs = []
    faces = []

    # Vértices da base (y=0) e do topo (y=height)
    for i in range(segments):
        angle = (2 * math.pi * i) / segments
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        vertices.append((x, 0.0, z))
        vertices.append((x, height, z))
        normals.append((math.cos(angle), 0.0, math.sin(angle)))

    # Centros de tampo
    center_bottom_idx = len(vertices) + 1
    vertices.append((0.0, 0.0, 0.0))
    center_top_idx = len(vertices) + 1
    vertices.append((0.0, height, 0.0))

    normals.append((0.0, -1.0, 0.0)) # bottom normal idx
    normals.append((0.0, 1.0, 0.0))  # top normal idx
    bottom_norm_idx = len(normals) - 1
    top_norm_idx = len(normals)

    # UVs
    for i in range(segments + 1):
        u = i / segments
        uvs.append((u, 0.0))
        uvs.append((u, 1.0))
    uvs.append((0.5, 0.5)) # center uv
    center_uv_idx = len(uvs)

    obj_lines = [
        f"# Model: {model_name}",
        f"# Dimensions (m): Radius {radius:.3f} x Height {height:.3f}",
        f"mtllib {model_name}.mtl",
        f"o {model_name}",
        ""
    ]

    for v in vertices:
        obj_lines.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}")
    obj_lines.append("")
    for n in normals:
        obj_lines.append(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}")
    obj_lines.append("")
    for uv in uvs:
        obj_lines.append(f"vt {uv[0]:.4f} {uv[1]:.4f}")
    obj_lines.append("")
    obj_lines.append("s 1")
    obj_lines.append("usemtl Material")

    # Faces laterais
    for i in range(segments):
        next_i = (i + 1) % segments
        # Vértices:
        # v1: base i -> (2*i + 1)
        # v2: top i -> (2*i + 2)
        # v3: top next -> (2*next_i + 2)
        # v4: base next -> (2*next_i + 1)
        v1 = 2 * i + 1
        v2 = 2 * i + 2
        v3 = 2 * next_i + 2
        v4 = 2 * next_i + 1
        n1 = i + 1
        n2 = next_i + 1
        # Quad lateral
        obj_lines.append(f"f {v1}/1/{n1} {v2}/2/{n1} {v3}/4/{n2} {v4}/3/{n2}")

    # Tampas (superior e inferior)
    for i in range(segments):
        next_i = (i + 1) % segments
        # Topo
        vt1 = 2 * i + 2
        vt2 = 2 * next_i + 2
        obj_lines.append(f"f {center_top_idx}/{center_uv_idx}/{top_norm_idx} {vt1}/{center_uv_idx}/{top_norm_idx} {vt2}/{center_uv_idx}/{top_norm_idx}")
        # Fundo
        vb1 = 2 * i + 1
        vb2 = 2 * next_i + 1
        obj_lines.append(f"f {center_bottom_idx}/{center_uv_idx}/{bottom_norm_idx} {vb2}/{center_uv_idx}/{bottom_norm_idx} {vb1}/{center_uv_idx}/{bottom_norm_idx}")

    mtl_lines = [
        "newmtl Material",
        "Ka 1.0 1.0 1.0",
        "Kd 1.0 1.0 1.0",
        "Ks 0.3 0.3 0.3",
        "d 1.0",
        "illum 2",
        f"map_Kd textures/{texture_name}"
    ]

    return "\n".join(obj_lines), "\n".join(mtl_lines)

def main():
    print("=== Gerando Novos Modelos 3D Prontos (.obj / .mtl) ===")

    models_to_create = [
        # 1. Gôndolas e Prateleiras (Moveis-e-Caixas)
        {
            "dir": MOVEIS_DIR,
            "name": "store_shelf_gondola_3d",
            "type": "box",
            "dim": (0.90, 1.60, 0.80),
            "tex": "store_shelf_gondola_diffuse.png"
        },
        {
            "dir": MOVEIS_DIR,
            "name": "metal_store_shelf_3d",
            "type": "box",
            "dim": (0.90, 1.85, 0.50),
            "tex": "metal_store_shelf_diffuse.png"
        },
        # 2. Balcões de Loja (Moveis-e-Caixas)
        {
            "dir": MOVEIS_DIR,
            "name": "shop_counter_wood_3d",
            "type": "box",
            "dim": (0.90, 0.90, 0.65),
            "tex": "shop_counter_wood_diffuse.png"
        },
        {
            "dir": MOVEIS_DIR,
            "name": "shop_counter_glass_3d",
            "type": "box",
            "dim": (0.90, 0.90, 0.65),
            "tex": "shop_counter_glass_diffuse.png"
        },
        # 3. Portas Interiores (Moveis-e-Caixas)
        {
            "dir": MOVEIS_DIR,
            "name": "wooden_door_interior_3d",
            "type": "box",
            "dim": (0.85, 2.10, 0.08),
            "tex": "wooden_door_interior_diffuse.png"
        },
        # 4. Freezers e Refrigeração (Eletrodomesticos)
        {
            "dir": ELETRO_DIR,
            "name": "commercial_freezer_vertical_3d",
            "type": "box",
            "dim": (0.85, 1.85, 0.75),
            "tex": "commercial_freezer_vertical_diffuse.png"
        },
        {
            "dir": ELETRO_DIR,
            "name": "ice_cooler_freezer_3d",
            "type": "box",
            "dim": (1.00, 0.90, 0.65),
            "tex": "ice_cooler_freezer_diffuse.png"
        },
        # 5. Latas de Comida & Garrafas (Itens-de-Chao-Loot)
        {
            "dir": LOOT_DIR,
            "name": "canned_food_can_3d",
            "type": "cylinder",
            "radius": 0.0425,
            "height": 0.12,
            "segments": 12,
            "tex": "canned_food_can_diffuse.png"
        },
        {
            "dir": LOOT_DIR,
            "name": "water_bottle_3d",
            "type": "cylinder",
            "radius": 0.04,
            "height": 0.24,
            "segments": 12,
            "tex": "water_bottle_diffuse.png"
        },
        {
            "dir": LOOT_DIR,
            "name": "canned_beans_3d",
            "type": "cylinder",
            "radius": 0.0425,
            "height": 0.12,
            "segments": 12,
            "tex": "canned_beans_diffuse.png"
        },
        {
            "dir": LOOT_DIR,
            "name": "canned_sardines_3d",
            "type": "box",
            "dim": (0.11, 0.04, 0.065),
            "tex": "canned_sardines_diffuse.png"
        }
    ]

    for m in models_to_create:
        target_dir = m["dir"]
        target_dir.mkdir(parents=True, exist_ok=True)
        m_name = m["name"]
        obj_file = target_dir / f"{m_name}.obj"
        mtl_file = target_dir / f"{m_name}.mtl"

        if m["type"] == "box":
            w, h, d = m["dim"]
            obj_content, mtl_content = generate_box_obj(m_name, w, h, d, m["tex"])
        else:
            obj_content, mtl_content = generate_cylinder_obj(m_name, m["radius"], m["height"], m["segments"], m["tex"])

        with open(obj_file, "w", encoding="utf-8") as f:
            f.write(obj_content)
        with open(mtl_file, "w", encoding="utf-8") as f:
            f.write(mtl_content)
        print(f"  [OK] Criado modelo: {m_name}.obj / .mtl em {target_dir.name}")

    # Atualiza pack.manifest mestre
    print("\n=== Atualizando pack.manifest com as novas amarrações ===")
    manifest_file = READY_DIR / "pack.manifest"

    # Conteúdo expandido completo do pack.manifest
    new_manifest_content = """id = zomboid-3d-essentials
name = Zomboid 3D Essentials Pack

# ====================================================================
# Viewpoint 3D Model Pack Manifest - Objetos Prontos Expandidos
# ====================================================================
# Formato:
# model.<id_modelo> = <subpasta>/<arquivo>.obj
# bind.<nome_do_sprite_2d> = <id_modelo> <graus_rotacao> <offset_x> <offset_y> <offset_z> <escala>
# ====================================================================

# --------------------------------------------------------------------
# 1. Móveis, Caixas e Carpintaria (Moveis-e-Caixas)
# --------------------------------------------------------------------
model.wooden_crate_3d = Moveis-e-Caixas/wooden_crate_3d.obj
bind.furniture_storage_01_16 = wooden_crate_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_storage_01_17 = wooden_crate_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_storage_01_18 = wooden_crate_3d 0.0 0.00 0.00 0.00 1.00

model.wooden_table_3d = Moveis-e-Caixas/wooden_table_3d.obj
bind.furniture_tables_high_01_0 = wooden_table_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_tables_high_01_1 = wooden_table_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_tables_low_01_0 = wooden_table_3d 0.0 0.00 0.00 0.00 1.00

model.office_chair_3d = Moveis-e-Caixas/office_chair_3d.obj
bind.furniture_seating_indoor_01_16 = office_chair_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_seating_indoor_01_17 = office_chair_3d 0.0 0.00 0.00 0.00 1.00

model.counter_sink_3d = Moveis-e-Caixas/counter_sink_3d.obj
bind.fixtures_bathroom_01_48 = counter_sink_3d 0.0 0.00 0.00 0.00 1.00
bind.fixtures_bathroom_01_49 = counter_sink_3d 0.0 0.00 0.00 0.00 1.00

# --------------------------------------------------------------------
# 2. Gôndolas de Loja e Prateleiras Comerciais (Moveis-e-Caixas)
# --------------------------------------------------------------------
model.store_shelf_gondola_3d = Moveis-e-Caixas/store_shelf_gondola_3d.obj
bind.furniture_shelving_01_0 = store_shelf_gondola_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_shelving_01_1 = store_shelf_gondola_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_generic_01_0 = store_shelf_gondola_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_generic_01_1 = store_shelf_gondola_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_zippee_01_0 = store_shelf_gondola_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_zippee_01_1 = store_shelf_gondola_3d 0.0 0.00 0.00 0.00 1.00

model.metal_store_shelf_3d = Moveis-e-Caixas/metal_store_shelf_3d.obj
bind.furniture_shelving_01_24 = metal_store_shelf_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_shelving_01_25 = metal_store_shelf_3d 0.0 0.00 0.00 0.00 1.00
bind.furniture_shelving_01_26 = metal_store_shelf_3d 0.0 0.00 0.00 0.00 1.00

# --------------------------------------------------------------------
# 3. Balcões de Atendimento e Vitrines de Loja (Moveis-e-Caixas)
# --------------------------------------------------------------------
model.shop_counter_wood_3d = Moveis-e-Caixas/shop_counter_wood_3d.obj
bind.location_shop_generic_01_24 = shop_counter_wood_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_generic_01_25 = shop_counter_wood_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_generic_01_26 = shop_counter_wood_3d 0.0 0.00 0.00 0.00 1.00

model.shop_counter_glass_3d = Moveis-e-Caixas/shop_counter_glass_3d.obj
bind.location_shop_generic_01_32 = shop_counter_glass_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_generic_01_33 = shop_counter_glass_3d 0.0 0.00 0.00 0.00 1.00
bind.location_shop_generic_01_34 = shop_counter_glass_3d 0.0 0.00 0.00 0.00 1.00

# --------------------------------------------------------------------
# 4. Portas e Divisórias (Moveis-e-Caixas)
# --------------------------------------------------------------------
model.wooden_door_interior_3d = Moveis-e-Caixas/wooden_door_interior_3d.obj
bind.fixtures_doors_01_0 = wooden_door_interior_3d 0.0 0.00 0.00 0.00 1.00
bind.fixtures_doors_01_1 = wooden_door_interior_3d 0.0 0.00 0.00 0.00 1.00
bind.fixtures_doors_01_8 = wooden_door_interior_3d 0.0 0.00 0.00 0.00 1.00

# --------------------------------------------------------------------
# 5. Eletrodomésticos e Refrigeração (Eletrodomesticos)
# --------------------------------------------------------------------
model.kitchen_stove_3d = Eletrodomesticos/kitchen_stove_3d.obj
bind.appliances_cooking_01_0 = kitchen_stove_3d 0.0 0.00 0.00 0.00 1.00
bind.appliances_cooking_01_1 = kitchen_stove_3d 0.0 0.00 0.00 0.00 1.00

model.microwave_oven_3d = Eletrodomesticos/microwave_oven_3d.obj
bind.appliances_cooking_01_8 = microwave_oven_3d 0.0 0.00 0.00 0.00 1.00
bind.appliances_cooking_01_9 = microwave_oven_3d 0.0 0.00 0.00 0.00 1.00

model.refrigerator_3d = Eletrodomesticos/refrigerator_3d.obj
bind.appliances_refrigeration_01_0 = refrigerator_3d 0.0 0.00 0.00 0.00 1.00
bind.appliances_refrigeration_01_1 = refrigerator_3d 0.0 0.00 0.00 0.00 1.00

model.commercial_freezer_vertical_3d = Eletrodomesticos/commercial_freezer_vertical_3d.obj
bind.appliances_refrigeration_01_24 = commercial_freezer_vertical_3d 0.0 0.00 0.00 0.00 1.00
bind.appliances_refrigeration_01_25 = commercial_freezer_vertical_3d 0.0 0.00 0.00 0.00 1.00
bind.appliances_refrigeration_01_26 = commercial_freezer_vertical_3d 0.0 0.00 0.00 0.00 1.00

model.ice_cooler_freezer_3d = Eletrodomesticos/ice_cooler_freezer_3d.obj
bind.appliances_refrigeration_01_16 = ice_cooler_freezer_3d 0.0 0.00 0.00 0.00 1.00
bind.appliances_refrigeration_01_17 = ice_cooler_freezer_3d 0.0 0.00 0.00 0.00 1.00

# --------------------------------------------------------------------
# 6. Suprimentos, Munição e Kits Médicos (Itens-de-Chao-Loot)
# --------------------------------------------------------------------
model.military_ammo_can_3d = Itens-de-Chao-Loot/military_ammo_can_3d.obj
bind.Item_ShotgunShellsBox = military_ammo_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Item_Bullets9mmBox = military_ammo_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.Bullets9mmBox = military_ammo_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.ShotgunShellsBox = military_ammo_can_3d 0.0 0.00 0.00 0.00 1.00

model.medical_firstaid_kit_3d = Itens-de-Chao-Loot/medical_firstaid_kit_3d.obj
bind.Item_FirstAidKit = medical_firstaid_kit_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.FirstAidKit = medical_firstaid_kit_3d 0.0 0.00 0.00 0.00 1.00

# --------------------------------------------------------------------
# 7. Comidas Enlatadas e Garrafas de Bebida (Itens-de-Chao-Loot)
# --------------------------------------------------------------------
model.canned_beans_3d = Itens-de-Chao-Loot/canned_beans_3d.obj
bind.Base.TinnedBeans = canned_beans_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.OpenBeans = canned_beans_3d 0.0 0.00 0.00 0.00 1.00

model.canned_food_can_3d = Itens-de-Chao-Loot/canned_food_can_3d.obj
bind.Base.CannedChili = canned_food_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.CannedCorn = canned_food_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.CannedCarrots2 = canned_food_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.CannedPeas = canned_food_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.CannedTomato2 = canned_food_can_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.CannedBolognese = canned_food_can_3d 0.0 0.00 0.00 0.00 1.00

model.canned_sardines_3d = Itens-de-Chao-Loot/canned_sardines_3d.obj
bind.Base.CannedSardines = canned_sardines_3d 0.0 0.00 0.00 0.00 1.00

model.water_bottle_3d = Itens-de-Chao-Loot/water_bottle_3d.obj
bind.Base.WaterBottle = water_bottle_3d 0.0 0.00 0.00 0.00 1.00
bind.Base.WaterBottleFull = water_bottle_3d 0.0 0.00 0.00 0.00 1.00
"""

    with open(manifest_file, "w", encoding="utf-8") as f:
        f.write(new_manifest_content)

    print(f"[OK] pack.manifest atualizado com sucesso em: {manifest_file}")

if __name__ == "__main__":
    main()
