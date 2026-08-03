"""Verificacoes automaticas do modelo antes de imprimir.

Confere, por interseccao booleana real, que as pecas encaixam sem colidir:

  * gaveta fechada dentro do casco;
  * chave dentro do sulco superior (uniao vertical);
  * chave dentro do sulco lateral (uniao lado a lado);
  * dois modulos empilhados nao se interpenetram;
  * todas as malhas sao fechadas (manifold).

Aceita as mesmas flags de cota do tcg_storage.py, para conferir a configuracao
que voce vai imprimir e nao so a padrao.

Uso:
    blender --background --python validate.py
    blender --background --python validate.py -- --g-open 18 --drawers 3
"""

import argparse
import math
import os
import sys

import bpy  # noqa: I001
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tcg_storage import (  # noqa: E402
    add_param_args, build_all, mesh_report, params_from_args, place_label,
    strip_argv,
)


def volume_mm3(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    v = bm.calc_volume(signed=True)
    bm.free()
    return abs(v)


def duplicate(obj, name, location=(0, 0, 0), rotation=(0, 0, 0)):
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = name
    copy.location = location
    copy.rotation_euler = rotation
    bpy.context.collection.objects.link(copy)
    bpy.context.view_layer.update()
    return copy


def intersection_volume(a, b):
    """Volume da interseccao de dois objetos (0 = nao colidem)."""
    tmp = duplicate(a, "isect_a", tuple(a.location), tuple(a.rotation_euler))
    other = duplicate(b, "isect_b", tuple(b.location), tuple(b.rotation_euler))
    for obj in (tmp, other):
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    mod = tmp.modifiers.new(name="bool", type="BOOLEAN")
    mod.operation = "INTERSECT"
    mod.object = other
    mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = tmp
    bpy.ops.object.modifier_apply(modifier=mod.name)

    vol = volume_mm3(tmp)
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.objects.remove(other, do_unlink=True)
    return vol


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_param_args(ap)
    args = ap.parse_args(strip_argv(list(argv if argv is not None else sys.argv)))

    p = params_from_args(args)
    parts, shell, drawers, key, labels = build_all(
        p, args.label_text or ["Cheap sleeves"])
    drawer = drawers[0]

    failures = []

    def check(label, ok, detail=""):
        mark = "OK  " if ok else "FALHA"
        print(f"  [{mark}] {label}{('  -> ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print("\n=== Malhas ===")
    for obj in parts:
        _, bad = mesh_report(obj)
        check(f"{obj.name}: malha fechada", bad == 0, f"{bad} arestas nao-manifold")

    print("\n=== Folgas dimensionais ===")
    check("gaveta cabe na largura da cavidade",
          p.drawer_w < p.cav_w, f"{p.cav_w - p.drawer_w:.2f} mm de folga total")
    check("gaveta cabe na altura da cavidade",
          p.drawer_h < p.cav_h, f"{p.cav_h - p.drawer_h:.2f} mm de folga total")
    check("gaveta cabe na profundidade da cavidade",
          p.drawer_d < p.cav_d, f"{p.cav_d - p.drawer_d:.2f} mm de folga")
    check("parede do casco mais grossa que o sulco",
          p.s_wall - p.g_depth >= 1.2,
          f"restam {p.s_wall - p.g_depth:.2f} mm de material")
    check("chave nao ultrapassa a soma dos dois sulcos",
          2 * (p.g_depth - p.key_clear) < 2 * p.g_depth,
          f"chave {2 * (p.g_depth - p.key_clear):.2f} mm x "
          f"vao {2 * p.g_depth:.2f} mm")
    check("flancos do rabo de andorinha imprimivel (<= 45 graus)",
          math.degrees(math.atan2(p.g_flare, p.g_depth)) <= 45.5,
          f"{math.degrees(math.atan2(p.g_flare, p.g_depth)):.1f} graus")
    # sulcos largos demais se encostariam, virando um rasgo unico: a malha
    # continua fechada e a chave continua entrando, entao so uma conta pega.
    for face, total, count in (("topo/base", p.shell_w, p.grooves_top),
                               ("lateral", p.shell_h, p.grooves_side)):
        step = total / (count + 1.0)
        check(f"sulcos da face {face} nao se encostam",
              p.g_bottom + 2.0 <= step,
              f"fundo {p.g_bottom:.1f} mm x passo {step:.1f} mm "
              f"({step - p.g_bottom:.1f} mm entre sulcos)")

    print("\n=== Porta-etiqueta ===")
    check("porta-etiqueta cabe na frente da gaveta", *(
        lambda ok, why: (ok, why or "ok"))(*p.label_fits(0)))
    check("token mais raso que o vao do bolso",
          p.token_t < p.label_slot,
          f"token {p.token_t:.2f} mm x vao {p.label_slot:.2f} mm")
    check("moldura segura o token",
          p.label_lip - p.label_clear / 2 >= 1.0,
          f"{p.label_lip - p.label_clear / 2:.2f} mm de sobreposicao por lado")
    check("texto em relevo nao passa da frente do bolso",
          p.label_text_h < p.label_front,
          f"relevo {p.label_text_h:.1f} mm x moldura {p.label_front:.1f} mm")
    check("bolso aberto em cima (token entra deslizando, sem ponte)",
          p.label_wall_h < p.token_h,
          f"paredes {p.label_wall_h:.1f} mm x token {p.token_h:.1f} mm")
    check("token sobra acima do bolso para poder ser puxado",
          p.label_grip >= 1.5, f"{p.label_grip:.1f} mm de pega")
    check("moldura ainda segura o token com folga de pega",
          p.label_wall_h >= p.token_h * 0.7,
          f"{p.label_wall_h / p.token_h * 100:.0f}% da altura retida")
    check("bolso nao invade a lateral da frente da gaveta",
          p.label_box_w <= p.shell_w - 2 * p.face_gap - 4.0,
          f"bolso {p.label_box_w:.1f} mm x frente "
          f"{p.shell_w - 2 * p.face_gap:.1f} mm")

    print("\n=== Colisoes reais (booleano) ===")
    # 1. gaveta fechada dentro do casco
    drawer.location = (0.0, 0.0, p.cavity_z(0) + p.gap)
    v = intersection_volume(shell, drawer)
    check("gaveta fechada nao colide com o casco", v < 1e-3, f"{v:.4f} mm3")

    # 2. chave no sulco do topo
    x = p.groove_centers_top()[0]
    key.location = (x, p.shell_d / 2, p.shell_h)
    key.rotation_euler = (0.0, 0.0, 0.0)
    v = intersection_volume(shell, key)
    check("chave desliza no sulco do topo", v < 1e-3, f"{v:.4f} mm3")

    # 3. chave no sulco da base
    key.location = (x, p.shell_d / 2, 0.0)
    v = intersection_volume(shell, key)
    check("chave desliza no sulco da base", v < 1e-3, f"{v:.4f} mm3")

    # 4. chave no sulco lateral (girada 90 graus em Y)
    z = p.groove_centers_side()[0]
    key.location = (p.shell_w / 2, p.shell_d / 2, z)
    key.rotation_euler = (0.0, math.radians(90), 0.0)
    v = intersection_volume(shell, key)
    check("chave desliza no sulco lateral", v < 1e-3, f"{v:.4f} mm3")
    key.rotation_euler = (0.0, 0.0, 0.0)

    # 4b. tokens encaixados no bolso da gaveta
    drawer.location = (0.0, 0.0, p.cavity_z(0) + p.gap)
    for token in labels:
        place_label(p, token, drawer.location, 0)
        v = intersection_volume(drawer, token)
        check(f"'{token.name}' encaixa no bolso sem colidir", v < 1e-3,
              f"{v:.4f} mm3")
        v = intersection_volume(shell, token)
        check(f"'{token.name}' nao encosta no casco", v < 1e-3, f"{v:.4f} mm3")

    # 5. dois modulos empilhados
    upper = duplicate(shell, "shell_upper", (0.0, 0.0, p.shell_h))
    v = intersection_volume(shell, upper)
    check("modulos empilhados nao se interpenetram", v < 1e-3, f"{v:.4f} mm3")
    bpy.data.objects.remove(upper, do_unlink=True)

    # 6. dois modulos lado a lado
    side = duplicate(shell, "shell_side", (p.shell_w, 0.0, 0.0))
    v = intersection_volume(shell, side)
    check("modulos lado a lado nao se interpenetram", v < 1e-3, f"{v:.4f} mm3")
    bpy.data.objects.remove(side, do_unlink=True)

    print()
    if failures:
        print(f"{len(failures)} verificacao(oes) falharam.\n")
        sys.exit(1)
    print("Todas as verificacoes passaram.\n")


if __name__ == "__main__":
    main()
