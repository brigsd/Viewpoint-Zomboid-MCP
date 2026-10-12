"""Amostra dos materiais procedurais do porte 3D, sem janela:
  - monta alguns objetos de teste (geladeira de metal pintado, aço escovado, sofá de tecido, mesa de madeira,
    caixa lisa);
  - assa COR BASE + oclusão de ambiente numa textura por objeto (Smart UV Project; albedo x (0,30 + 0,70*ao^0,9)),
    como o nível 3 da mesa;
  - renderiza na câmera do jogo e num close-up em perspectiva a ~0,6 m, e monta folhas lado a lado.

Uso: blender -b --factory-startup -P amostra_materiais.py -- [objeto ...] [--tex N] [--saida PASTA] [--so-folha]
Objetos: geladeira, inox, sofa, mesa, liso (padrão: todos). Sai em acervo/data/exp/porte3d_materiais/.
"""
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import materiais  # noqa: E402

RAIZ = os.path.abspath(os.path.join(AQUI, "..", ".."))            # 05-Model-3D-Extractor-MCP
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAIDA = os.path.join(RAIZ, "acervo", "data", "exp", "porte3d_materiais")
TEX_FORCADO = None
SO_FOLHA = False
nomes = []
i = 0
while i < len(args):
    if args[i] == "--tex":
        TEX_FORCADO = int(args[i + 1]); i += 2
    elif args[i] == "--so-folha":          # só remonta as folhas a partir dos PNGs já renderizados
        SO_FOLHA = True; i += 1
    elif args[i] == "--saida":
        SAIDA = args[i + 1]; i += 2
    else:
        nomes.append(args[i]); i += 1
os.makedirs(SAIDA, exist_ok=True)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def caixa(scene, nome, lo, hi, mat, chanfro=0.0, seg=3):
    me = bpy.data.meshes.new(nome)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    lo, hi = Vector(lo), Vector(hi)
    for v in bm.verts:
        v.co = Vector(((lo[k] + hi[k]) / 2 + v.co[k] * (hi[k] - lo[k]) for k in range(3)))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(nome, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    if chanfro:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method = chanfro, seg, "ANGLE"
    return ob


# ------------------------------------------------------------------ definição dos objetos de teste
# cada um devolve (partes, tex, closeups); closeups = [(rótulo, alvo, direção da câmera)]
def obj_geladeira(scene):
    m = materiais.criar("geladeira", "metal", (230, 230, 225), eixos=("z", "x", "y"), semente=1)
    p = [caixa(scene, "corpo", (-0.45, -0.35, 0.02), (0.45, 0.35, 1.6), m, 0.012),
         caixa(scene, "base", (-0.43, -0.33, 0.0), (0.43, 0.33, 0.03), m, 0.004)]
    return p, 4096, [("frente_baixo", (0.0, -0.35, 0.22), (0.0, -1.0, 0.12)),
                     ("lado", (0.45, 0.0, 0.5), (1.0, 0.0, 0.12))]


def obj_inox(scene):
    m = materiais.criar("inox", "metal", (150, 152, 155), eixos=("x", "y", "z"), semente=2)
    p = [caixa(scene, "corpo", (-0.30, -0.30, 0.0), (0.30, 0.30, 0.9), m, 0.006)]
    return p, 2048, [("frente", (0.0, -0.30, 0.45), (0.0, -1.0, 0.1)),
                     ("topo", (0.0, 0.0, 0.9), (0.15, -0.35, 1.0))]


def obj_sofa(scene):
    m = materiais.criar("sofa", "tecido", (120, 70, 60), eixos=("x", "y", "z"), semente=3)
    p = [caixa(scene, "assento", (-0.80, -0.40, 0.12), (0.80, 0.40, 0.45), m, 0.05, 4),
         caixa(scene, "encosto", (-0.80, 0.20, 0.12), (0.80, 0.45, 0.85), m, 0.05, 4),
         caixa(scene, "braco_e", (-0.90, -0.40, 0.12), (-0.78, 0.45, 0.62), m, 0.04, 4),
         caixa(scene, "braco_d", (0.78, -0.40, 0.12), (0.90, 0.45, 0.62), m, 0.04, 4),
         caixa(scene, "base", (-0.88, -0.38, 0.0), (0.88, 0.43, 0.14), m, 0.01)]
    return p, 4096, [("assento", (0.0, -0.40, 0.30), (0.0, -1.0, 0.45)),
                     ("braco", (0.84, -0.1, 0.62), (0.7, -0.5, 0.9))]


def obj_mesa(scene):
    tampo = materiais.criar("tampo", "madeira", (88, 82, 78), eixos=("x", "y", "z"), faixa=(-0.45, 0.45),
                            superficie=0.72, tabuas=3, semente=1)
    p = [caixa(scene, "tampo", (-0.50, -0.45, 0.68), (0.50, 0.45, 0.72), tampo, 0.004)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * 0.42, sy * 0.37        # um material por pé (faixa = a própria peça; semente diferente)
            pe = materiais.criar(f"pe{sx}{sy}", "madeira", (88, 82, 78), eixos=("z", "x", "y"),
                                 faixa=(cx - 0.04, cx + 0.04), superficie=cy + 0.04 * (1 if sy > 0 else -1),
                                 lado=(1 if sy > 0 else -1), tabuas=0, semente=10 + sx + 2 * sy)
            p.append(caixa(scene, f"pe{sx}{sy}", (sx * 0.42 - 0.04, sy * 0.37 - 0.04, 0.0),
                           (sx * 0.42 + 0.04, sy * 0.37 + 0.04, 0.68), pe, 0.003))
    return p, 4096, [("tampo", (0.0, 0.0, 0.72), (0.0, -0.45, 1.0)),
                     ("pe", (0.42, -0.37, 0.35), (1.0, -1.0, 0.25))]


def obj_liso(scene):
    m = materiais.criar("liso", "liso", (90, 140, 170), semente=4)
    p = [caixa(scene, "caixa", (-0.25, -0.25, 0.0), (0.25, 0.25, 0.5), m, 0.01)]
    return p, 2048, [("frente", (0.0, -0.25, 0.25), (0.0, -1.0, 0.15))]


OBJETOS = {"geladeira": obj_geladeira, "inox": obj_inox, "sofa": obj_sofa, "mesa": obj_mesa, "liso": obj_liso}


# ------------------------------------------------------------------ bake + render
def processar(nome):
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    partes, tex, closeups = OBJETOS[nome](scene)
    TEX = TEX_FORCADO or tex
    t_mat = time.time() - t0

    for ob in partes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = partes[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = nome
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")

    # densidade de texels: área da malha x fração de UV usada
    area = sum(p.area for p in obj.data.polygons)
    uv = obj.data.uv_layers.active.data
    area_uv = 0.0
    for p in obj.data.polygons:
        pts = [uv[k].uv for k in p.loop_indices]
        area_uv += 0.5 * abs(sum(pts[k].x * pts[(k + 1) % len(pts)].y - pts[(k + 1) % len(pts)].x * pts[k].y
                                 for k in range(len(pts))))
    dens = math.sqrt(area_uv * TEX * TEX / area) / 1000.0     # texels por mm

    # chão e mundo para a oclusão
    fm = bpy.data.meshes.new("chao")
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3); bm.to_mesh(fm); bm.free()
    chao = bpy.data.objects.new("chao", fm)
    scene.collection.objects.link(chao)
    world = bpy.data.worlds.new("w"); scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.light_settings.distance = 0.25

    def assar(kind, **kw):
        img = bpy.data.images.new(f"bake_{kind}", TEX, TEX, float_buffer=True)
        for mat in obj.data.materials:
            n = mat.node_tree.nodes.new("ShaderNodeTexImage")
            n.image = img
            mat.node_tree.nodes.active = n
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        scene.render.bake.margin = 16
        bpy.ops.object.bake(type=kind, **kw)
        a = np.empty(TEX * TEX * 4, np.float32)
        img.pixels.foreach_get(a)
        return a.reshape(TEX, TEX, 4)

    t1 = time.time()
    scene.cycles.samples = 16
    albedo = assar("DIFFUSE", pass_filter={"COLOR"})
    t_alb = time.time() - t1
    t1 = time.time()
    scene.cycles.samples = 32
    ao = assar("AO")[..., :1]
    t_ao = time.time() - t1
    final = albedo[..., :3] * (0.30 + 0.70 * ao ** 0.9)
    # cor média do albedo (só texels cobertos pelas ilhas de UV)
    mascara = ao[..., 0] > 0
    media = to_srgb(albedo[..., :3][mascara].mean(axis=0)) * 255
    out = np.dstack([to_srgb(final), np.ones((TEX, TEX, 1))]).astype(np.float32)
    png = bpy.data.images.new(nome, TEX, TEX, alpha=False)
    png.pixels.foreach_set(out.ravel())
    caminho_tex = os.path.join(SAIDA, f"{nome}_tex.png")
    png.filepath_raw = caminho_tex
    png.file_format = "PNG"
    png.save()
    bpy.data.objects.remove(chao)

    tex_img = bpy.data.images.load(caminho_tex)
    mfin = bpy.data.materials.new(nome + "_final")
    mfin.use_nodes = True
    tn = mfin.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = tex_img
    b = mfin.node_tree.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.7
    mfin.node_tree.links.new(tn.outputs["Color"], b.inputs["Base Color"])
    obj.data.materials.clear()
    obj.data.materials.append(mfin)
    for p in obj.data.polygons:
        p.material_index = 0

    # ---- luz e câmeras (as mesmas da mesa)
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.45, 0.48, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    sun = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN"))
    sun.data.energy = 3.0
    sun.data.angle = math.radians(8)
    scene.collection.objects.link(sun)
    sun.rotation_euler = Vector((-0.6, -1.0, 1.6)).to_track_quat("Z", "Y").to_euler()
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True

    t1 = time.time()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 2 * math.sqrt(2)
    scene.collection.objects.link(cam)
    scene.camera = cam
    target = Vector((0, 0, 96 / 78.38))
    d = Vector((1, -1, 0.8166)).normalized()
    cam.location = target + d * 10
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x, scene.render.resolution_y = 128 * 4, 256 * 4
    scene.render.filepath = os.path.join(SAIDA, f"{nome}_jogo.png")
    bpy.ops.render.render(write_still=True)

    # close-ups: perspectiva a ~0,6 m
    cam.data.type, cam.data.lens, cam.data.sensor_width = "PERSP", 50, 36
    scene.render.resolution_x, scene.render.resolution_y = 1200, 800
    sun.data.energy = 2.0
    scene.cycles.samples = 32
    for rot, alvo, direc in closeups:
        dd = Vector(direc).normalized()
        cam.location = Vector(alvo) + dd * 0.6
        cam.rotation_euler = (-dd).to_track_quat("-Z", "Y").to_euler()
        # luz do lado da câmera (um pouco acima e de lado), para a face fotografada receber sol
        lado = dd.cross(Vector((0, 0, 1)))
        lado = lado.normalized() if lado.length > 1e-3 else Vector((1, 0, 0))
        ld = (dd + Vector((0, 0, 0.7)) + lado * 0.5).normalized()
        sun.rotation_euler = (-ld).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(SAIDA, f"{nome}_perto_{rot}.png")
        bpy.ops.render.render(write_still=True)
    t_ren = time.time() - t1
    print(f"[tempo] {nome}: nós {t_mat:.1f}s | bake cor {t_alb:.1f}s | bake AO {t_ao:.1f}s | render {t_ren:.1f}s | "
          f"textura {TEX} px, {dens:.2f} texel/mm | cor média albedo sRGB {media.round(0).tolist()}")
    return [r for r, _, _ in closeups]


def carregar(caminho):
    img = bpy.data.images.load(caminho)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1]          # origem no topo


def salvar_folha(caminho, quadro):
    h, w = quadro.shape[:2]
    img = bpy.data.images.new("folha", w, h, alpha=True)
    rgba = np.dstack([quadro, np.ones((h, w, 1))])[::-1].astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = caminho
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def sobre_fundo(a, fundo=0.62):
    al = a[..., 3:4]
    return a[..., :3] * al + fundo * (1 - al)      # os PNGs de render ja estão em sRGB (Standard)


def montar(feitos):
    # folha 1: vistas do jogo lado a lado
    jogo = [sobre_fundo(carregar(os.path.join(SAIDA, f"{n}_jogo.png")), 0.5) for n in feitos]
    salvar_folha(os.path.join(SAIDA, "folha_jogo.png"), np.concatenate(jogo, axis=1))
    # folha 2: close-ups (1 por objeto) em grade
    perto = []
    for n, rots in feitos.items():
        for r in rots:
            q = carregar(os.path.join(SAIDA, f"{n}_perto_{r}.png"))
            perto.append(sobre_fundo(q, 0.5)[::2, ::2])
    cols = 2
    while len(perto) % cols:
        perto.append(np.full_like(perto[0], 0.5))
    linhas = [np.concatenate(perto[k:k + cols], axis=1) for k in range(0, len(perto), cols)]
    salvar_folha(os.path.join(SAIDA, "folha_perto.png"), np.concatenate(linhas, axis=0))


T0 = time.time()
feitos = {}
if SO_FOLHA:
    import glob
    for n in (nomes or list(OBJETOS)):
        feitos[n] = [os.path.basename(f)[len(n) + 7:-4] for f in sorted(glob.glob(os.path.join(SAIDA, f"{n}_perto_*.png")))]
else:
    for n in (nomes or list(OBJETOS)):
        feitos[n] = processar(n)
montar(feitos)
print(f"[tempo] total {time.time() - T0:.1f}s; saída em {SAIDA}")
