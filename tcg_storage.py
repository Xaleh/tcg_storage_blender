"""
Sistema modular de armazenamento de cartas (TCG) - gerador parametrico para Blender.

Modela tres pecas prontas para impressao 3D:

  1. shell   - o corpo/casco do modulo, com sulcos (rabo de andorinha) nas quatro
               faces externas (topo, base, esquerda, direita) correndo ao longo
               da profundidade.
  2. drawer  - a gaveta (bandeja + frente + puxador), uma por nivel.
  3. key     - a chave/clipe de encaixe: um perfil de rabo de andorinha duplo que
               desliza em dois sulcos vizinhos e trava dois modulos juntos.

Todas as medidas estao em milimetros (1 unidade Blender = 1 mm).

Uso:
    blender --background --python tcg_storage.py -- --export
    python tcg_storage.py --export            (se o modulo `bpy` estiver instalado)

Parametros principais (ver --help):
    --card-w/--card-h  espaco interno para a carta (padrao 70 x 95 mm, ja
                       acomoda carta com sleeve duplo)
    --depth            profundidade util da gaveta (padrao 220 mm ~ 350 cartas)
    --drawers          numero de gavetas empilhadas no mesmo casco (padrao 1)
"""

import argparse
import math
import os
import sys

import bpy  # noqa: I001  (bpy precisa vir antes; ele e quem registra bmesh)
import bmesh


# --------------------------------------------------------------------------
# Parametros
# --------------------------------------------------------------------------

class Params:
    """Todas as cotas do projeto, em milimetros."""

    def __init__(self, **kw):
        # --- espaco util para as cartas -------------------------------------
        self.card_w = 70.0        # largura interna da gaveta (carta 63 + sleeves)
        self.card_h = 95.0        # altura interna da gaveta (carta 88 + sleeves)
        # 190 mm mantem o casco em 195 mm quando impresso em pe (apoiado no
        # fundo, boca para cima), que cabe na altura util da maioria das
        # impressoras. Ver README para outras profundidades.
        self.depth = 190.0        # profundidade util (pilha de cartas)
        self.drawers = 1          # gavetas empilhadas no mesmo casco

        # --- espessuras -----------------------------------------------------
        self.d_wall = 1.6         # parede da gaveta
        self.d_floor = 1.6        # fundo da gaveta
        self.d_face = 3.0         # frente da gaveta
        self.s_wall = 3.0         # parede externa do casco
        self.shelf = 2.0          # divisoria entre gavetas (drawers > 1)

        # --- folgas ---------------------------------------------------------
        self.gap = 0.4            # folga gaveta <-> casco (por lado)
        self.face_gap = 0.3       # folga ao redor da frente da gaveta
        self.key_clear = 0.2      # folga da chave dentro do sulco (por face)

        # --- sulcos de encaixe (rabo de andorinha, flancos a 45 graus) ------
        self.g_open = 6.0         # largura na superficie
        self.g_depth = 1.6        # profundidade do sulco
        self.g_flare = 1.6        # alargamento por lado no fundo (45 graus)
        self.grooves_top = 2      # sulcos no topo e na base
        self.grooves_side = 3     # sulcos em cada lateral

        # --- puxador --------------------------------------------------------
        self.handle_w = 40.0      # largura
        self.handle_out = 16.0    # quanto avanca a frente
        self.handle_t = 8.0       # espessura da aba
        self.handle_ramp = 16.0   # rampa inferior a 45 graus (auto-sustentavel)

        # --- porta-etiqueta na frente da gaveta ------------------------------
        # Bolso saliente, aplicado sobre a frente da gaveta (nao a atravessa).
        # Tem paredes nas laterais e embaixo e fica aberto em cima: o token
        # desce por ali e a moldura frontal o segura. Aberto em cima nao ha
        # nenhuma ponte para imprimir.
        self.label = True         # criar o porta-etiqueta
        self.label_w = 56.0       # largura util do bolso
        self.label_h = 16.0       # altura util do bolso
        self.label_out = 2.6      # quanto o bolso avanca da frente da gaveta
        self.label_front = 0.8    # espessura da moldura frontal
        self.label_rim = 1.6      # espessura das paredes laterais e do fundo
        self.label_lip = 2.0      # quanto a moldura cobre o token por lado
        self.label_clear = 0.3    # folga do token no bolso (total)
        self.label_grip = 2.0     # quanto o token sobra acima do bolso, para
                                  # dar onde pegar na hora de trocar (0 = rente)
        self.label_z = None       # cota do centro (None = automatico)

        # --- token de etiqueta ----------------------------------------------
        self.label_text_h = 0.6   # altura do texto em relevo
        self.label_margin = 1.5   # margem do texto dentro da janela
        self.label_font = None    # caminho de um .ttf (None = fonte padrao)

        # --- chave de uniao -------------------------------------------------
        self.key_len = 60.0

        # --- acabamento -----------------------------------------------------
        self.bevel = 0.6          # chanfro das arestas externas (0 = desligado)

        for k, v in kw.items():
            if v is not None:
                if not hasattr(self, k):
                    raise KeyError(f"parametro desconhecido: {k}")
                setattr(self, k, v)

    # --- cotas derivadas ---------------------------------------------------

    @property
    def g_bottom(self):
        """Largura do sulco no fundo (parte mais larga do rabo de andorinha)."""
        return self.g_open + 2.0 * self.g_flare

    @property
    def drawer_w(self):
        return self.card_w + 2.0 * self.d_wall

    @property
    def drawer_h(self):
        return self.card_h + self.d_floor

    @property
    def drawer_d(self):
        return self.depth + self.d_wall

    @property
    def cav_w(self):
        return self.drawer_w + 2.0 * self.gap

    @property
    def cav_h(self):
        return self.drawer_h + 2.0 * self.gap

    @property
    def cav_d(self):
        return self.drawer_d + self.gap

    @property
    def shell_w(self):
        return self.cav_w + 2.0 * self.s_wall

    @property
    def shell_h(self):
        n = self.drawers
        return 2.0 * self.s_wall + n * self.cav_h + (n - 1) * self.shelf

    @property
    def shell_d(self):
        return self.cav_d + self.s_wall

    def cavity_z(self, level):
        """Altura da base da cavidade do nivel `level` (0 = mais baixo)."""
        return self.s_wall + level * (self.cav_h + self.shelf)

    def face_span(self, level):
        """Faixa vertical (z0, z1) coberta pela frente da gaveta do nivel."""
        n = self.drawers
        if level == 0:
            b0 = 0.0
        else:
            b0 = self.s_wall + level * (self.cav_h + self.shelf) - self.shelf / 2.0
        if level == n - 1:
            b1 = self.shell_h
        else:
            b1 = self.s_wall + (level + 1) * (self.cav_h + self.shelf) - self.shelf / 2.0
        return b0 + self.face_gap, b1 - self.face_gap

    @property
    def label_slot(self):
        """Profundidade do vao do token, medida a partir da frente da gaveta."""
        return self.label_out - self.label_front

    @property
    def label_box_w(self):
        """Largura externa do bolso."""
        return self.label_w + 2.0 * self.label_rim

    @property
    def token_w(self):
        return self.label_w - self.label_clear

    @property
    def token_h(self):
        return self.label_h - self.label_clear

    @property
    def token_t(self):
        """Espessura do token: fica 0,2 mm mais raso que o vao."""
        return self.label_slot - 0.2

    @property
    def label_wall_h(self):
        """Altura das paredes do bolso, contada a partir da base do vao.

        Fica `label_grip` abaixo do topo do token, para sobrar onde pegar.
        """
        return self.token_h - self.label_grip

    @property
    def label_box_h(self):
        """Altura externa do bolso (sem parede em cima: entrada do token)."""
        return self.label_wall_h + self.label_rim

    def face_span_local(self, level):
        """`face_span` nas coordenadas locais da gaveta (fundo da bandeja = 0)."""
        z0, z1 = self.face_span(level)
        base = self.cavity_z(level) + self.gap
        return z0 - base, z1 - base

    def handle_span(self, fz0, fz1):
        """(espessura da aba, topo, base) do puxador, em coordenadas locais."""
        ht = min(self.handle_t, (fz1 - fz0) * 0.25)
        top = fz1 - 4.0
        return ht, top, top - ht - self.handle_ramp

    def label_center_z(self, level=0):
        """Cota local do centro do vao do token: meio da area livre abaixo do
        puxador, descontando a parede de baixo do bolso."""
        if self.label_z is not None:
            return self.label_z
        fz0, fz1 = self.face_span_local(level)
        _, _, handle_bottom = self.handle_span(fz0, fz1)
        return (fz0 + handle_bottom) / 2.0 + self.label_rim / 2.0

    def label_fits(self, level=0):
        """(cabe?, motivo) - confere se o bolso cabe na frente desta gaveta."""
        fz0, fz1 = self.face_span_local(level)
        _, _, handle_bottom = self.handle_span(fz0, fz1)
        free = handle_bottom - fz0
        if self.label_box_w + 4.0 > self.shell_w - 2 * self.face_gap:
            return False, "largura da frente insuficiente"
        if self.label_box_h + 2.0 > free:
            return False, "altura livre abaixo do puxador insuficiente"
        if self.label_front < 0.6:
            return False, "moldura frontal fina demais"
        if self.label_lip < 1.0:
            return False, "aba da moldura pequena demais"
        if self.label_slot <= 0.8:
            return False, "vao do token raso demais"
        return True, ""

    def groove_centers_top(self):
        """Posicoes X dos sulcos das faces superior/inferior."""
        return _spread(self.shell_w, self.grooves_top)

    def groove_centers_side(self):
        """Posicoes Z dos sulcos das faces laterais."""
        return [z + self.shell_h / 2.0 for z in _spread(self.shell_h, self.grooves_side)]


def _spread(total, count):
    """Distribui `count` posicoes simetricas em torno de 0 dentro de `total`."""
    if count <= 0:
        return []
    step = total / (count + 1.0)
    return [-total / 2.0 + step * (i + 1) for i in range(count)]


# --------------------------------------------------------------------------
# Utilitarios de malha
# --------------------------------------------------------------------------

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.objects):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def setup_units():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"


def _mesh_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return obj


def box(name, x0, x1, y0, y1, z0, z1):
    """Caixa alinhada aos eixos definida pelos seus limites."""
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    return _mesh_object(name, verts, faces)


def prism(name, profile, axis, a, b):
    """Extruda um poligono 2D ao longo de `axis` ('X', 'Y' ou 'Z'), de a ate b.

    `profile` e uma lista de pares nas duas coordenadas restantes, na ordem
    (X, Y, Z) menos o eixo de extrusao.
    """
    order = {"X": (1, 2), "Y": (0, 2), "Z": (0, 1)}[axis]
    idx = {"X": 0, "Y": 1, "Z": 2}[axis]

    def place(pt, t):
        v = [0.0, 0.0, 0.0]
        v[order[0]], v[order[1]] = pt
        v[idx] = t
        return tuple(v)

    n = len(profile)
    verts = [place(p, a) for p in profile] + [place(p, b) for p in profile]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    return _mesh_object(name, verts, faces)


def boolean(target, cutter, operation="DIFFERENCE"):
    """Aplica um booleano exato e remove o objeto cortante."""
    mod = target.modifiers.new(name="bool", type="BOOLEAN")
    mod.operation = operation
    mod.object = cutter
    mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def add_bevel(obj, width, segments=2, angle=math.radians(40)):
    if width <= 0:
        return obj
    mod = obj.modifiers.new(name="bevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = angle
    mod.harden_normals = False
    mod.use_clamp_overlap = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def mesh_report(obj):
    """Retorna (volume_cm3, n_arestas_nao_manifold)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol / 1000.0, bad


# --------------------------------------------------------------------------
# Perfis dos sulcos
# --------------------------------------------------------------------------

def _dovetail_profile(u_center, v_surface, v_dir, p, over=1.0):
    """Perfil (u, v) do cortador do sulco.

    u = direcao da largura do sulco, v = direcao da profundidade.
    `v_dir` = -1 corta para baixo (sulco numa face voltada para +v).
    """
    half_o = p.g_open / 2.0
    half_b = p.g_bottom / 2.0
    v_out = v_surface - v_dir * over          # um pouco fora da peca
    v_in = v_surface + v_dir * p.g_depth      # fundo do sulco
    return [
        (u_center - half_o, v_out),
        (u_center + half_o, v_out),
        (u_center + half_o, v_surface),
        (u_center + half_b, v_in),
        (u_center - half_b, v_in),
        (u_center - half_o, v_surface),
    ]


def _key_profile(p):
    """Secao transversal da chave: dois rabos de andorinha costas com costas.

    O perfil e o do sulco recuado de `key_clear` em todas as faces, de modo que
    a folga seja uniforme (inclusive na ponta do rabo de andorinha, onde um
    simples estreitamento em largura deixaria folga zero).
    """
    c = p.key_clear
    d = p.g_depth - c                 # profundidade em cada lado
    half_o = p.g_open / 2.0 - c       # meia largura na garganta (v = 0)
    half_b = half_o + d               # meia largura na ponta (flanco a 45 graus)
    return [
        (-half_b, -d), (half_b, -d),
        (half_o, 0.0),
        (half_b, d), (-half_b, d),
        (-half_o, 0.0),
    ]


# --------------------------------------------------------------------------
# Pecas
# --------------------------------------------------------------------------

def build_shell(p):
    """Casco do modulo. Frente aberta em y = 0, base em z = 0."""
    body = box("shell", -p.shell_w / 2, p.shell_w / 2, 0.0, p.shell_d, 0.0, p.shell_h)

    if p.bevel:
        add_bevel(body, p.bevel, segments=2)

    # cavidades das gavetas (abertas na frente)
    for level in range(p.drawers):
        z0 = p.cavity_z(level)
        cav = box(
            f"cav{level}",
            -p.cav_w / 2, p.cav_w / 2,
            -1.0, p.cav_d,
            z0, z0 + p.cav_h,
        )
        boolean(body, cav)

    # sulcos topo / base (correm ao longo de Y)
    for i, x in enumerate(p.groove_centers_top()):
        top = prism(f"gt{i}", _dovetail_profile(x, p.shell_h, -1, p), "Y", -1.0, p.shell_d + 1.0)
        boolean(body, top)
        bot = prism(f"gb{i}", _dovetail_profile(x, 0.0, +1, p), "Y", -1.0, p.shell_d + 1.0)
        boolean(body, bot)

    # sulcos laterais: perfil no plano Z-X, extrudado em Y
    for i, z in enumerate(p.groove_centers_side()):
        for side, sx in (("r", +1), ("l", -1)):
            prof_zx = _dovetail_profile(z, sx * p.shell_w / 2, -sx, p)
            prof_xz = [(v, u) for (u, v) in prof_zx]      # (u=z, v=x) -> (x, z)
            cut = prism(f"gs{i}{side}", prof_xz, "Y", -1.0, p.shell_d + 1.0)
            boolean(body, cut)

    return body


def build_drawer(p, level=0, name=None):
    """Gaveta: bandeja aberta em cima + frente + puxador.

    Origem local: fundo da bandeja em z = 0, face interna da frente em y = 0.
    """
    name = name or (f"drawer_{level + 1}" if p.drawers > 1 else "drawer")

    tray = box(
        name,
        -p.drawer_w / 2, p.drawer_w / 2,
        0.0, p.drawer_d,
        0.0, p.drawer_h,
    )
    cavity = box(
        "tray_cav",
        -p.card_w / 2, p.card_w / 2,
        -1.0, p.depth,
        p.d_floor, p.drawer_h + 1.0,
    )
    boolean(tray, cavity)

    # frente
    z0, z1 = p.face_span(level)
    base_z = p.cavity_z(level) + p.gap        # onde a bandeja repousa no casco
    fz0, fz1 = z0 - base_z, z1 - base_z
    face = box(
        "face",
        -(p.shell_w / 2 - p.face_gap), p.shell_w / 2 - p.face_gap,
        -p.d_face, 0.0,
        fz0, fz1,
    )
    if p.bevel:
        add_bevel(face, p.bevel, segments=2)

    # puxador: aba com rampa inferior a 45 graus (imprime sem suporte)
    ht, top, _ = p.handle_span(fz0, fz1)
    y_out = -p.d_face - p.handle_out
    profile = [
        (-p.d_face, top),
        (y_out, top),
        (y_out, top - ht),
        (-p.d_face, top - ht - p.handle_ramp),
    ]
    handle = prism("handle", profile, "X", -p.handle_w / 2, p.handle_w / 2)
    add_bevel(handle, min(1.2, ht / 3.0), segments=3)

    boolean(tray, face, "UNION")
    boolean(tray, handle, "UNION")

    if p.label:
        ok, why = p.label_fits(level)
        if ok:
            boolean(tray, _label_pocket(p, level), "UNION")
        else:
            print(f"  aviso: porta-etiqueta omitido em {name} ({why})")

    tray.name = name
    return tray


def _label_pocket(p, level=0):
    """Bolso saliente do porta-etiqueta, pronto para unir a frente da gaveta.

    E um bloco macico do qual se tira o vao do token (aberto em cima, por onde
    ele entra) e a janela frontal, cuja moldura o segura. Nenhum corte chega a
    atravessar a frente da gaveta.
    """
    zc = p.label_center_z(level)
    zb = zc - p.label_h / 2               # base do vao: onde o token repousa
    zt = zb + p.label_wall_h              # topo das paredes
    front = -p.d_face                     # superficie da frente da gaveta
    bury = 0.6                            # afunda na frente: uniao sem faces coplanares

    body = box(
        "label_pocket",
        -p.label_box_w / 2, p.label_box_w / 2,
        front - p.label_out, front + bury,
        zb - p.label_rim, zt,
    )

    # vao do token: aberto em cima e com o fundo na propria frente da gaveta
    slot = box(
        "label_slot",
        -p.label_w / 2, p.label_w / 2,
        front - p.label_slot, front + bury + 1.0,
        zb, zt + 1.0,
    )
    boolean(body, slot)

    # janela frontal: a moldura cobre laterais e base do token
    window = box(
        "label_window",
        -(p.label_w / 2 - p.label_lip), p.label_w / 2 - p.label_lip,
        front - p.label_out - 1.0, front - p.label_slot,
        zb + p.label_lip, zt + 1.0,
    )
    boolean(body, window)
    return body


def _text_mesh(p, text, top_z):
    """Malha do texto em relevo, centrada na origem, apoiada em z = top_z."""
    from mathutils import Matrix

    bpy.ops.object.text_add(location=(0.0, 0.0, top_z))
    obj = bpy.context.object
    obj.name = "label_text"
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    # extrusao simetrica: metade sobe (relevo) e metade afunda na placa,
    # garantindo interseccao solida para a uniao booleana.
    obj.data.extrude = p.label_text_h
    if p.label_font:
        obj.data.font = bpy.data.fonts.load(p.label_font)

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object

    # encaixa o texto na janela visivel da moldura
    win_w = p.label_w - 2 * p.label_lip - 2 * p.label_margin
    win_h = p.label_h - 2 * p.label_lip - 2 * p.label_margin
    dim = obj.dimensions
    if dim.x > 1e-6 and dim.y > 1e-6:
        s = min(win_w / dim.x, win_h / dim.y)
        obj.scale = (s, s, 1.0)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # recentraliza pelo bounding box real (acentos e descidas desalinham)
    bb = obj.bound_box
    cx = (min(v[0] for v in bb) + max(v[0] for v in bb)) / 2.0
    cy = (min(v[1] for v in bb) + max(v[1] for v in bb)) / 2.0
    obj.data.transform(Matrix.Translation((-cx, -cy, 0.0)))
    return obj


def slugify(text):
    """Nome de arquivo a partir do texto da etiqueta."""
    out = []
    for ch in text.lower():
        out.append(ch if ch.isalnum() else "_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "token"


def build_label(p, text=None, name=None):
    """Token de etiqueta, deitado (espessura em Z) - ja na posicao de impressao.

    Com `text`, o texto sai em relevo na face de cima; imprima com troca de
    filamento na altura do relevo para ter contraste de cor.
    """
    name = name or ("label" if not text else f"label_{slugify(text)}")

    plate = box(
        name,
        -p.token_w / 2, p.token_w / 2,
        -p.token_h / 2, p.token_h / 2,
        0.0, p.token_t,
    )
    add_bevel(plate, 0.3, segments=1)      # quebra as bordas: entra mais facil

    if text:
        boolean(plate, _text_mesh(p, text, p.token_t), "UNION")

    plate.name = name
    return plate


def build_key(p):
    """Chave de uniao: rabo de andorinha duplo, desliza em dois sulcos."""
    # sem chanfro: as arestas da "cintura" sao concavas e o bevel acrescentaria
    # material justamente onde a folga do sulco e minima.
    return prism("key", _key_profile(p), "Y", -p.key_len / 2, p.key_len / 2)


# --------------------------------------------------------------------------
# Cena / exportacao
# --------------------------------------------------------------------------

def export_stl(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=path,
        export_selected_objects=True,
        global_scale=1.0,
        apply_modifiers=True,
    )
    obj.select_set(False)


def build_all(p, texts=None):
    """Constroi as pecas e devolve (pecas, casco, gavetas, chave, etiquetas)."""
    clear_scene()
    setup_units()

    shell = build_shell(p)
    drawers = [build_drawer(p, level) for level in range(p.drawers)]
    key = build_key(p)

    labels = []
    if p.label and p.label_fits(0)[0]:
        labels.append(build_label(p))                 # token em branco
        for text in (texts or []):
            labels.append(build_label(p, text))

    return [shell] + drawers + [key] + labels, shell, drawers, key, labels


def place_label(p, token, drawer_location=(0.0, 0.0, 0.0), level=0):
    """Encaixa um token no bolso da gaveta indicada.

    O token e modelado deitado (espessura em Z); girado 90 graus em X ele fica
    em pe, com o texto voltado para a frente, encostado na moldura.
    """
    token.rotation_euler = (math.radians(90), 0.0, 0.0)
    token.location = (
        drawer_location[0],
        drawer_location[1] - (p.d_face + p.label_slot - p.token_t),
        drawer_location[2] + p.label_center_z(level),
    )
    return token


def place_assembly(p, shell, drawers, key, open_mm=90.0):
    """Posiciona as pecas montadas (a primeira gaveta fica aberta)."""
    for level, drw in enumerate(drawers):
        drw.location = (
            0.0,
            (open_mm if level == 0 else 0.0),
            p.cavity_z(level) + p.gap,
        )
    key.rotation_euler = (0.0, 0.0, 0.0)
    key.location = (p.shell_w / 2 + 30.0, p.shell_d / 2, p.shell_h / 2)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--card-w", type=float, help="largura interna da gaveta (mm)")
    ap.add_argument("--card-h", type=float, help="altura interna da gaveta (mm)")
    ap.add_argument("--depth", type=float, help="profundidade util da gaveta (mm)")
    ap.add_argument("--drawers", type=int, help="gavetas empilhadas no mesmo casco")
    ap.add_argument("--gap", type=float, help="folga gaveta/casco por lado (mm)")
    ap.add_argument("--s-wall", type=float, help="espessura da parede do casco (mm)")
    ap.add_argument("--d-wall", type=float, help="espessura da parede da gaveta (mm)")
    ap.add_argument("--key-len", type=float, help="comprimento da chave de uniao (mm)")
    ap.add_argument("--key-clear", type=float,
                    help="folga da chave no sulco, por face (mm); menor = mais firme")
    ap.add_argument("--bevel", type=float, help="chanfro das arestas externas (0 desliga)")
    ap.add_argument("--label-text", action="append", metavar="TEXTO",
                    help="gera um token com esse texto em relevo (pode repetir)")
    ap.add_argument("--label-w", type=float, help="largura do porta-etiqueta (mm)")
    ap.add_argument("--label-h", type=float, help="altura do porta-etiqueta (mm)")
    ap.add_argument("--label-font", metavar="TTF", help="fonte do texto do token")
    ap.add_argument("--no-label", action="store_true",
                    help="gaveta lisa, sem porta-etiqueta")
    ap.add_argument("--out", default="stl", help="pasta de saida dos STL")
    ap.add_argument("--export", action="store_true", help="exportar STL")
    ap.add_argument("--save-blend", metavar="ARQUIVO", help="salvar arquivo .blend")
    ap.add_argument("--assembly", action="store_true",
                    help="deixar a cena montada em vez de lado a lado")

    # `blender --background --python x.py -- <args>` passa tudo em sys.argv;
    # `python x.py <args>` passa o nome do script em argv[0].
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    elif argv and os.path.basename(argv[0]).startswith("blender"):
        argv = []
    else:
        argv = argv[1:]
    args = ap.parse_args(argv)

    p = Params(
        card_w=args.card_w, card_h=args.card_h, depth=args.depth,
        drawers=args.drawers, gap=args.gap, s_wall=args.s_wall,
        d_wall=args.d_wall, key_len=args.key_len, bevel=args.bevel,
        key_clear=args.key_clear, label_w=args.label_w, label_h=args.label_h,
        label_font=args.label_font,
        label=(False if args.no_label else None),
    )

    parts, shell, drawers, key, labels = build_all(p, args.label_text)

    print("\n=== Modulo de armazenamento de cartas ===")
    print(f"  externo do casco : {p.shell_w:.1f} x {p.shell_d:.1f} x {p.shell_h:.1f} mm"
          "  (largura x profundidade x altura)")
    print(f"  com a frente     : profundidade total "
          f"{p.shell_d + p.d_face + (p.label_out if labels else 0.0):.1f} mm "
          f"(o puxador avanca outros {p.handle_out:.0f} mm)")
    print(f"  espaco por gaveta: {p.card_w:.1f} x {p.depth:.1f} x {p.card_h:.1f} mm")
    print(f"  capacidade       : ~{int(p.depth / 0.62)} cartas com sleeve duplo "
          f"(~{int(p.depth / 0.45)} com sleeve simples) por gaveta")
    print(f"  sulcos           : {p.grooves_top} no topo/base, {p.grooves_side} "
          f"por lateral - abertura {p.g_open:.1f} mm, {p.g_depth:.1f} mm de "
          "profundidade")
    if labels:
        print(f"  porta-etiqueta   : bolso saliente {p.label_box_w:.1f} x "
              f"{p.label_box_h:.1f} mm, avanca {p.label_out:.1f} mm da frente")
        print(f"  token            : {p.token_w:.1f} x {p.token_h:.1f} x "
              f"{p.token_t:.1f} mm, texto {p.label_text_h:.1f} mm em relevo, "
              "entra por cima")
    print()

    for obj in parts:
        vol, bad = mesh_report(obj)
        status = "manifold" if bad == 0 else f"{bad} ARESTAS NAO-MANIFOLD"
        print(f"  {obj.name:<12} volume {vol:7.2f} cm3   {status}")
    print()

    if args.export:
        out = os.path.abspath(args.out)
        os.makedirs(out, exist_ok=True)
        for obj in parts:
            loc = tuple(obj.location)
            obj.location = (0.0, 0.0, 0.0)
            path = os.path.join(out, f"{obj.name}.stl")
            export_stl(obj, path)
            obj.location = loc
            print(f"  exportado {path} ({os.path.getsize(path) / 1024:.0f} KB)")
        print()

    if args.assembly:
        place_assembly(p, shell, drawers, key)
        if labels:
            place_label(p, labels[-1], drawers[0].location, 0)
    else:
        gap = 20.0
        shell.location = (0.0, 0.0, 0.0)
        for i, drw in enumerate(drawers):
            drw.location = (p.shell_w + gap, 0.0, i * (p.drawer_h + gap))
        key.location = (-p.shell_w / 2 - gap, p.shell_d / 2, 0.0)
        for i, token in enumerate(labels):
            token.location = (-p.shell_w / 2 - gap, p.shell_d / 2 + 40.0,
                              i * (p.label_h + 6.0))

    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save_blend))
        print(f"  cena salva em {args.save_blend}\n")


if __name__ == "__main__":
    main(list(sys.argv))
