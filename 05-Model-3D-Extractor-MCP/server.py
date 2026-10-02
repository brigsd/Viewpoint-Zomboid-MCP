"""
Project Zomboid 3D Model Extractor & Patch MCP Server
=====================================================
Servidor MCP em Python utilizando FastMCP para automação do pipeline 3D:
- Inspeção e busca de sprites e tiles do Project Zomboid
- Geração e importação de modelos 3D (.obj)
- Mapeamento e binding (Sprite 2D -> Modelo 3D) no formato nativo do Viewpoint
- Deploy automatizado e hot-reload no motor do jogo
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any

# Compatibilidade entre mcp 2.x (MCPServer) e mcp 1.x (FastMCP)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

# Diretórios padrão do sistema
PZ_GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid")
PZ_USER_DIR = Path(os.path.expanduser(r"~\Zomboid"))
VIEWPOINT_MOD_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600\3809306528\mods\Viewpoint\42")
SUITE_MODULE_DIR = Path(r"C:\Users\micro\Desktop\ProjectZomboid-FirstPerson-Suite\05-Model-3D-Extractor-MCP")
STAGING_PACKS_DIR = SUITE_MODULE_DIR / "packs"
READY_MODELS_DIR = SUITE_MODULE_DIR / "objetos-prontos-3d"
VANILLA_DIR = SUITE_MODULE_DIR / "objetos-extraidos-vanilla"

STAGING_PACKS_DIR.mkdir(parents=True, exist_ok=True)
READY_MODELS_DIR.mkdir(parents=True, exist_ok=True)
VANILLA_DIR.mkdir(parents=True, exist_ok=True)

# Inicializa o servidor FastMCP
mcp = FastMCP("PZ-3D-Model-Extractor")

# Dicionário de categorias conhecidas de tiles no Project Zomboid Build 42
SPRITE_CATALOG = {
    "furniture_seating": {
        "description": "Cadeiras, poltronas, sofás e bancos",
        "prefixes": ["furniture_seating_indoor_01", "furniture_seating_indoor_02", "furniture_seating_indoor_03", "furniture_seating_outdoor_01"],
        "common_tiles": ["furniture_seating_indoor_01_0", "furniture_seating_indoor_01_1", "furniture_seating_indoor_01_16", "furniture_seating_indoor_01_24"]
    },
    "furniture_tables": {
        "description": "Mesas de centro, mesas de jantar, escrivaninhas e balcões",
        "prefixes": ["furniture_tables_high_01", "furniture_tables_low_01", "furniture_tables_indoor_01"],
        "common_tiles": ["furniture_tables_high_01_0", "furniture_tables_high_01_1", "furniture_tables_low_01_0"]
    },
    "appliances_cooking": {
        "description": "Fogões, fornos, micro-ondas e geladeiras",
        "prefixes": ["appliances_cooking_01", "appliances_refrigeration_01"],
        "common_tiles": ["appliances_cooking_01_0", "appliances_cooking_01_1", "appliances_refrigeration_01_0"]
    },
    "furniture_storage": {
        "description": "Caixotes de madeira, estantes, armários e gavetas",
        "prefixes": ["furniture_storage_01", "furniture_storage_02", "furniture_shelving_01"],
        "common_tiles": ["furniture_storage_01_16", "furniture_storage_01_17", "furniture_shelving_01_0"]
    },
    "lighting_indoor": {
        "description": "Luminárias de mesa, abajures, luzes de teto e arandelas",
        "prefixes": ["lighting_indoor_01", "lighting_outdoor_01"],
        "common_tiles": ["lighting_indoor_01_0", "lighting_indoor_01_1"]
    },
    "appliances_media": {
        "description": "Televisores, rádios, computadores e telefones",
        "prefixes": ["appliances_television_01", "appliances_radio_01", "appliances_comms_01"],
        "common_tiles": ["appliances_television_01_0", "appliances_radio_01_0"]
    },
    "containers_outdoor": {
        "description": "Lixeiras, latões de lixo e caixas de correio",
        "prefixes": ["street_decoration_01"],
        "common_tiles": ["street_decoration_01_0", "street_decoration_01_1"]
    }
}


@mcp.tool()
def get_diagnostics() -> Dict[str, Any]:
    """Retorna o status do ambiente, diretórios do Project Zomboid, Viewpoint e packs 3D."""
    return {
        "game_dir_exists": PZ_GAME_DIR.exists(),
        "game_dir": str(PZ_GAME_DIR),
        "viewpoint_installed": VIEWPOINT_MOD_DIR.exists(),
        "viewpoint_dir": str(VIEWPOINT_MOD_DIR),
        "staging_packs_dir": str(STAGING_PACKS_DIR),
        "active_packs": [p.name for p in STAGING_PACKS_DIR.iterdir() if p.is_dir()],
        "status": "ready"
    }


@mcp.tool()
def list_sprite_categories() -> Dict[str, Any]:
    """Lista as principais categorias de objetos/tiles do Project Zomboid com prefixos e exemplos."""
    return {
        "categories": SPRITE_CATALOG,
        "total_categories": len(SPRITE_CATALOG)
    }


@mcp.tool()
def search_sprites(query: str, max_results: int = 20) -> List[Dict[str, str]]:
    """Pesquisa sprites e tiles por palavra-chave (ex: 'chair', 'table', 'cooking', 'storage', '01')."""
    query_lower = query.lower()
    results = []

    # Procura no catálogo interno
    for cat_name, cat_data in SPRITE_CATALOG.items():
        if query_lower in cat_name or query_lower in cat_data["description"].lower():
            for tile in cat_data["common_tiles"]:
                results.append({
                    "tile_name": tile,
                    "category": cat_name,
                    "description": cat_data["description"]
                })
        else:
            for tile in cat_data["common_tiles"]:
                if query_lower in tile:
                    results.append({
                        "tile_name": tile,
                        "category": cat_name,
                        "description": cat_data["description"]
                    })

    # Procura também em arquivos .tiles do jogo se existirem
    tile_defs = PZ_GAME_DIR / "media" / "tiledefinitions.tiles"
    if tile_defs.exists() and len(results) < max_results:
        try:
            with open(tile_defs, "rb") as f:
                content = f.read().decode("latin1", errors="ignore")
                for line in content.split("\n"):
                    if query_lower in line.lower() and "_" in line:
                        parts = line.strip().split()
                        if parts:
                            candidate = parts[0]
                            if candidate.isalnum() or "_" in candidate:
                                results.append({
                                    "tile_name": candidate,
                                    "category": "tiles_pack",
                                    "description": "Extracted from tiledefinitions.tiles"
                                })
                                if len(results) >= max_results:
                                    break
        except Exception:
            pass

    return results[:max_results]


@mcp.tool()
def create_model_pack(pack_id: str, pack_name: str) -> Dict[str, Any]:
    """Cria uma estrutura completa de pacote de modelos 3D compatível com o Viewpoint."""
    pack_dir = STAGING_PACKS_DIR / pack_id
    models_dir = pack_dir / "models"
    textures_dir = pack_dir / "textures"

    models_dir.mkdir(parents=True, exist_ok=True)
    textures_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = pack_dir / "pack.manifest"
    if not manifest_file.exists():
        manifest_content = f"""id = {pack_id}
name = {pack_name}

# ====================================================================
# Viewpoint 3D Model Pack Manifest
# ====================================================================
# Formato:
# model.<id_modelo> = models/<arquivo>.obj
# bind.<nome_do_sprite_2d> = <id_modelo> <graus_rotacao> <offset_x> <offset_y> <offset_z> <escala>
# ====================================================================
"""
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(manifest_content)

    return {
        "status": "created",
        "pack_id": pack_id,
        "pack_name": pack_name,
        "pack_path": str(pack_dir),
        "manifest_path": str(manifest_file)
    }


@mcp.tool()
def generate_box_model(
    pack_id: str,
    model_name: str,
    width: float = 0.8,
    height: float = 0.8,
    depth: float = 0.8,
    texture_name: str = "diffuse.png"
) -> Dict[str, Any]:
    """Gera uma malha 3D (.obj) em formato de paralelepípedo com coordenadas UV e normais calculadas."""
    pack_dir = STAGING_PACKS_DIR / pack_id
    if not pack_dir.exists():
        return {"error": f"Pack '{pack_id}' não existe. Use create_model_pack primeiro."}

    models_dir = pack_dir / "models"
    models_dir.mkdir(exist_ok=True)
    obj_path = models_dir / f"{model_name}.obj"

    hw = width / 2.0
    hh = height
    hd = depth / 2.0

    # Definição de vértices, coordenadas de textura (UV) e normais
    obj_lines = [
        f"# Model: {model_name}",
        f"# Dimensions: {width} x {height} x {depth}",
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
        # Coordenadas UV (vt u v)
        "vt 0.0000 0.0000",
        "vt 1.0000 0.0000",
        "vt 1.0000 1.0000",
        "vt 0.0000 1.0000",
        "",
        # Faces (f v/vt/vn ...)
        "s 1",
        "usemtl Material",
        # Frente
        "f 5/1/2 6/2/2 7/3/2 8/4/2",
        # Traseira
        "f 2/1/1 1/2/1 4/3/1 3/4/1",
        # Topo
        "f 8/1/5 7/2/5 3/3/5 4/4/5",
        # Fundo
        "f 1/1/6 2/2/6 6/3/6 5/4/6",
        # Esquerda
        "f 1/1/3 5/2/3 8/3/3 4/4/3",
        # Direita
        "f 6/1/4 2/2/4 3/3/4 7/4/4",
        ""
    ]

    with open(obj_path, "w", encoding="utf-8") as f:
        f.write("\n".join(obj_lines))

    # Cria arquivo MTL associado
    mtl_path = models_dir / f"{model_name}.mtl"
    mtl_lines = [
        f"newmtl Material",
        "Ka 1.000 1.000 1.000",
        "Kd 1.000 1.000 1.000",
        "Ks 0.000 0.000 0.000",
        "d 1.0",
        "illum 2",
        f"map_Kd ../textures/{texture_name}"
    ]
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write("\n".join(mtl_lines))

    # Registra o modelo no pack.manifest
    manifest_file = pack_dir / "pack.manifest"
    model_entry = f"model.{model_name} = models/{model_name}.obj\n"
    with open(manifest_file, "r", encoding="utf-8") as f:
        content = f.read()
    if f"model.{model_name}" not in content:
        with open(manifest_file, "a", encoding="utf-8") as f:
            f.write(model_entry)

    return {
        "status": "generated",
        "model_name": model_name,
        "obj_path": str(obj_path),
        "mtl_path": str(mtl_path),
        "dimensions": {"width": width, "height": height, "depth": depth}
    }


@mcp.tool()
def generate_custom_obj(pack_id: str, model_name: str, obj_content: str) -> Dict[str, Any]:
    """Salva um modelo 3D (.obj) customizado diretamente na pasta de modelos do pack."""
    pack_dir = STAGING_PACKS_DIR / pack_id
    if not pack_dir.exists():
        return {"error": f"Pack '{pack_id}' não encontrado."}

    models_dir = pack_dir / "models"
    models_dir.mkdir(exist_ok=True)
    obj_path = models_dir / f"{model_name}.obj"

    with open(obj_path, "w", encoding="utf-8") as f:
        f.write(obj_content)

    manifest_file = pack_dir / "pack.manifest"
    with open(manifest_file, "r", encoding="utf-8") as f:
        content = f.read()
    if f"model.{model_name}" not in content:
        with open(manifest_file, "a", encoding="utf-8") as f:
            f.write(f"model.{model_name} = models/{model_name}.obj\n")

    return {
        "status": "saved",
        "model_name": model_name,
        "obj_path": str(obj_path)
    }


@mcp.tool()
def bind_sprite_to_3d(
    pack_id: str,
    sprite_name: str,
    model_name: str,
    rotation_degrees: float = 0.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    scale: float = 1.0
) -> Dict[str, Any]:
    """Cria ou atualiza a ligação entre um sprite 2D do Zomboid e o modelo 3D no pack.manifest."""
    pack_dir = STAGING_PACKS_DIR / pack_id
    manifest_file = pack_dir / "pack.manifest"
    if not manifest_file.exists():
        return {"error": f"Manifesto do pack '{pack_id}' não existe."}

    bind_line = f"bind.{sprite_name} = {model_name} {rotation_degrees:.1f} {offset_x:.2f} {offset_y:.2f} {offset_z:.2f} {scale:.2f}"

    lines = []
    found = False
    with open(manifest_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith(f"bind.{sprite_name}"):
                lines.append(bind_line + "\n")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(bind_line + "\n")

    with open(manifest_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {
        "status": "bound",
        "sprite_name": sprite_name,
        "model_name": model_name,
        "binding": bind_line
    }


@mcp.tool()
def list_pack_manifest(pack_id: str) -> Dict[str, Any]:
    """Lê o conteúdo completo do manifesto de um pack 3D."""
    manifest_file = STAGING_PACKS_DIR / pack_id / "pack.manifest"
    if not manifest_file.exists():
        return {"error": f"Pack '{pack_id}' não encontrado."}

    with open(manifest_file, "r", encoding="utf-8") as f:
        content = f.read()

    return {
        "pack_id": pack_id,
        "manifest": content
    }


@mcp.tool()
def deploy_pack(pack_id: str) -> Dict[str, Any]:
    """Copia o pack 3D para o diretório ativo do Viewpoint no jogo e gera o carregador Lua."""
    source_pack = STAGING_PACKS_DIR / pack_id
    if not source_pack.exists():
        return {"error": f"Pack de origem '{pack_id}' não encontrado."}

    # Destino dentro da pasta media do mod Viewpoint
    dest_pack = VIEWPOINT_MOD_DIR / "media" / "modelpacks" / pack_id
    dest_pack.parent.mkdir(parents=True, exist_ok=True)

    if dest_pack.exists():
        shutil.rmtree(dest_pack)
    shutil.copytree(source_pack, dest_pack)

    # Injeta um script Lua de auto-registro no Viewpoint se não existir
    lua_client_dir = VIEWPOINT_MOD_DIR / "media" / "lua" / "client"
    lua_client_dir.mkdir(parents=True, exist_ok=True)
    loader_lua = lua_client_dir / "Viewpoint_AutoRegisterPacks.lua"

    lua_code = f"""-- Auto-registrador de Model Packs 3D gerados pelo MCP
if Viewpoint and Viewpoint.ModelPacks then
    Viewpoint.ModelPacks.register("Viewpoint", "modelpacks/{pack_id}")
    print("[MCP 3D] Model Pack registrado: {pack_id}")
end
"""
    with open(loader_lua, "w", encoding="utf-8") as f:
        f.write(lua_code)

    return {
        "status": "deployed",
        "pack_id": pack_id,
        "deployed_path": str(dest_pack),
        "loader_lua": str(loader_lua)
    }


@mcp.tool()
def list_ready_models() -> Dict[str, Any]:
    """Lista todos os modelos 3D prontos na pasta objetos-prontos-3d agrupados por categoria."""
    categories = {}
    for sub in READY_MODELS_DIR.iterdir():
        if sub.is_dir():
            models = [f.name for f in sub.glob("*.obj")]
            if models:
                categories[sub.name] = models

    manifest_file = READY_MODELS_DIR / "pack.manifest"
    has_manifest = manifest_file.exists()

    return {
        "total_categories": len(categories),
        "categories": categories,
        "has_master_manifest": has_manifest,
        "folder_path": str(READY_MODELS_DIR)
    }


@mcp.tool()
def list_vanilla_extracted() -> Dict[str, Any]:
    """Lista todos os modelos 3D e arquivos de referência da pasta objetos-extraidos-vanilla."""
    files = [f.name for f in VANILLA_DIR.iterdir() if f.is_file() and not f.name.endswith(".py")]
    catalog_file = VANILLA_DIR / "sprites_vanilla_catalog.json"
    catalog_data = None
    if catalog_file.exists():
        with open(catalog_file, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)

    original_manifest = VANILLA_DIR / "modelos-3d-originais" / "modelos_vanilla_manifest.json"
    orig_data = None
    if original_manifest.exists():
        with open(original_manifest, "r", encoding="utf-8") as f:
            orig_data = json.load(f)

    return {
        "total_files": len(files),
        "files": files,
        "catalog_summary": {k: len(v) for k, v in catalog_data.items()} if catalog_data else None,
        "modelos_originais_total": orig_data.get("total_modelos") if orig_data else 0,
        "modelos_originais_por_categoria": orig_data.get("categorias") if orig_data else None,
        "folder_path": str(VANILLA_DIR)
    }


@mcp.tool()
def deploy_ready_pack() -> Dict[str, Any]:
    """Faz o deploy direto da pasta inteira 'objetos-prontos-3d' para o Viewpoint ativo no jogo."""
    dest_pack = VIEWPOINT_MOD_DIR / "media" / "modelpacks" / "zomboid-3d-essentials"
    dest_pack.parent.mkdir(parents=True, exist_ok=True)

    if dest_pack.exists():
        shutil.rmtree(dest_pack)
    shutil.copytree(READY_MODELS_DIR, dest_pack)

    lua_client_dir = VIEWPOINT_MOD_DIR / "media" / "lua" / "client"
    lua_client_dir.mkdir(parents=True, exist_ok=True)
    loader_lua = lua_client_dir / "Viewpoint_AutoRegisterPacks.lua"

    lua_code = """-- Auto-registrador de Model Packs 3D gerados pelo MCP
if Viewpoint and Viewpoint.ModelPacks then
    Viewpoint.ModelPacks.register("Viewpoint", "modelpacks/zomboid-3d-essentials")
    print("[MCP 3D] Model Pack 'zomboid-3d-essentials' registrado e ativo!")
end
"""
    with open(loader_lua, "w", encoding="utf-8") as f:
        f.write(lua_code)

    return {
        "status": "deployed",
        "pack_name": "zomboid-3d-essentials",
        "deployed_path": str(dest_pack),
        "loader_lua": str(loader_lua)
    }


@mcp.tool()
def capture_inspections(model_name: Optional[str] = None) -> Dict[str, Any]:
    """Aciona a esteira headless de renderização e auditoria 3D para gerar fotos e dados técnicos."""
    import subprocess
    script = SUITE_MODULE_DIR / "scripts" / "capturar_inspecoes.py"
    if not script.exists():
        return {"error": "Script capturar_inspecoes.py não encontrado."}

    cmd = [sys.executable, str(script)]
    if model_name:
        cmd.extend(["--obj", model_name])
    else:
        cmd.append("--all")

    res = subprocess.run(cmd, cwd=str(SUITE_MODULE_DIR), capture_output=True, text=True)
    return {
        "status": "success" if res.returncode == 0 else "error",
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr
    }


@mcp.tool()
def list_inspections() -> Dict[str, Any]:
    """Lista todas as inspeções realizadas, fotos geradas e status de aprovação técnica."""
    inspecoes_dir = VANILLA_DIR / "inspecoes"
    if not inspecoes_dir.exists():
        return {"total": 0, "inspections": {}}

    res = {}
    for d in sorted(inspecoes_dir.iterdir()):
        if d.is_dir():
            dados_file = d / "dados-tecnicos.json"
            if dados_file.exists():
                with open(dados_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                res[d.name] = {
                    "dimensoes_metros": data.get("dimensoes_metros"),
                    "volume_m3": data.get("volume_delimitador_m3"),
                    "vertices": data.get("total_vertices"),
                    "faces": data.get("total_faces"),
                    "status_solo": data.get("alinhamento_solo_valido"),
                    "fotos": [p.name for p in d.glob("*.png")]
                }
    return {
        "total": len(res),
        "inspections": res,
        "inspecoes_path": str(inspecoes_dir)
    }


if __name__ == "__main__":
    # Inicia o servidor MCP via stdio
    mcp.run()
