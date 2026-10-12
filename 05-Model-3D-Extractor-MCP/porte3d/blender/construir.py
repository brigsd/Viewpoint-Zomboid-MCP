"""Parte do porte3d que roda dentro do Blender (sem janela). Duas etapas (ver CONTRATO.md):

  malha  — lê entrada/receita.json (já expandida), monta as peças, aplica chanfro, junta, faz o UV e assa,
           por texel do atlas: posição, normal, peça, visibilidade da câmera do jogo em 0° e 180°, oclusão
           de ambiente e a cor do material do nível realista. Grava buffers/*.npy, malha.obj, pecas.json e cena.blend.
  vistas — abre cena.blend, aplica arte.png e realista.png (feitas pelo texturas.py) e renderiza as vistas
           na câmera do jogo: arte (cor pura da textura), realista (com luz), fio (wireframe colorido por peça)
           e fio por cima da arte.

Uso: blender -b --factory-startup -P construir.py -- malha <pasta_objeto> [tex]
     blender -b <pasta>/cena.blend -P construir.py -- vistas <pasta_objeto> [escala]
Os buffers são gravados de cima para baixo (linha 0 = topo da imagem, como no PNG).
"""
import colorsys
import json
import math
import os
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from porte3d.blender import materiais  # noqa: E402

AX = "xyz"
D_CAM = Vector((1.0, -1.0, 0.8166)).normalized()      # do objeto para a câmera do jogo (ângulo 0)
ANGULOS = (0, 45, 90, 135, 180, 225, 270, 315)


def log(*a):
    print("[construir]", *a, flush=True)


# ---------------------------------------------------------------- peças

def _objeto(nome, verts, faces, p):
    """Cria o objeto com os vértices recentrados no meio da peça, gira (rot) e aplica o chanfro."""
    v = np.asarray(verts, float)
    c = (v.min(0) + v.max(0)) / 2
    me = bpy.data.meshes.new(nome)
    me.from_pydata([tuple(x) for x in (v - c)], [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(nome, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(c)
    if p.get("rot"):
        ob.rotation_euler = Euler([math.radians(a) for a in p["rot"]], "XYZ")
    if p.get("chanfro", 0) > 0:
        m = ob.modifiers.new("chanfro", "BEVEL")
        m.width, m.segments, m.limit_method = p["chanfro"], 3, "ANGLE"
        m.angle_limit = math.radians(30)
    return ob


def caixa(p):
    lo, hi = p["min"], p["max"]
    v = [[(hi if (i >> k) & 1 else lo)[k] for k in range(3)] for i in range(8)]
    af = p.get("afinar")
    if af:
        for x in v:
            if x[2] == lo[2]:
                for lado in af["lados"]:
                    k, s = AX.index(lado[1]), (1 if lado[0] == "+" else -1)
                    if (x[k] == hi[k]) == (s > 0):
                        x[k] -= s * af["quanto"]
    f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    return _objeto(p["nome"], v, f, p)


def prisma(p):
    pts, n = p["perfil"], len(p["perfil"])
    v = []
    for t in (p["de"], p["ate"]):
        for a, z in pts:
            v.append((a, t, z) if p["eixo"] == "y" else (t, a, z))
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    f += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return _objeto(p["nome"], v, f, p)


def cilindro(p):
    n, h = p["segmentos"], p["altura"]
    r0, r1 = p["raio"], p.get("raio_topo", p["raio"])
    ang = [2 * math.pi * i / n for i in range(n)]
    loc = [(r0 * math.cos(a), r0 * math.sin(a), 0.0) for a in ang] + [(r1 * math.cos(a), r1 * math.sin(a), h) for a in ang]
    e = p["eixo"]
    perm = {"z": lambda x, y, z: (x, y, z), "x": lambda x, y, z: (z, x, y), "y": lambda x, y, z: (y, z, x)}[e]
    cx, cy, cz = p["centro"]
    v = [tuple(a + b for a, b in zip(perm(*q), (cx, cy, cz))) for q in loc]
    f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return _objeto(p["nome"], v, f, p)


def limites(p):
    if p["forma"] == "caixa":
        return np.array(p["min"], float), np.array(p["max"], float)
    if p["forma"] == "prisma":
        a = [q[0] for q in p["perfil"]]
        z = [q[1] for q in p["perfil"]]
        if p["eixo"] == "y":
            return np.array([min(a), p["de"], min(z)]), np.array([max(a), p["ate"], max(z)])
        return np.array([p["de"], min(a), min(z)]), np.array([p["ate"], max(a), max(z)])
    r = max(p["raio"], p.get("raio_topo", 0))
    c = np.array(p["centro"], float)
    k = AX.index(p["eixo"])
    lo, hi = c - r, c + r
    lo[k], hi[k] = c[k], c[k] + p["altura"]
    return lo, hi


def cor_fio(i, n):
    r, g, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.75, 1.0)
    return [int(r * 255), int(g * 255), int(b * 255)]


# ---------------------------------------------------------------- assar

def imagem(nome, tex):
    img = bpy.data.images.get(nome) or bpy.data.images.new(nome, tex, tex, float_buffer=True)
    return img


def assar(ob, tipo, tex, **kw):
    img = imagem(f"assar_{tipo}", tex)
    for slot in ob.material_slots:
        nt = slot.material.node_tree
        n = nt.nodes.get("alvo_assar") or nt.nodes.new("ShaderNodeTexImage")
        n.name = "alvo_assar"
        n.image = img
        nt.nodes.active = n
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.bake(type=tipo, **kw)
    a = np.empty(tex * tex * 4, np.float32)
    img.pixels.foreach_get(a)
    return np.flipud(a.reshape(tex, tex, 4))


def material_simples(nome, cor=(1, 1, 1), emissao=None, forca=1.0):
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*cor, 1)
    if emissao is not None:
        b.inputs["Emission Color"].default_value = (*emissao, 1)
        b.inputs["Emission Strength"].default_value = forca
    return m


def trocar(ob, mats):
    for slot, m in zip(ob.material_slots, mats):
        slot.material = m


def mundo(cor, forca, distancia_ao=0.25):
    w = bpy.context.scene.world or bpy.data.worlds.new("mundo")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*cor, 1)
    bg.inputs["Strength"].default_value = forca
    w.light_settings.distance = distancia_ao


def etapa_malha(pasta: Path, tex: int):
    t0 = time.time()
    r = json.loads((pasta / "entrada" / "receita.json").read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.view_settings.view_transform = "Standard"
    sc.render.bake.margin = 8
    sc.render.bake.margin_type = "EXTEND"

    cores = r.get("cores", {})
    tipos = {k: v["tipo"] for k, v in r.get("realista", {}).get("materiais", {}).items()}
    desgastes = {k: float(v.get("desgaste", 0.0)) for k, v in r.get("realista", {}).get("materiais", {}).items()}
    ferrugens = {k: float(v.get("ferrugem", 0.0)) for k, v in r.get("realista", {}).get("materiais", {}).items()}
    pecas, objs, mats_real, mats_id = [], [], [], []
    for i, p in enumerate(r["pecas"]):
        ob = {"caixa": caixa, "prisma": prisma, "cilindro": cilindro}[p["forma"]](p)
        lo, hi = limites(p)
        tam = hi - lo
        comp = AX.index(p["veio"])
        resto = sorted((k for k in range(3) if k != comp), key=lambda k: -tam[k])
        atr, prof = resto
        mat = p["material"]
        tipo = tipos.get(mat, mat if mat in ("madeira", "metal", "tecido", "liso") else "liso")
        cor = cores.get(mat, [128, 128, 128])
        mr = materiais.criar(f"p{i:03d}_{p['nome']}", tipo, cor, eixos=(AX[comp], AX[atr], AX[prof]),
                             faixa=(float(lo[atr]), float(hi[atr])), superficie=float(hi[prof]),
                             tabuas=int(p.get("tabuas", 0)), semente=i, desgaste=desgastes.get(mat, 0.0), ferrugem=ferrugens.get(mat, 0.0),
                             limites=(tuple(map(float, lo)), tuple(map(float, hi))))
        ob.data.materials.append(mr)
        mats_real.append(mr)
        mats_id.append(material_simples(f"id{i:03d}", (0, 0, 0), emissao=(1.0, 1.0, 1.0), forca=float(i + 1)))
        objs.append(ob)
        pecas.append({"indice": i, "nome": p["nome"], "cor_fio": cor_fio(i, len(r["pecas"]))})

    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = r["id"]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    # as cópias espelhadas viram slots na mesma ordem das peças? garante pela ordem dos nomes
    ordem = {m.name: k for k, m in enumerate(mats_real)}
    slots = [s.material.name for s in ob.material_slots]
    assert sorted(ordem[n] for n in slots) == list(range(len(pecas))), slots
    perm = [ordem[n] for n in slots]                 # slot -> índice da peça
    mats_real = [mats_real[k] for k in perm]
    mats_id = [mats_id[k] for k in perm]

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.006, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    log(f"malha: {len(ob.data.polygons)} faces, {len(pecas)} peças ({time.time() - t0:.1f}s)")

    buf = pasta / "buffers"
    buf.mkdir(parents=True, exist_ok=True)
    branco = material_simples("branco", (1, 1, 1))

    # dados geométricos (1 amostra basta)
    sc.cycles.samples = 1
    mundo((0, 0, 0), 0.0)
    trocar(ob, [branco] * len(perm))
    np.save(buf / "posicao.npy", assar(ob, "POSITION", tex)[..., :3])
    sc.render.bake.normal_space = "OBJECT"
    nrm = assar(ob, "NORMAL", tex)[..., :3] * 2 - 1
    np.save(buf / "normal.npy", nrm.astype(np.float32))
    trocar(ob, mats_id)
    idx = assar(ob, "EMIT", tex)[..., 0]
    np.save(buf / "peca.npy", (np.rint(idx) - 1).astype(np.int16))

    # visibilidade da câmera do jogo: sol vindo da câmera, só luz direta sobre material branco
    trocar(ob, [branco] * len(perm))
    sc.cycles.samples = 4
    sol = bpy.data.objects.new("sol_vis", bpy.data.lights.new("sol_vis", "SUN"))
    sol.data.energy, sol.data.angle = 1.0, 0.0
    sc.collection.objects.link(sol)
    for ang in (0, 180):
        d = D_CAM.copy()
        d.rotate(Euler((0, 0, -math.radians(ang))))     # câmera vista do referencial do objeto girado
        sol.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        v = assar(ob, "DIFFUSE", tex, pass_filter={"DIRECT"})[..., 0]
        np.save(buf / f"vis_{ang}.npy", (v / max(float(v.max()), 1e-6)).astype(np.float32))
    bpy.data.objects.remove(sol)

    # oclusão de ambiente, com o chão
    chao_me = bpy.data.meshes.new("chao")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3)
    bm.to_mesh(chao_me)
    bm.free()
    chao = bpy.data.objects.new("chao", chao_me)
    sc.collection.objects.link(chao)
    mundo((1, 1, 1), 1.0)
    sc.cycles.samples = 128
    np.save(buf / "ao.npy", assar(ob, "AO", tex)[..., 0])
    bpy.data.objects.remove(chao)

    # cor do material do nível realista
    trocar(ob, mats_real)
    sc.cycles.samples = 16
    np.save(buf / "albedo.npy", assar(ob, "DIFFUSE", tex, pass_filter={"COLOR"})[..., :3])
    # o índice de peça foi gravado pelo id do material, não pelo slot; registra a ordem dos slots
    (pasta / "pecas.json").write_text(json.dumps(pecas, ensure_ascii=False, indent=1), encoding="utf-8")

    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.wm.obj_export(filepath=str(pasta / "malha.obj"), export_selected_objects=True, export_uv=True,
                          export_normals=True, export_materials=True, path_mode="STRIP",
                          forward_axis="NEGATIVE_Z", up_axis="Y")
    for img in list(bpy.data.images):
        if img.name.startswith("assar_"):
            bpy.data.images.remove(img)
    bpy.ops.wm.save_as_mainfile(filepath=str(pasta / "cena.blend"))
    log(f"etapa malha pronta em {time.time() - t0:.1f}s")


# ---------------------------------------------------------------- vistas

def material_textura(nome, png, luz):
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = bpy.data.images.load(str(png))
    b = nt.nodes["Principled BSDF"]
    if luz:
        b.inputs["Roughness"].default_value = 0.7
        nt.links.new(tn.outputs["Color"], b.inputs["Base Color"])
    else:                               # cor pura da textura (o desenho do jogo já traz a luz pintada)
        b.inputs["Base Color"].default_value = (0, 0, 0, 1)
        b.inputs["Specular IOR Level"].default_value = 0.0
        b.inputs["Emission Strength"].default_value = 1.0
        nt.links.new(tn.outputs["Color"], b.inputs["Emission Color"])
    return m


def etapa_vistas(pasta: Path, escala: int):
    t0 = time.time()
    sc = bpy.context.scene
    pecas = json.loads((pasta / "pecas.json").read_text(encoding="utf-8"))
    ob = next(o for o in sc.objects if o.type == "MESH")
    sc.render.engine = "CYCLES"
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 128 * escala, 256 * escala
    mundo((0.45, 0.45, 0.48), 0.78)
    sol = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN"))
    sol.data.energy, sol.data.angle = 2.6, math.radians(8)
    sc.collection.objects.link(sol)
    sol.rotation_euler = Vector((-0.6, -1.0, 1.6)).to_track_quat("Z", "Y").to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 2 * math.sqrt(2)
    sc.collection.objects.link(cam)
    sc.camera = cam
    alvo = Vector((0, 0, 96 / 78.38))          # o centro do quadro 128x256 (o tile fica em 64,224)
    cam.location = alvo + D_CAM * 10
    cam.rotation_euler = (-D_CAM).to_track_quat("-Z", "Y").to_euler()

    # fio: cópia com wireframe, um material por peça na cor da legenda
    fio = ob.copy()
    fio.data = ob.data.copy()
    sc.collection.objects.link(fio)
    m = fio.modifiers.new("fio", "WIREFRAME")
    m.thickness, m.use_replace = 0.002, True
    por_nome = {f"p{q['indice']:03d}_{q['nome']}": q for q in pecas}
    for slot in fio.material_slots:
        q = por_nome[slot.material.name]
        c = [v / 255 for v in q["cor_fio"]]
        slot.material = material_simples(f"fio_{q['indice']}", (0, 0, 0), emissao=c)
        slot.material.diffuse_color = (*c, 1)            # cor que o Workbench mostra

    vistas = pasta / "vistas"
    vistas.mkdir(exist_ok=True)

    # sem luz (arte e fio): Workbench com luz chapada, que mostra a cor da textura como ela é e é rápido;
    # com luz (realista): Cycles
    sc.display.shading.light = "FLAT"
    sc.display.shading.color_type = "TEXTURE"
    sc.display.render_aa = "8"

    def rodar(nome, objetos, amostras, luz):
        sc.render.engine = "CYCLES" if luz else "BLENDER_WORKBENCH"
        sc.cycles.samples = amostras
        for o in (ob, fio):
            o.hide_render = o not in objetos
        for a in ANGULOS:
            for o in objetos:
                o.rotation_euler = (0, 0, math.radians(a))
            sc.render.filepath = str(vistas / f"{nome}_{a:03d}.png")
            bpy.ops.render.render(write_still=True)

    for nivel, luz in (("arte", False), ("realista", True)):
        png = pasta / f"{nivel}.png"
        if not png.exists():
            continue
        trocar(ob, [material_textura(nivel, png, luz)] * len(ob.material_slots))
        rodar(nivel, [ob], 24, luz)
        if nivel == "arte":
            rodar("fio_sobre_arte", [ob, fio], 1, False)
    rodar("fio", [fio], 1, False)
    log(f"vistas prontas em {time.time() - t0:.1f}s")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    etapa, pasta = args[0], Path(args[1]).resolve()
    if etapa == "malha":
        etapa_malha(pasta, int(args[2]) if len(args) > 2 else 2048)
    elif etapa == "vistas":
        etapa_vistas(pasta, int(args[2]) if len(args) > 2 else 4)
    else:
        raise SystemExit(f"etapa desconhecida: {etapa}")
