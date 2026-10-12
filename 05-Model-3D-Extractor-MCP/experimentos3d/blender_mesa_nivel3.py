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
def wood(name, rgb, grain_axis, planks=0, plank_axis="y", plank_len=0.98):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.65
    tc = N.new("ShaderNodeTexCoord")
    # veio: anéis em volta do eixo do comprimento, centro deslocado para fora da peça (arcos suaves, quase retos)
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = {"x": (0, 0.9, 0.35), "y": (0.9, 0, 0.35), "z": (0.7, 0.55, 0)}[grain_axis]
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    wave = N.new("ShaderNodeTexWave")
    wave.wave_type, wave.rings_direction = "RINGS", grain_axis.upper()
    wave.inputs["Scale"].default_value = 8.0
    wave.inputs["Distortion"].default_value = 2.2
    wave.inputs["Detail"].default_value = 2.5
    wave.inputs["Detail Scale"].default_value = 0.25
    L.new(mp.outputs["Vector"], wave.inputs["Vector"])
    # fibras: ruído esticado ao longo do comprimento
    mp2 = N.new("ShaderNodeMapping")
    mp2.inputs["Scale"].default_value = {"x": (1.5, 90, 90), "y": (90, 1.5, 90), "z": (90, 90, 1.5)}[grain_axis]
    L.new(tc.outputs["Object"], mp2.inputs["Vector"])
    fib = N.new("ShaderNodeTexNoise")
    fib.inputs["Scale"].default_value = 1.0
    fib.inputs["Detail"].default_value = 4.0
    L.new(mp2.outputs["Vector"], fib.inputs["Vector"])
    mix = N.new("ShaderNodeMix")
    mix.data_type = "FLOAT"
    mix.inputs["Factor"].default_value = 0.55
    L.new(wave.outputs["Fac"], mix.inputs["A"])
    L.new(fib.outputs["Fac"], mix.inputs["B"])
    ramp = N.new("ShaderNodeValToRGB")
    base = lin(rgb)
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.25, 0.85
    ramp.color_ramp.elements[0].color = (*(base * 0.84), 1)
    ramp.color_ramp.elements[1].color = (*(base * 1.14), 1)
    L.new(mix.outputs["Result"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if planks:
        # junta entre tábuas: linha escura a cada 1/planks do comprimento perpendicular
        sep = N.new("ShaderNodeSeparateXYZ")
        L.new(tc.outputs["Object"], sep.inputs["Vector"])
        m1 = N.new("ShaderNodeMath"); m1.operation = "MULTIPLY_ADD"
        m1.inputs[1].default_value = planks / plank_len
        m1.inputs[2].default_value = planks / 2
        L.new(sep.outputs[plank_axis.upper()], m1.inputs[0])
        fr = N.new("ShaderNodeMath"); fr.operation = "PINGPONG"; fr.inputs[1].default_value = 0.5
        L.new(m1.outputs[0], fr.inputs[0])
        st = N.new("ShaderNodeMapRange")
        st.inputs["From Min"].default_value, st.inputs["From Max"].default_value = 0.0, 0.02
        st.inputs["To Min"].default_value, st.inputs["To Max"].default_value = 0.45, 1.0
        L.new(fr.outputs[0], st.inputs["Value"])
        mm = N.new("ShaderNodeMix"); mm.data_type = "RGBA"; mm.blend_type = "MULTIPLY"
        mm.inputs["Factor"].default_value = 1.0
        L.new(col, mm.inputs["A"])
        L.new(st.outputs["Result"], mm.inputs["B"])
        col = mm.outputs["Result"]
    # variação grande de tom (manchas de idade)
    mp3 = N.new("ShaderNodeTexNoise"); mp3.inputs["Scale"].default_value = 4.0
    L.new(tc.outputs["Object"], mp3.inputs["Vector"])
    vr = N.new("ShaderNodeMapRange")
    vr.inputs["To Min"].default_value, vr.inputs["To Max"].default_value = 0.9, 1.08
    L.new(mp3.outputs["Fac"], vr.inputs["Value"])
    mv = N.new("ShaderNodeMix"); mv.data_type = "RGBA"; mv.blend_type = "MULTIPLY"
    mv.inputs["Factor"].default_value = 1.0
    L.new(col, mv.inputs["A"])
    L.new(vr.outputs["Result"], mv.inputs["B"])
    L.new(mv.outputs["Result"], bsdf.inputs["Base Color"])
    return mat


top_rgb, side_rgb = P["tampo"], P["pe"]
m_top = wood("tampo", top_rgb, "x", planks=3, plank_axis="y")
m_leg = wood("pe", side_rgb, "z")
m_ax = wood("saia_x", side_rgb, "x")
m_ay = wood("saia_y", side_rgb, "y")

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
