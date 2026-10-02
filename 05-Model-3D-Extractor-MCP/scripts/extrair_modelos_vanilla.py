"""
Script de Extração em Massa de Modelos 3D Vanilla do Project Zomboid Build 42.
Varre media/models_X e extrai modelos estruturados para objetos-extraidos-vanilla/modelos-3d-originais.
"""

import os
import shutil
import json
from pathlib import Path

PZ_MEDIA = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media")
MODELS_X = PZ_MEDIA / "models_X"
DEST_BASE = Path(r"C:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\05-Model-3D-Extractor-MCP\objetos-extraidos-vanilla\modelos-3d-originais")

def main():
    print("=== Iniciando Extração de Modelos 3D Vanilla ===")
    DEST_BASE.mkdir(parents=True, exist_ok=True)

    extracted_manifest = []

    # 1. Extração de IsoObject (Todos os 63 modelos do jogo)
    iso_dest = DEST_BASE / "IsoObject"
    iso_dest.mkdir(parents=True, exist_ok=True)
    iso_src = MODELS_X / "IsoObject"
    if iso_src.exists():
        for f in iso_src.glob("*.*"):
            if f.suffix.lower() in [".glb", ".fbx", ".x"]:
                dst = iso_dest / f.name
                shutil.copy2(f, dst)
                extracted_manifest.append({
                    "nome_arquivo": f.name,
                    "categoria": "IsoObject",
                    "caminho_relativo": f"IsoObject/{f.name}",
                    "formato": f.suffix.lower(),
                    "tamanho_bytes": f.stat().st_size,
                    "descricao": f"Objeto estático do mundo 3D ({f.stem})"
                })
        print(f"[OK] IsoObject extraídos: {len([x for x in extracted_manifest if x['categoria'] == 'IsoObject'])}")

    # 2. Extração de WorldItems & Itens de Chão Canônicos
    world_dest = DEST_BASE / "WorldItems"
    world_dest.mkdir(parents=True, exist_ok=True)
    
    # Do diretório WorldItems e da raiz de models_X
    world_src = MODELS_X / "WorldItems"
    root_src = MODELS_X

    # Padrões canônicos essenciais
    world_patterns = [
        "can", "bottle", "beans", "food", "soup", "ammo", "bullet", "round", "shell",
        "firstaid", "med", "pill", "bandage", "antibiotic", "alarmclock", "battery",
        "radio", "generator", "hammer", "wrench", "screwdriver", "saw", "knife",
        "beer", "wine", "whiskey", "bleach", "canteen", "pot", "pan", "apple", "bread",
        "meat", "fish", "book", "newspaper", "map", "lighter", "matches", "gascan",
        "flashlight", "duffel", "backpack", "pouch", "holster"
    ]

    copied_world_files = set()

    # Raiz de models_X (.x e .fbx)
    for f in root_src.glob("*.*"):
        if f.suffix.lower() in [".x", ".fbx", ".glb"]:
            name_lower = f.name.lower()
            if any(p in name_lower for p in world_patterns) and f.name not in copied_world_files:
                dst = world_dest / f.name
                shutil.copy2(f, dst)
                copied_world_files.add(f.name)
                extracted_manifest.append({
                    "nome_arquivo": f.name,
                    "categoria": "WorldItems",
                    "caminho_relativo": f"WorldItems/{f.name}",
                    "formato": f.suffix.lower(),
                    "tamanho_bytes": f.stat().st_size,
                    "descricao": f"Item de inventário/chão raiz ({f.stem})"
                })

    # Subdiretório WorldItems (.fbx)
    if world_src.exists():
        for f in world_src.glob("*.*"):
            if f.suffix.lower() in [".fbx", ".x", ".glb"]:
                name_lower = f.name.lower()
                if any(p in name_lower for p in world_patterns) and f.name not in copied_world_files:
                    dst = world_dest / f.name
                    shutil.copy2(f, dst)
                    copied_world_files.add(f.name)
                    extracted_manifest.append({
                        "nome_arquivo": f.name,
                        "categoria": "WorldItems",
                        "caminho_relativo": f"WorldItems/{f.name}",
                        "formato": f.suffix.lower(),
                        "tamanho_bytes": f.stat().st_size,
                        "descricao": f"Item 3D de chão e loot ({f.stem})"
                    })

    print(f"[OK] WorldItems extraídos: {len([x for x in extracted_manifest if x['categoria'] == 'WorldItems'])}")

    # 3. Extração de Armas (weapons: firearm, 1handed, 2handed)
    weap_dest = DEST_BASE / "weapons"
    weap_dest.mkdir(parents=True, exist_ok=True)
    weap_src = MODELS_X / "weapons"

    weap_keywords = [
        "shotgun", "pistol", "revolver", "rifle", "m14", "m16", "varmint",
        "axe", "bat", "crowbar", "hammer", "knife", "machete", "pipe", "sledgehammer",
        "katana", "spear", "shovel", "golfclub", "nightstick", "cleaver", "handgun"
    ]

    copied_weap = set()
    if weap_src.exists():
        for f in weap_src.rglob("*.*"):
            if f.suffix.lower() in [".x", ".fbx", ".glb"]:
                name_lower = f.name.lower()
                if any(k in name_lower for k in weap_keywords) and f.name not in copied_weap:
                    # Copia para armas
                    dst = weap_dest / f.name
                    shutil.copy2(f, dst)
                    copied_weap.add(f.name)
                    extracted_manifest.append({
                        "nome_arquivo": f.name,
                        "categoria": "weapons",
                        "caminho_relativo": f"weapons/{f.name}",
                        "formato": f.suffix.lower(),
                        "tamanho_bytes": f.stat().st_size,
                        "descricao": f"Arma vanilla ({f.stem})"
                    })

    print(f"[OK] Armas extraídas: {len([x for x in extracted_manifest if x['categoria'] == 'weapons'])}")

    # 4. Extração de Veículos e Peças (vehicles)
    veh_dest = DEST_BASE / "vehicles"
    veh_dest.mkdir(parents=True, exist_ok=True)
    veh_src = MODELS_X / "vehicles"

    copied_veh = set()
    if veh_src.exists():
        for f in veh_src.glob("*.*"):
            if f.suffix.lower() in [".fbx", ".x", ".glb"]:
                dst = veh_dest / f.name
                shutil.copy2(f, dst)
                copied_veh.add(f.name)
                extracted_manifest.append({
                    "nome_arquivo": f.name,
                    "categoria": "vehicles",
                    "caminho_relativo": f"vehicles/{f.name}",
                    "formato": f.suffix.lower(),
                    "tamanho_bytes": f.stat().st_size,
                    "descricao": f"Veículo ou componente veicular ({f.stem})"
                })

    print(f"[OK] Veículos extraídos: {len([x for x in extracted_manifest if x['categoria'] == 'vehicles'])}")

    # 5. Extração de Corpos, Animais e Roupas (Skinned & Static)
    chars_dest = DEST_BASE / "corpos_e_personagens"
    chars_dest.mkdir(parents=True, exist_ok=True)

    char_keywords = ["bull", "cow", "chicken", "pig", "sheep", "body", "skeleton", "bob_bone", "greave"]
    copied_chars = set()

    for p in [MODELS_X / "Skinned", MODELS_X / "Static"]:
        if p.exists():
            for f in p.rglob("*.*"):
                if f.suffix.lower() in [".x", ".fbx", ".glb"]:
                    name_lower = f.name.lower()
                    if any(k in name_lower for k in char_keywords) and f.name not in copied_chars:
                        dst = chars_dest / f.name
                        shutil.copy2(f, dst)
                        copied_chars.add(f.name)
                        extracted_manifest.append({
                            "nome_arquivo": f.name,
                            "categoria": "corpos_e_personagens",
                            "caminho_relativo": f"corpos_e_personagens/{f.name}",
                            "formato": f.suffix.lower(),
                            "tamanho_bytes": f.stat().st_size,
                            "descricao": f"Malha esquelética/personagem/animal ({f.stem})"
                        })

    print(f"[OK] Corpos/personagens extraídos: {len([x for x in extracted_manifest if x['categoria'] == 'corpos_e_personagens'])}")

    # Salva o manifesto de modelos vanilla
    manifest_path = DEST_BASE / "modelos_vanilla_manifest.json"
    manifest_data = {
        "total_modelos": len(extracted_manifest),
        "categorias": {
            "IsoObject": len([x for x in extracted_manifest if x["categoria"] == "IsoObject"]),
            "WorldItems": len([x for x in extracted_manifest if x["categoria"] == "WorldItems"]),
            "weapons": len([x for x in extracted_manifest if x["categoria"] == "weapons"]),
            "vehicles": len([x for x in extracted_manifest if x["categoria"] == "vehicles"]),
            "corpos_e_personagens": len([x for x in extracted_manifest if x["categoria"] == "corpos_e_personagens"])
        },
        "modelos": extracted_manifest
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    print(f"=== Extração concluída com sucesso! Total: {len(extracted_manifest)} modelos extraídos. ===")
    print(f"Manifesto salvo em: {manifest_path}")

if __name__ == "__main__":
    main()
