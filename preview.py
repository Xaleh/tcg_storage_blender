"""Renderiza uma imagem de preview do sistema modular de armazenamento.

Uso:
    blender --background --python preview.py -- --out preview.png
    blender --background --python preview.py -- --stack 3 --samples 128
"""

import argparse
import math
import os
import sys

import bpy  # noqa: I001
import bmesh  # noqa: F401  (importado por consistencia com tcg_storage)
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tcg_storage import (  # noqa: E402
    Params, build_all, place_assembly, place_key, place_label, strip_argv,
)


def material(name, color, roughness=0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def look_at(obj, target):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def scene_bounds():
    """(centro, 8 cantos) da caixa que envolve o que ja esta na cena.

    A gaveta aberta e a chave meio encaixada avancam bem para fora do casco,
    entao enquadrar pelas cotas do modulo corta a imagem: e o conteudo real que
    manda. Chame antes de acrescentar chao, luzes e camera.
    """
    bpy.context.view_layer.update()
    pts = [
        obj.matrix_world @ mathutils.Vector(c)
        for obj in bpy.context.scene.objects if obj.type == "MESH"
        for c in obj.bound_box
    ]
    lo = mathutils.Vector([min(q[i] for q in pts) for i in range(3)])
    hi = mathutils.Vector([max(q[i] for q in pts) for i in range(3)])
    corners = [mathutils.Vector((x, y, z))
               for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    return (lo + hi) / 2.0, corners


def fit_distance(center, corners, direction, lens, aspect, margin=1.03):
    """Distancia em `direction` que faz todos os cantos caberem no quadro.

    Com a camera em `center + direction * d`, um ponto v = canto - center cai
    dentro do quadro quando |v.R| <= (v.F + d) * tx e |v.U| <= (v.F + d) * ty
    (R/U/F = eixos da camera, tx/ty = tangentes das meias aberturas). Basta
    isolar d e ficar com o maior valor exigido.
    """
    fwd = -mathutils.Vector(direction).normalized()
    right = fwd.cross(mathutils.Vector((0.0, 0.0, 1.0))).normalized()
    up = right.cross(fwd)
    tx = 18.0 / lens                  # sensor padrao de 36 mm na maior dimensao
    ty = tx * aspect
    need = 0.0
    for c in corners:
        v = c - center
        need = max(need, abs(v.dot(right)) / tx - v.dot(fwd),
                   abs(v.dot(up)) / ty - v.dot(fwd))
    return need * margin


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="preview.png")
    ap.add_argument("--drawers", type=int, default=1)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--res", type=int, default=1100)
    ap.add_argument("--stack", type=int, default=2, help="modulos empilhados na cena")
    ap.add_argument("--open", type=float, default=110.0, help="quanto a gaveta abre (mm)")
    ap.add_argument("--label", default="Dragonshields", help="texto da etiqueta")
    args = ap.parse_args(strip_argv(argv))

    p = Params(drawers=args.drawers)
    parts, shell, drawers, key, labels = build_all(p, [args.label, "Commons"])
    place_assembly(p, shell, drawers, key, open_mm=args.open)
    # chave a meio caminho de entrar num sulco lateral, que e o que a camera ve
    place_key(p, key, face="side", index=0, side=-1, out_mm=p.key_len * 0.55)

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

    # segunda chave, alinhada com um sulco do topo e ainda por encaixar: mostra
    # a peca inteira e onde ela entra na hora de empilhar mais um modulo
    key_up = key.copy()
    key_up.data = key.data
    bpy.context.collection.objects.link(key_up)
    place_key(p, key_up, face="top", index=1, base_z=max(args.stack - 1, 0) * step)
    key_up.location.z += 26.0

    center, corners = scene_bounds()

    # chao
    bpy.ops.mesh.primitive_plane_add(size=2000, location=(0, p.shell_d / 2, -0.1))
    floor = bpy.context.object
    floor.data.materials.append(material("mesa", (0.20, 0.13, 0.08), roughness=0.7))

    # luzes
    bpy.ops.object.light_add(type="AREA", location=(-320, -260, 480))
    key_light = bpy.context.object
    key_light.data.energy = 6.0e6
    key_light.data.size = 400
    look_at(key_light, center)

    bpy.ops.object.light_add(type="AREA", location=(420, -120, 260))
    fill = bpy.context.object
    fill.data.energy = 1.6e6
    fill.data.size = 500
    look_at(fill, center)

    world = bpy.context.scene.world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

    # camera na diagonal frente-esquerda, de onde se veem a frente, a lateral
    # com os sulcos e o topo; a distancia sai do proprio conteudo da cena
    lens = 55.0
    aspect = 0.78                      # altura / largura do render
    direction = mathutils.Vector((-0.60, -0.72, 0.34)).normalized()
    dist = fit_distance(center, corners, direction, lens, aspect)
    bpy.ops.object.camera_add(location=center + direction * dist)
    cam = bpy.context.object
    cam.data.lens = lens
    look_at(cam, center)
    bpy.context.scene.camera = cam

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.res
    scene.render.resolution_y = int(args.res * aspect)
    scene.render.film_transparent = False
    scene.render.filepath = os.path.abspath(args.out)
    bpy.ops.render.render(write_still=True)
    print(f"preview salvo em {scene.render.filepath}")


if __name__ == "__main__":
    main(list(sys.argv))
