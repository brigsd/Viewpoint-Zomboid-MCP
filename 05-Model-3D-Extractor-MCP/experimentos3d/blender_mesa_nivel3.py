"""Nível 3 ("esculpido") da mesa, feito no Blender sem janela:
  - geometria com detalhe: tampo fino com borda arredondada, saia recuada, cantoneiras, pés afinando para baixo;
  - madeira procedural nas cores tiradas da arte do jogo;
  - luz embutida na textura: cor da madeira x oclusão de ambiente (cantos e encontros mais escuros);
  - exporta OBJ + MTL + PNG (só map_Kd, que é o que o Viewpoint lê) e renderiza vistas na câmera do jogo.

Uso: blender -b --factory-startup -P blender_mesa_nivel3.py -- <params.json>
Coordenadas: 1 unidade = 1 tile = 1 m; Blender (x, y, z) = jogo (X, -Z, Y).
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

P = json.load(open(sys.argv[sys.argv.index("--") + 1]))
OUT = P["out"]
os.makedirs(OUT, exist_ok=True)
TEX = P.get("tex", 2048)


def lin(c):
    c = np.asarray(c, float) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 64
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"

# ---------------------------------------------------------------- geometria
LEG_C, LEG_H, TAPER = 0.40, 0.04, 0.012          # centro dos pés, meia largura, quanto afina embaixo (lado de dentro)
TOP_HALF, TOP_LO, TOP_HI = 0.49, 0.68, 0.72     # tampo de 4 cm
APR_LO, APR_HI, APR_IN, APR_T = 0.565, 0.68, 0.006, 0.022   # saia: altura, recuo da face do pé, espessura
BRK = 0.05                                       # cantoneira (triângulo) sob a saia


def box(name, lo, hi, bevel, mat):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    lo, hi = Vector(lo), Vector(hi)
    for v in bm.verts:
        v.co = Vector(((lo[i] + hi[i]) / 2 + v.co[i] * (hi[i] - lo[i]) for i in range(3)))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    if bevel:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method = bevel, 3, "ANGLE"
    return ob


def prism(name, pts2d, axis, t0, t1, mat):
    """Prisma de seção triangular: pts2d no plano (eixo horizontal da saia, z), extrudado em `axis` de t0 a t1."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = []
    for t in (t0, t1):
        for a, z in pts2d:
            co = (a, t, z) if axis == "y" else (t, a, z)
            vs.append(bm.verts.new(co))
    n = len(pts2d)
    bm.faces.new(vs[:n])
    bm.faces.new(vs[n:][::-1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((vs[i], vs[j], vs[n + j], vs[n + i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    m = ob.modifiers.new("bevel", "BEVEL")
    m.width, m.segments, m.limit_method = 0.002, 2, "ANGLE"
    return ob


# ---------------------------------------------------------------- materiais (madeira procedural)
AX = {"x": 0, "y": 1, "z": 2}


def wood(name, rgb, length, across, depth, planks=0, plank_len=0.98, surf=0.72, seed=0.0, spacing=0.0055):
    """Madeira com anéis de crescimento de verdade: cada tábua tem o próprio centro de tronco (sorteado),
    inclinação, espaçamento de anel e tom — então nenhuma tábua repete a outra. Os anéis viram linhas finas
    escuras (lenho tardio) sobre fundo claro, e não listras de seno."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.65
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    Lk.new(tc.outputs["Object"], sep.inputs["Vector"])

    def M(op, a, b=None, c=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                Lk.new(v, n.inputs[i])
        return n.outputs[0]

    pl, pa, pb = (sep.outputs[AX[k]] for k in (length, across, depth))
    if planks:
        idx = M("FLOOR", M("MULTIPLY_ADD", pa, planks / plank_len, planks / 2))
    else:
        idx = M("ADD", 0.0, 0.0)
    rnd = []
    for k in range(2):                                   # 6 números sorteados por tábua
        wn = N.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "1D"
        Lk.new(M("ADD", idx, seed * 13.7 + k * 0.37), wn.inputs["W"])
        sc = N.new("ShaderNodeSeparateColor")
        Lk.new(wn.outputs["Color"], sc.inputs["Color"])
        rnd += [sc.outputs[i] for i in range(3)]
    r0, r1, r2, r3, r4, r5 = rnd
    w = plank_len / planks if planks else 0.6
    # centro do tronco: ao lado da tábua (às vezes dentro dela -> arcos "catedral"), um pouco inclinado
    base_a = M("MULTIPLY", M("SUBTRACT", M("ADD", idx, 0.5), planks / 2), w) if planks else 0.0
    ca = M("ADD", M("ADD", base_a, M("MULTIPLY", M("SUBTRACT", r0, 0.5), w * 1.6)),
           M("MULTIPLY", pl, M("MULTIPLY", M("SUBTRACT", r1, 0.5), 0.05)))
    cb = M("ADD", M("SUBTRACT", surf, M("MULTIPLY_ADD", r2, 0.22, 0.02)),
           M("MULTIPLY", pl, M("MULTIPLY", M("SUBTRACT", r3, 0.5), 0.12)))
    da, db = M("SUBTRACT", pa, ca), M("SUBTRACT", pb, cb)
    dist = M("SQRT", M("ADD", M("MULTIPLY", da, da), M("MULTIPLY", db, db)))
    # anéis levemente tortos (ruído lento ao longo do comprimento)
    mpn = N.new("ShaderNodeMapping")
    sc_v = [6.0, 6.0, 6.0]; sc_v[AX[length]] = 1.2
    mpn.inputs["Scale"].default_value = sc_v
    Lk.new(tc.outputs["Object"], mpn.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.0; nz.inputs["Detail"].default_value = 3.0
    Lk.new(mpn.outputs["Vector"], nz.inputs["Vector"])
    dist = M("ADD", dist, M("MULTIPLY", M("SUBTRACT", nz.outputs["Fac"], 0.5), 0.012))
    sp = M("MULTIPLY_ADD", r4, spacing * 0.6, spacing * 0.7)
    rings = M("FRACT", M("DIVIDE", dist, sp))
    ramp = N.new("ShaderNodeValToRGB")
    base = lin(rgb)
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*(base * 1.06), 1)
    els[1].position, els[1].color = 1.0, (*(base * 1.04), 1)
    for pos, f in ((0.55, 1.0), (0.80, 0.80), (0.88, 0.70)):
        e = els.new(pos); e.color = (*(base * f), 1)
    Lk.new(rings, ramp.inputs["Fac"])
    col = ramp.outputs["Color"]

    def mult(col, fac):
        mm = N.new("ShaderNodeMix"); mm.data_type = "RGBA"; mm.blend_type = "MULTIPLY"
        mm.inputs["Factor"].default_value = 1.0
        Lk.new(col, mm.inputs["A"])
        if isinstance(fac, float):
            mm.inputs["B"].default_value = (fac, fac, fac, 1)
        else:
            Lk.new(fac, mm.inputs["B"])
        return mm.outputs["Result"]

    def rng(v, lo, hi, fmin=0.0, fmax=1.0):
        mr = N.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = fmin, fmax
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = lo, hi
        Lk.new(v, mr.inputs["Value"])
        return mr.outputs["Result"]

    # poros/fibras: ruído fino esticado no comprimento
    mpf = N.new("ShaderNodeMapping")
    sf = [140.0, 140.0, 140.0]; sf[AX[length]] = 3.0
    mpf.inputs["Scale"].default_value = sf
    Lk.new(tc.outputs["Object"], mpf.inputs["Vector"])
    fib = N.new("ShaderNodeTexNoise"); fib.inputs["Scale"].default_value = 1.0; fib.inputs["Detail"].default_value = 2.0
    Lk.new(mpf.outputs["Vector"], fib.inputs["Vector"])
    col = mult(col, rng(fib.outputs["Fac"], 0.90, 1.07, 0.3, 0.7))
    col = mult(col, rng(r5, 0.88, 1.08))                  # tom próprio de cada tábua
    if planks:                                           # junta entre tábuas
        fr = M("PINGPONG", M("MULTIPLY_ADD", pa, planks / plank_len, planks / 2), 0.5)
        col = mult(col, rng(fr, 0.4, 1.0, 0.0, 0.015))
    big = N.new("ShaderNodeTexNoise"); big.inputs["Scale"].default_value = 3.0
    Lk.new(tc.outputs["Object"], big.inputs["Vector"])
    col = mult(col, rng(big.outputs["Fac"], 0.92, 1.06, 0.3, 0.7))   # manchas de uso
    Lk.new(col, bsdf.inputs["Base Color"])
    return mat


top_rgb, side_rgb = P["tampo"], P["pe"]
m_top = wood("tampo", top_rgb, "x", "y", "z", planks=3, surf=TOP_HI, seed=1)
m_leg = wood("pe", side_rgb, "z", "x", "y", surf=0.9, seed=2)
m_ax = wood("saia_x", side_rgb, "x", "z", "y", surf=1.0, seed=3)
m_ay = wood("saia_y", side_rgb, "y", "z", "x", surf=1.0, seed=4)

parts = [box("tampo", (-TOP_HALF, -TOP_HALF, TOP_LO), (TOP_HALF, TOP_HALF, TOP_HI), 0.008, m_top)]
for sx in (-1, 1):
    for sy in (-1, 1):
        lg = box(f"pe_{sx}_{sy}", (sx * LEG_C - LEG_H, sy * LEG_C - LEG_H, 0), (sx * LEG_C + LEG_H, sy * LEG_C + LEG_H, TOP_LO), 0, m_leg)
        for v in lg.data.vertices:              # afina só pelos lados de dentro
            if v.co.z < 0.01:
                if abs(v.co.x) < LEG_C:
                    v.co.x += sx * TAPER
                if abs(v.co.y) < LEG_C:
                    v.co.y += sy * TAPER
        m = lg.modifiers.new("bevel", "BEVEL"); m.width, m.segments, m.limit_method = 0.004, 3, "ANGLE"
        parts.append(lg)
o_out = LEG_C + LEG_H - APR_IN
inner = LEG_C - LEG_H + 0.005
for s in (-1, 1):
    parts.append(box(f"saia_x{s}", (-inner, s * o_out - (APR_T if s > 0 else 0), APR_LO), (inner, s * o_out + (0 if s > 0 else APR_T), APR_HI), 0.003, m_ax))
    parts.append(box(f"saia_y{s}", (s * o_out - (APR_T if s > 0 else 0), -inner, APR_LO), (s * o_out + (0 if s > 0 else APR_T), inner, APR_HI), 0.003, m_ay))
    e = LEG_C - LEG_H
    for c in (-1, 1):
        tri = [(c * e, APR_LO), (c * (e - BRK), APR_LO), (c * e, APR_LO - BRK)]
        y0, y1 = sorted((s * o_out, s * (o_out - APR_T)))
        parts.append(prism(f"cant_x{s}{c}", tri, "y", y0, y1, m_ax))
        parts.append(prism(f"cant_y{s}{c}", tri, "x", y0, y1, m_ay))

# junta tudo num objeto só (o Viewpoint carrega um OBJ por modelo)
for ob in parts:
    ob.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.convert(target="MESH")             # aplica os chanfros
bpy.ops.object.join()
mesa = bpy.context.view_layer.objects.active
mesa.name = "mesa_n3"
bpy.ops.object.shade_auto_smooth(angle=math.radians(35))

bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, scale_to_bounds=True)
bpy.ops.object.mode_set(mode="OBJECT")

# ---------------------------------------------------------------- assar cor e oclusão na textura
floor_me = bpy.data.meshes.new("chao")
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3); bm.to_mesh(floor_me); bm.free()
floor = bpy.data.objects.new("chao", floor_me)
scene.collection.objects.link(floor)
world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
world.light_settings.distance = 0.25


def bake(kind, **kw):
    img = bpy.data.images.new(f"bake_{kind}", TEX, TEX, float_buffer=True)
    for mat in mesa.data.materials:
        n = mat.node_tree.nodes.new("ShaderNodeTexImage")
        n.image = img
        mat.node_tree.nodes.active = n
    bpy.ops.object.select_all(action="DESELECT")
    mesa.select_set(True)
    bpy.context.view_layer.objects.active = mesa
    scene.render.bake.margin = 12
    bpy.ops.object.bake(type=kind, **kw)
    a = np.empty(TEX * TEX * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(TEX, TEX, 4)


scene.cycles.samples = 16
albedo = bake("DIFFUSE", pass_filter={"COLOR"})
scene.cycles.samples = 128
ao = bake("AO")[..., :1]
final = albedo[..., :3] * (0.30 + 0.70 * ao ** 0.9)
out = np.dstack([to_srgb(final), np.ones((TEX, TEX, 1))]).astype(np.float32)
png = bpy.data.images.new("mesa_n3", TEX, TEX, alpha=False)
png.pixels.foreach_set(out.ravel())
png.filepath_raw = os.path.join(OUT, "mesa_n3.png")
png.file_format = "PNG"
png.save()
bpy.data.objects.remove(floor)

# troca para um material só com a textura assada (o que o jogo vai ver)
tex = bpy.data.images.load(os.path.join(OUT, "mesa_n3.png"))
mfin = bpy.data.materials.new("mesa_n3")
mfin.use_nodes = True
tn = mfin.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = tex
b = mfin.node_tree.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.7
mfin.node_tree.links.new(tn.outputs["Color"], b.inputs["Base Color"])
mesa.data.materials.clear()
mesa.data.materials.append(mfin)
for p in mesa.data.polygons:
    p.material_index = 0

bpy.ops.object.select_all(action="DESELECT")
mesa.select_set(True)
bpy.ops.wm.obj_export(filepath=os.path.join(OUT, "mesa_n3.obj"), export_selected_objects=True, export_uv=True,
                      export_normals=True, export_materials=True, path_mode="STRIP", forward_axis="NEGATIVE_Z", up_axis="Y")

# ---------------------------------------------------------------- vistas na câmera do jogo
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.45, 0.48, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = P.get("ambiente", 0.9)
sun = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN"))
sun.data.energy = P.get("sol", 3.0)
sun.data.angle = math.radians(8)
scene.collection.objects.link(sun)
sun.rotation_euler = Vector((-0.6, -1.0, 1.6)).to_track_quat("Z", "Y").to_euler()   # luz de cima, pela face esquerda

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type, cam.data.ortho_scale = "ORTHO", 2 * math.sqrt(2)    # 128x256 px do jogo = 1,414 x 2,828 m
scene.collection.objects.link(cam)
scene.camera = cam
target = Vector((0, 0, 96 / 78.38))           # ponto que cai no centro do quadro 128x256 (o tile fica em 64,224)
d = Vector((1, -1, 0.8166)).normalized()
cam.location = target + d * 10
cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
scene.render.resolution_x, scene.render.resolution_y = 128 * P.get("scale", 4), 256 * P.get("scale", 4)
scene.cycles.samples = 48
scene.cycles.use_denoising = True


def shot(angle, path):
    mesa.rotation_euler = (0, 0, -math.radians(angle))
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


for a in P.get("angles", (0, 60, 180)):
    shot(a, os.path.join(OUT, f"vista_{a:03d}.png"))

# wireframe (vista do crítico)
wf = mesa.copy(); wf.data = mesa.data.copy(); scene.collection.objects.link(wf)
mw = wf.modifiers.new("wf", "WIREFRAME"); mw.thickness = 0.0025; mw.use_replace = True
em = bpy.data.materials.new("fio"); em.use_nodes = True
em.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.3, 1.0, 0.4, 1)
em.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
wf.data.materials.clear(); wf.data.materials.append(em)
mesa.hide_render = True
for a in (0, 60):
    wf.rotation_euler = (0, 0, -math.radians(a))
    scene.render.filepath = os.path.join(OUT, f"wire_{a:03d}.png")
    bpy.ops.render.render(write_still=True)
wf.hide_render, mesa.hide_render = True, False

if P.get("turntable"):
    scene.render.resolution_x, scene.render.resolution_y = 128 * 3, 256 * 3
    scene.cycles.samples = 24
    for k in range(36):
        shot(k * 10, os.path.join(OUT, "giro", f"{k:02d}.png"))
print("faces:", len(mesa.data.polygons), "vertices:", len(mesa.data.vertices))
