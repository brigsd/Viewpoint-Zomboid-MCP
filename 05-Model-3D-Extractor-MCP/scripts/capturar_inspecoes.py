#!/usr/bin/env python3
"""
capturar_inspecoes.py
=====================
Esteira de Automação de Captura Fotográfica Headless e Inspeção Técnica 3D.
Gera renders limpos sem UI (modo auditoria) e ficha técnica com metadados
para os modelos 3D do Project Zomboid (Viewpoint FPS Suite).

Uso:
    python capturar_inspecoes.py --all
    python capturar_inspecoes.py --obj caminho/do/modelo.obj
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Garante suporte a UTF-8 no Windows Console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Caminhos padrão da suíte
SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_DIR = SCRIPT_DIR.parent
SUITE_ROOT = MODULE_DIR.parent
READY_MODELS_DIR = MODULE_DIR / "objetos-prontos-3d"
INSPECOES_DIR = MODULE_DIR / "objetos-extraidos-vanilla" / "inspecoes"
MECANIFICA_DIR = Path(r"C:\Users\micro\Desktop\mecanifica")
NODE_RENDERER = SCRIPT_DIR / "render_headless_three.mjs"

# 7 Modelos Canônicos de Referência
MODELOS_CANONICOS = [
    {
        "id": "wooden_crate_3d",
        "categoria": "Moveis-e-Caixas",
        "nome_legivel": "Caixa de Madeira (Wooden Crate)",
        "descricao": "Caixote rústico de madeira com ripas e pregos para armazenamento."
    },
    {
        "id": "kitchen_stove_3d",
        "categoria": "Eletrodomesticos",
        "nome_legivel": "Fogão de Cozinha (Kitchen Stove)",
        "descricao": "Fogão doméstico com 4 bocas, forno e puxadores frontais."
    },
    {
        "id": "kitchen_fridge_3d",
        "categoria": "Eletrodomesticos",
        "nome_legivel": "Geladeira de Cozinha (Kitchen Refrigerator)",
        "descricao": "Refrigerador vertical de duas portas com prateleiras e puxador."
    },
    {
        "id": "counter_sink_3d",
        "categoria": "Moveis-e-Caixas",
        "nome_legivel": "Balcão de Cozinha com Pia (Counter Sink)",
        "descricao": "Gabinete de cozinha em madeira/inox com cuba de pia embutida."
    },
    {
        "id": "microwave_oven_3d",
        "categoria": "Eletrodomesticos",
        "nome_legivel": "Forno Micro-ondas (Microwave Oven)",
        "descricao": "Micro-ondas de bancada com visor de vidro, teclado digital e porta."
    },
    {
        "id": "medical_box_3d",
        "categoria": "Itens-de-Chao-Loot",
        "nome_legivel": "Kit Médico de Primeiros Socorros (First Aid Kit)",
        "descricao": "Maleta médica branca portátil com cruz vermelha e fechos metálicos."
    },
    {
        "id": "shotgun_ammo_box_3d",
        "categoria": "Itens-de-Chao-Loot",
        "nome_legivel": "Caixa de Munição de Calibre 12 (Shotgun Ammo Box)",
        "descricao": "Caixa original de papelão com munições calibre 12 e código de barras."
    },
    {
        "id": "store_shelves_3d",
        "categoria": "Moveis-e-Caixas",
        "nome_legivel": "Gôndola de Supermercado (Store Shelves)",
        "descricao": "Prateleira modular de gôndola de mercado com 3 níveis e colunas de sustentação."
    },
    {
        "id": "canned_sardines_3d",
        "categoria": "Itens-de-Chao-Loot",
        "nome_legivel": "Lata de Sardinhas (Canned Sardines)",
        "descricao": "Lata achatada de sardinha em conserva com textura oficial do jogo."
    },
    {
        "id": "canned_beans_3d",
        "categoria": "Itens-de-Chao-Loot",
        "nome_legivel": "Lata de Feijão (Canned Beans)",
        "descricao": "Lata cilíndrica de feijão com textura oficial RefriedBeans de Kentucky 1993."
    },
    {
        "id": "water_bottle_3d",
        "categoria": "Itens-de-Chao-Loot",
        "nome_legivel": "Garrafa de Água Mineral (Water Bottle)",
        "descricao": "Garrafa cilíndrica de água com textura oficial WaterBottleFull."
    },
    {
        "id": "store_shelf_gondola_3d",
        "categoria": "Moveis-e-Caixas",
        "nome_legivel": "Gôndola Dupla de Supermercado (Store Gondola)",
        "descricao": "Gôndola metálica de loja com acabamento bege e fitas de preços."
    }
]


def analisar_geometria_obj(caminho_obj: Path) -> Dict[str, Any]:
    """Lê um arquivo .obj e calcula métricas geométricas analíticas com precisão."""
    vertices = []
    normais = []
    uvs = []
    faces = []

    with open(caminho_obj, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue

            partes = linha.split()
            tipo = partes[0]

            if tipo == "v":
                vertices.append([float(partes[1]), float(partes[2]), float(partes[3])])
            elif tipo == "vn":
                normais.append([float(partes[1]), float(partes[2]), float(partes[3])])
            elif tipo == "vt":
                uvs.append([float(partes[1]), float(partes[2])])
            elif tipo == "f":
                faces.append(partes[1:])

    if not vertices:
        raise ValueError(f"O arquivo {caminho_obj} não contém vértices válidos.")

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    largura_x = round(max_x - min_x, 4)
    altura_y = round(max_y - min_y, 4)
    profundidade_z = round(max_z - min_z, 4)
    volume_m3 = round(largura_x * altura_y * profundidade_z, 6)

    origem_base_y = round(min_y, 4)
    alinhamento_solo = abs(origem_base_y) < 0.001

    return {
        "arquivo": str(caminho_obj),
        "total_vertices": len(vertices),
        "total_faces": len(faces),
        "total_normais": len(normais),
        "total_uvs": len(uvs),
        "bounding_box": {
            "min": {"x": min_x, "y": min_y, "z": min_z},
            "max": {"x": max_x, "y": max_y, "z": max_z}
        },
        "dimensoes_metros": {
            "largura_x": largura_x,
            "altura_y": altura_y,
            "profundidade_z": profundidade_z
        },
        "volume_delimitador_m3": volume_m3,
        "origem_base_y": origem_base_y,
        "alinhamento_solo_valido": alinhamento_solo
    }


def renderizar_via_three_playwright(lista_modelos: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Executa o motor headless de renderização Three.js via Playwright."""
    if not NODE_RENDERER.exists():
        print(f"[Erro] Script do motor Three.js não encontrado em {NODE_RENDERER}", file=sys.stderr)
        return False

    cmd = ["node", str(NODE_RENDERER)]
    print(f"[Captura Headless] Acionando motor Three.js + Playwright...")

    resultado = subprocess.run(cmd, cwd=str(MECANIFICA_DIR), capture_output=True, text=True)
    if resultado.returncode != 0:
        print(f"[Erro] Falha na execução do Node Three renderer:\n{resultado.stderr}", file=sys.stderr)
        return False

    print(resultado.stdout)
    return True


def renderizar_fallback_matplotlib(caminho_obj: Path, pasta_saida: Path) -> bool:
    """Renderizador alternativo 3D em Python via Matplotlib para contingência estrita."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError:
        print("[Aviso] Matplotlib não disponível para fallback.", file=sys.stderr)
        return False

    vertices = []
    faces = []
    with open(caminho_obj, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            p = linha.strip().split()
            if not p:
                continue
            if p[0] == "v":
                vertices.append([float(p[1]), float(p[2]), float(p[3])])
            elif p[0] == "f":
                indices = [int(v.split('/')[0]) - 1 for v in p[1:]]
                faces.append(indices)

    if not vertices or not faces:
        return False

    pasta_saida.mkdir(parents=True, exist_ok=True)
    vistas = [
        ("isometrica", 30, 45),
        ("frontal", 0, 0),
        ("direita", 0, 90),
        ("superior", 90, -90)
    ]

    for nome_vista, elev, azim in vistas:
        fig = plt.figure(figsize=(8, 8), dpi=120, facecolor="#14171c")
        ax = fig.add_subplot(111, projection='3d', facecolor="#14171c")

        poly3d = [[vertices[idx] for idx in face] for face in faces]
        colecao = Poly3DCollection(poly3d, facecolors="#76879e", edgecolors="#28303d", linewidths=1.5, alpha=0.95)
        ax.add_collection3d(colecao)

        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]

        max_range = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)) * 0.7
        mid_x = (max(xs)+min(xs)) * 0.5
        mid_y = (max(ys)+min(ys)) * 0.5
        mid_z = (max(zs)+min(zs)) * 0.5

        ax.set_xlim(mid_x - max_range, mid_x + max_range)
        ax.set_ylim(mid_y - max_range, mid_y + max_range)
        ax.set_zlim(mid_z - max_range, mid_z + max_range)

        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()

        caminho_png = pasta_saida / f"{nome_vista}.png"
        plt.savefig(caminho_png, bbox_inches='tight', pad_inches=0, facecolor=fig.get_facecolor(), transparent=False)
        plt.close(fig)

    return True


def verificar_integridade_inspecoes(alvos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica se todas as 4 imagens canônicas e arquivos JSON foram criados e são válidos."""
    relatorio = {
        "total_alvos": len(alvos),
        "total_aprovados": 0,
        "detalhes": {}
    }

    for item in alvos:
        nome = item["id"]
        pasta = INSPECOES_DIR / nome
        if not pasta.exists():
            relatorio["detalhes"][nome] = {"status": "PASTA_NAO_ENCONTRADA"}
            continue

        arquivos_esperados = [
            "isometrica.png",
            "frontal.png",
            "direita.png",
            "superior.png",
            "dados-tecnicos.json",
            "auditoria.json",
            "relatorio_inspecao.md"
        ]

        faltantes = []
        tamanhos = {}
        for arq in arquivos_esperados:
            p = pasta / arq
            if not p.exists() or p.stat().st_size == 0:
                faltantes.append(arq)
            else:
                tamanhos[arq] = p.stat().st_size

        if not faltantes:
            relatorio["total_aprovados"] += 1
            status = "INTEGRO"
        else:
            status = f"INCOMPLETO_FALTANDO_{len(faltantes)}"

        relatorio["detalhes"][nome] = {
            "status": status,
            "pasta": str(pasta),
            "faltantes": faltantes,
            "arquivos": tamanhos
        }

    return relatorio


def executar_bateria_completa() -> int:
    """Executa a bateria completa para todos os 7 modelos canônicos."""
    print("====================================================================")
    print("[*] Iniciando Esteira de Inspeção 3D Headless (Project Zomboid B42)")
    print("====================================================================")
    INSPECOES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Roda o renderizador WebGL Three.js via Playwright
    sucesso_three = renderizar_via_three_playwright()

    if not sucesso_three:
        print("[Aviso] Tentando renderização de contingência via Python Matplotlib...")
        for modelo in MODELOS_CANONICOS:
            nome = modelo["id"]
            pasta_out = INSPECOES_DIR / nome
            # Busca obj
            candidatos = [
                READY_MODELS_DIR / modelo["categoria"] / f"{nome}.obj",
                READY_MODELS_DIR / "Moveis-e-Caixas" / f"{nome}.obj",
                READY_MODELS_DIR / "Eletrodomesticos" / f"{nome}.obj",
                READY_MODELS_DIR / "Itens-de-Chao-Loot" / f"{nome}.obj"
            ]
            obj_path = next((c for c in candidatos if c.exists()), None)
            if obj_path:
                renderizar_fallback_matplotlib(obj_path, pasta_out)

    # 2. Assegura o cálculo analítico rigoroso de metadados em Python
    for modelo in MODELOS_CANONICOS:
        nome = modelo["id"]
        pasta_out = INSPECOES_DIR / nome
        candidatos = [
            READY_MODELS_DIR / modelo["categoria"] / f"{nome}.obj",
            READY_MODELS_DIR / "Moveis-e-Caixas" / f"{nome}.obj",
            READY_MODELS_DIR / "Eletrodomesticos" / f"{nome}.obj",
            READY_MODELS_DIR / "Itens-de-Chao-Loot" / f"{nome}.obj"
        ]
        obj_path = next((c for c in candidatos if c.exists()), None)
        if not obj_path:
            continue

        dados_geo = analisar_geometria_obj(obj_path)
        dados_tecnicos_json = pasta_out / "dados-tecnicos.json"

        dados_completos = {
            "objeto": nome,
            "nome_legivel": modelo["nome_legivel"],
            "categoria": modelo["categoria"],
            "descricao": modelo["descricao"],
            "caminho_origem": str(obj_path.relative_to(SUITE_ROOT)).replace("\\", "/"),
            "dimensoes_metros": dados_geo["dimensoes_metros"],
            "volume_delimitador_m3": dados_geo["volume_delimitador_m3"],
            "total_vertices": dados_geo["total_vertices"],
            "total_faces": dados_geo["total_faces"],
            "origem_base_y": dados_geo["origem_base_y"],
            "alinhamento_solo_valido": dados_geo["alinhamento_solo_valido"],
            "vistas_geradas": [
                "isometrica.png",
                "frontal.png",
                "direita.png",
                "superior.png"
            ]
        }

        with open(dados_tecnicos_json, "w", encoding="utf-8") as f:
            json.dump(dados_completos, f, indent=2, ensure_ascii=False)

    # 3. Verificação de integridade
    relatorio = verificar_integridade_inspecoes(MODELOS_CANONICOS)
    print("\n====================================================================")
    print(f"[+] Relatório de Integridade das Inspeções ({relatorio['total_aprovados']}/{relatorio['total_alvos']} íntegros)")
    print("====================================================================")
    for mod_id, res in relatorio["detalhes"].items():
        st = "[OK]" if res["status"] == "INTEGRO" else "[FALHA]"
        print(f"  {st:7} {mod_id.ljust(25)} -> {res['status']}")

    return 0 if relatorio["total_aprovados"] == relatorio["total_alvos"] else 1


def main():
    parser = argparse.ArgumentParser(description="Esteira de Inspeção e Renderização 3D Headless")
    parser.add_argument("--all", action="store_true", help="Processar todos os 7 modelos prontos")
    parser.add_argument("--obj", type=str, help="Caminho para um arquivo .obj específico")
    parser.add_argument("--out", type=str, help="Diretório de saída para a inspeção")

    args = parser.parse_args()

    if args.obj:
        caminho_obj = Path(args.obj).resolve()
        if not caminho_obj.exists():
            print(f"[Erro] Arquivo não encontrado: {caminho_obj}", file=sys.stderr)
            sys.exit(1)
        nome = caminho_obj.stem
        pasta_out = Path(args.out).resolve() if args.out else INSPECOES_DIR / nome
        pasta_out.mkdir(parents=True, exist_ok=True)
        dados = analisar_geometria_obj(caminho_obj)
        with open(pasta_out / "dados-tecnicos.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        renderizar_via_three_playwright()
        sys.exit(0)

    # Padrão: roda a bateria completa
    sys.exit(executar_bateria_completa())


if __name__ == "__main__":
    main()
