"""Renderiza uma imagem de preview do sistema modular de armazenamento.

Uso:
    blender --background --python preview.py -- --out preview.png
    python preview.py --out preview.png        (com o modulo `bpy` instalado)
"""

import argparse
import math
import os
import sys

import bpy  # noqa: I001
import bmesh  # noqa: F401  (importado por consistencia com tcg_storage)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tcg_storage import Params, build_all, place_assembly, place_label  # noqa: E402


def material(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def look_at(obj, target):
    import mathutils
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="preview.png")
    ap.add_argument("--drawers", type=int, default=1)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--res", type=int, default=1100)
    ap.add_argument("--stack", type=int, default=2, help="modulos empilhados na cena")
    ap.add_argument("--open", type=float, default=110.0, help="quanto a gaveta abre (mm)")
    ap.add_argument("--label", default="Dragonshields", help="texto da etiqueta")
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    elif argv and os.path.basename(argv[0]).startswith("blender"):
        argv = []
    else:
        argv = argv[1:]
    args = ap.parse_args(argv)

    p = Params(drawers=args.drawers)
    parts, shell, drawers, key, labels = build_all(p, [args.label, "Commons"])
    place_assembly(p, shell, drawers, key, open_mm=args.open)
    # a chave flutua ao lado da junta entre dois modulos, na altura do sulco
    key.location = (-p.shell_w / 2 - 34.0, p.shell_d * 0.42, p.shell_h)
    key.rotation_euler = (0.0, 0.0, 0.0)

    grey = material("pla_cinza", (0.62, 0.62, 0.63))
    accent = material("pla_gaveta", (0.72, 0.72, 0.74))
    keymat = material("pla_chave", (0.85, 0.42, 0.20), roughness=0.45)
    labelmat = material("pla_etiqueta", (0.93, 0.93, 0.92), roughness=0.4)

    shell.data.materials.append(grey)
    for d in drawers:
        d.data.materials.append(accent)
    key.data.materials.append(keymat)
    for token in labels:
        token.data.materials.append(labelmat)

    # empilha copias do modulo para mostrar o encaixe
    step = p.shell_h
    drawer_slots = [tuple(drawers[0].location)]
    for i in range(1, args.stack):
        c = shell.copy()
        c.data = shell.data
        c.location = (0.0, 0.0, i * step)
        bpy.context.collection.objects.link(c)
        for level, d in enumerate(drawers):
            dc = d.copy()
            dc.data = d.data
            dc.location = (0.0, 0.0, d.location.z + i * step)
            bpy.context.collection.objects.link(dc)
            if level == 0:
                drawer_slots.append(tuple(dc.location))

    # coloca um token em cada gaveta e deixa o em branco sobre a mesa
    for token, slot in zip(labels[1:], reversed(drawer_slots)):
        place_label(p, token, slot, 0)
    if labels:
        labels[0].location = (-p.shell_w / 2 - 60.0, -60.0, p.token_t / 2)
        labels[0].rotation_euler = (0.0, 0.0, math.radians(-20))

    total_h = step * args.stack

    # chao
    bpy.ops.mesh.primitive_plane_add(size=2000, location=(0, p.shell_d / 2, -0.1))
    floor = bpy.context.object
    floor.data.materials.append(material("mesa", (0.20, 0.13, 0.08), roughness=0.7))

    # luzes
    bpy.ops.object.light_add(type="AREA", location=(-320, -260, 480))
    key_light = bpy.context.object
    key_light.data.energy = 6.0e6
    key_light.data.size = 400
    look_at(key_light, (0, p.shell_d / 2, total_h / 2))

    bpy.ops.object.light_add(type="AREA", location=(420, -120, 260))
    fill = bpy.context.object
    fill.data.energy = 1.6e6
    fill.data.size = 500
    look_at(fill, (0, p.shell_d / 2, total_h / 2))

    world = bpy.context.scene.world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

    # camera
    reach = max(total_h, p.shell_d) * 2.0
    bpy.ops.object.camera_add(
        location=(-reach * 0.70, -reach * 0.90, total_h * 0.60 + reach * 0.22)
    )
    cam = bpy.context.object
    cam.data.lens = 55
    look_at(cam, (0, p.shell_d * 0.38, total_h * 0.42))
    bpy.context.scene.camera = cam

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.res
    scene.render.resolution_y = int(args.res * 0.78)
    scene.render.film_transparent = False
    scene.render.filepath = os.path.abspath(args.out)
    bpy.ops.render.render(write_still=True)
    print(f"preview salvo em {scene.render.filepath}")


if __name__ == "__main__":
    main(list(sys.argv))
