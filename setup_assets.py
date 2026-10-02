#!/usr/bin/env python3
"""
setup_assets.py
===============
Script de Configuração e Geração de Modelos 3D e Texturas (1 Clique).
Gera todos os modelos 3D (.obj, .mtl) e texturas locais a partir do código,
sem necessitar de downloads pesados de imagens no Git.

Uso:
    python setup_assets.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
MCP_DIR = BASE_DIR / "05-Model-3D-Extractor-MCP"
SCRIPTS_DIR = MCP_DIR / "scripts"
READY_DIR = MCP_DIR / "objetos-prontos-3d"

def log(msg, symbol="[*]"):
    print(f"{symbol} {msg}")

def verificar_dependencias():
    log("Verificando dependências Python...")
    try:
        import PIL
        log(f"Pillow detectado (v{PIL.__version__}).", "[+]")
    except ImportError:
        log("Pillow não encontrado. Instalando automaticamente...", "[!]")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])

def gerar_modelos_e_texturas():
    log("Sintetizando modelos 3D e texturas HD/PBR...")
    script_gerador = SCRIPTS_DIR / "gerar_texturas_e_modelos.py"
    if not script_gerador.exists():
        log(f"Erro: Script {script_gerador} não encontrado!", "[X]")
        return False
    
    cmd = [sys.executable, str(script_gerador)]
    res = subprocess.run(cmd, cwd=str(MCP_DIR))
    if res.returncode != 0:
        log("Falha ao gerar modelos e texturas.", "[X]")
        return False
    log("Modelos 3D e texturas gerados com sucesso!", "[+]")
    return True

def implantar_no_mod():
    log("Verificando instalação do Viewpoint Mod no Project Zomboid...")
    sys.path.insert(0, str(MCP_DIR))
    try:
        from server import deploy_ready_pack
        resultado = deploy_ready_pack()
        if resultado.get("status") == "deployed":
            log(f"Pacote implantado com sucesso em: {resultado.get('deployed_path')}", "[+]")
            log(f"Loader Lua ativo em: {resultado.get('loader_lua')}", "[+]")
            return True
        else:
            log(f"Aviso de deploy: {resultado.get('reason')}", "[!]")
            return False
    except Exception as e:
        log(f"Aviso: Não foi possível realizar o deploy automático ({e}).", "[!]")
        log("Os modelos estão prontos em '05-Model-3D-Extractor-MCP/objetos-prontos-3d/'.", "[i]")
        return True

def main():
    print("=" * 65)
    print("  🎮 Project Zomboid 3D Suite - Setup Automatizado de Assets")
    print("=" * 65)
    
    verificar_dependencias()
    
    if not gerar_modelos_e_texturas():
        sys.exit(1)
        
    implantar_no_mod()
    
    print("\n" + "=" * 65)
    print("  ✅ SETUP CONCLUÍDO COM SUCESSO!")
    print("  Todos os modelos 3D volumétricos e texturas estão prontos.")
    print("  Inicie o Project Zomboid com o mod Viewpoint para conferir.")
    print("=" * 65)

if __name__ == "__main__":
    main()
