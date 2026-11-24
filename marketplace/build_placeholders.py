"""Builds the PLACEHOLDER Marketplace content of Aosabi Karaoke as grey-box .glb files:

  assets/scenes/karaoke_room/    a room (VTube Pro's room contract: SPOT_xx, CAM_*, SCREEN, DOOR, DOOR_OUTSIDE,
  assets/scenes/karaoke_stage/   PATH_xx, LIGHT_*; metres, +Y up, stage front = +Z)
  props/karaoke_props/           an asset pack ("vtp-props/1"): the rooms' furniture as objects people can place

    python build_placeholders.py     (needs numpy; Pillow for the pictures)

The boxes are stand-ins: replace each .glb with the real model later (keep the node names in the rooms, and each
prop's origin at its bottom centre with its front towards +Z), or use this file as the layout guide.

Nothing written into the pack files names a person or a brand: VTube Pro's Marketplace tool refuses packs that do
(the listing's "by ..." credit is given to that tool separately, see README.md). Copyright (c) 2026 aosabi. All rights reserved.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SUN = np.array([0.35, 0.85, 0.4]) / np.linalg.norm([0.35, 0.85, 0.4])   # for the simple baked shading


class Room:
    def __init__(self):
        self.nodes, self.meshes, self.materials, self.cameras = [], [], [], []
        self.accessors, self.views, self.bin = [], [], bytearray()
        self._mat = {}
        self.plan = []          # (name, centre, size) of every box, for the floor-plan pictures

    # ---- low level
    def _view(self, data: bytes, target: int | None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.views.append(v)
        return len(self.views) - 1

    def _acc(self, arr: np.ndarray, kind: str, comp: int, target: int | None, minmax=False) -> int:
        a = {"bufferView": self._view(arr.tobytes(), target), "componentType": comp, "count": len(arr), "type": kind}
        if minmax:
            a["min"], a["max"] = arr.min(axis=0).tolist(), arr.max(axis=0).tolist()
        self.accessors.append(a)
        return len(self.accessors) - 1

    def material(self, name: str, rgb, emissive=None, rough=0.9) -> int:
        if name not in self._mat:
            m = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [*[c ** 2.2 for c in rgb], 1.0], "metallicFactor": 0.0, "roughnessFactor": rough}}
            if emissive:
                m["emissiveFactor"] = [c ** 2.2 for c in emissive]
            self.materials.append(m)
            self._mat[name] = len(self.materials) - 1
        return self._mat[name]

    def _mesh(self, name, pos, nrm, idx, mat, uv=None, shade=True) -> int:
        pos, nrm = np.asarray(pos, "<f4"), np.asarray(nrm, "<f4")
        attrs = {"POSITION": self._acc(pos, "VEC3", 5126, 34962, True), "NORMAL": self._acc(nrm, "VEC3", 5126, 34962)}
        if uv is not None:
            attrs["TEXCOORD_0"] = self._acc(np.asarray(uv, "<f4"), "VEC2", 5126, 34962)
        if shade:   # light "baked" into vertex colours, as the room contract asks (room shadows are off in the app)
            lit = 0.55 + 0.45 * np.clip(nrm @ SUN.astype("<f4"), 0, 1)
            attrs["COLOR_0"] = self._acc(np.repeat(lit[:, None], 3, 1).astype("<f4"), "VEC3", 5126, 34962)
        self.meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": self._acc(np.asarray(idx, "<u2"), "SCALAR", 5123, 34963), "material": mat}]})
        return len(self.meshes) - 1

    def node(self, name, t=(0, 0, 0), yaw=0.0, mesh=None, extras=None, rotation=None, camera=None) -> int:
        n = {"name": name, "translation": [float(x) for x in t]}
        q = rotation or ([0.0, math.sin(math.radians(yaw) / 2), 0.0, math.cos(math.radians(yaw) / 2)] if yaw else None)
        if q:
            n["rotation"] = [float(x) for x in q]
        if mesh is not None:
            n["mesh"] = mesh
        if camera is not None:
            n["camera"] = camera
        if extras:
            n["extras"] = extras
        self.nodes.append(n)
        return len(self.nodes) - 1

    # ---- shapes
    def box(self, name, centre, size, mat, yaw=0.0, extras=None, origin=None) -> int:
        """A box. `origin` (world) moves the node's pivot, e.g. a door's hinge; default = the box centre."""
        self.plan.append((name, tuple(centre), tuple(size)))
        o = np.array(origin if origin is not None else centre, float)
        c, h = np.array(centre, float) - o, np.array(size, float) / 2
        pos, nrm, idx = [], [], []
        for axis in range(3):
            for sign in (-1, 1):
                u, v = [(1, 2), (2, 0), (0, 1)][axis]
                n = np.zeros(3)
                n[axis] = sign
                base = len(pos)
                for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    p = n * h[axis]
                    p[u], p[v] = du * h[u], dv * h[v]
                    pos.append(c + p)
                    nrm.append(n)
                idx += [base, base + 1, base + 2, base, base + 2, base + 3] if sign > 0 else [base, base + 2, base + 1, base, base + 3, base + 2]
        return self.node(name, o, yaw, self._mesh(name, pos, nrm, idx, mat), extras)

    def screen(self, centre, width, rest_offset) -> int:
        """The react screen: a 16:9 plane facing +Z with UVs 0..1 (top-left = 0,0)."""
        w, h = width / 2, width * 9 / 32
        pos = [(-w, -h, 0), (w, -h, 0), (w, h, 0), (-w, h, 0)]
        mat = self.material("screen", (0.05, 0.05, 0.07), rough=0.4)
        mesh = self._mesh("SCREEN", pos, [(0, 0, 1)] * 4, [0, 1, 2, 0, 2, 3], mat, uv=[(0, 1), (1, 1), (1, 0), (0, 0)], shade=False)
        return self.node("SCREEN", centre, 0, mesh, {"restOffsetY": rest_offset})

    def spot(self, i, pos, yaw, pose, label, seat_height=None) -> int:
        ex = {"pose": pose, "label": label}
        if seat_height:
            ex["seatHeight"] = seat_height
        return self.node(f"SPOT_{i:02d}", pos, yaw, extras=ex)

    def cam(self, name, pos, target, yfov=38.0) -> int:
        self.cameras.append({"name": name, "type": "perspective", "perspective": {"yfov": math.radians(yfov), "aspectRatio": 16 / 9, "znear": 0.1, "zfar": 200.0}})
        f = np.array(target, float) - np.array(pos, float)
        f /= np.linalg.norm(f)
        r = np.cross(f, [0, 1, 0])
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        m = np.stack([r, u, -f], axis=1)        # camera looks down its -Z
        w = math.sqrt(max(0.0, 1 + m[0, 0] + m[1, 1] + m[2, 2])) / 2
        q = [(m[2, 1] - m[1, 2]) / (4 * w), (m[0, 2] - m[2, 0]) / (4 * w), (m[1, 0] - m[0, 1]) / (4 * w), w]
        return self.node(name, pos, rotation=q, camera=len(self.cameras) - 1)

    def write(self, path: Path) -> None:
        while len(self.bin) % 4:
            self.bin.append(0)
        doc = {"asset": {"version": "2.0", "generator": "placeholder builder"}, "scene": 0,
               "scenes": [{"name": "Scene", "nodes": list(range(len(self.nodes)))}], "nodes": self.nodes, "meshes": self.meshes,
               "materials": self.materials, "cameras": self.cameras, "accessors": self.accessors, "bufferViews": self.views,
               "buffers": [{"byteLength": len(self.bin)}]}
        doc = {k: v for k, v in doc.items() if v != []}          # glTF does not allow empty lists (a prop has no cameras)
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(self.bin)) + struct.pack("<I4s", len(js), b"JSON") + js
                         + struct.pack("<I4s", len(self.bin), b"BIN\0") + bytes(self.bin))


def shell(r: Room, w: float, d: float, h: float, door_x: float):
    """Floor, back wall, two side walls and a door in the left wall (the front, +Z, stays open for the cameras)."""
    floor, wall, trim = r.material("floor", (0.32, 0.32, 0.36)), r.material("wall", (0.55, 0.55, 0.6)), r.material("trim", (0.2, 0.2, 0.24))
    r.box("Floor", (0, -0.05, 0), (w, 0.1, d), floor)
    r.box("Wall_Back", (0, h / 2, -d / 2 - 0.1), (w + 0.4, h, 0.2), wall)
    r.box("Wall_Right", (w / 2 + 0.1, h / 2, 0), (0.2, h, d), wall)
    zd = door_x                                   # the doorway sits in the left wall at this z
    r.box("Wall_Left_A", (-w / 2 - 0.1, h / 2, (-d / 2 + zd - 0.5) / 2), (0.2, h, zd - 0.5 + d / 2), wall)
    r.box("Wall_Left_B", (-w / 2 - 0.1, h / 2, (zd + 0.5 + d / 2) / 2), (0.2, h, d / 2 - zd - 0.5), wall)
    r.box("Wall_Left_Top", (-w / 2 - 0.1, (2.1 + h) / 2, zd), (0.2, h - 2.1, 1.0), wall)
    # the door leaf: its origin is the hinge, it turns about +Y
    r.box("DOOR", (-w / 2 - 0.1, 1.05, zd), (0.06, 2.1, 1.0), trim, extras={"openAngle": 95}, origin=(-w / 2 - 0.1, 0, zd - 0.5))
    r.node("DOOR_OUTSIDE", (-w / 2 - 1.2, 0, zd), yaw=90)
    r.node("PATH_01", (-w / 2 + 1.0, 0, zd))


def neon(r: Room, name: str, centre, size, colour):
    r.box(name + "_Strip", centre, size, r.material("EMIT_neon", (0.1, 0.1, 0.1), emissive=colour))
    r.node(f"LIGHT_{name}", centre, extras={"group": "neon", "color": "#%02x%02x%02x" % tuple(int(c * 255) for c in colour), "kind": "emissive"})


def karaoke_room() -> Room:
    r = Room()
    w, d, h = 7.0, 6.0, 3.0
    shell(r, w, d, h, door_x=1.2)
    soft, wood = r.material("couch", (0.5, 0.22, 0.34)), r.material("wood", (0.4, 0.3, 0.22))
    r.box("Singer_Riser", (0, 0.075, -1.6), (3.0, 0.15, 1.6), wood)
    r.box("Couch_Left_Seat", (-2.4, 0.225, 0.4), (0.9, 0.45, 2.0), soft)
    r.box("Couch_Left_Back", (-2.95, 0.6, 0.4), (0.2, 1.2, 2.0), soft)
    r.box("Couch_Right_Seat", (2.4, 0.225, 0.4), (0.9, 0.45, 2.0), soft)
    r.box("Couch_Right_Back", (2.95, 0.6, 0.4), (0.2, 1.2, 2.0), soft)
    r.box("Table", (0, 0.2, 0.9), (1.4, 0.4, 0.8), wood)
    r.screen((0, 1.75, -2.95), 3.2, rest_offset=0.0)
    neon(r, "NEON_01", (0, 2.75, -2.97), (5.0, 0.08, 0.05), (1.0, 0.25, 0.6))
    neon(r, "NEON_02", (0, 0.16, -0.79), (3.0, 0.03, 0.03), (0.3, 0.8, 1.0))
    r.spot(1, (0, 0.15, -1.6), 0, "stand", "Singer")
    r.spot(2, (0.9, 0.15, -1.5), -15, "stand", "Duet partner")
    r.spot(3, (-2.3, 0, 0.0), 75, "sit", "Couch left", 0.45)
    r.spot(4, (2.3, 0, 0.0), -75, "sit", "Couch right", 0.45)
    r.spot(5, (-2.3, 0, 0.9), 100, "sit", "Couch left, front", 0.45)
    r.spot(6, (2.3, 0, 0.9), -100, "sit", "Couch right, front", 0.45)
    r.cam("CAM_WIDE", (0, 1.7, 5.6), (0, 1.1, -1.4))
    r.cam("CAM_REACT", (0, 1.75, 2.2), (0, 1.75, -2.95), yfov=36)
    r.cam("CAM_SINGER", (0.5, 1.55, 1.4), (0, 1.35, -1.6), yfov=35)
    return r


def stage() -> Room:
    r = Room()
    w, d, h = 16.0, 12.0, 7.0
    shell(r, w, d, h, door_x=3.5)
    deck, truss = r.material("stage", (0.16, 0.16, 0.18)), r.material("truss", (0.4, 0.4, 0.44))
    r.box("Stage_Deck", (0, 0.4, -3.2), (10.0, 0.8, 5.0), deck)
    r.box("Stage_Steps_1", (-5.6, 0.2, -1.6), (1.2, 0.4, 1.4), deck)
    r.box("Stage_Steps_2", (-5.6, 0.1, -0.4), (1.2, 0.2, 1.0), deck)
    r.box("Truss_Top", (0, 6.2, -1.2), (11.0, 0.3, 0.3), truss)
    r.box("Truss_Left", (-5.4, 3.1, -1.2), (0.3, 6.2, 0.3), truss)
    r.box("Truss_Right", (5.4, 3.1, -1.2), (0.3, 6.2, 0.3), truss)
    r.box("Monitor_Left", (-1.6, 0.95, -1.0), (0.7, 0.3, 0.5), truss)
    r.box("Monitor_Right", (1.6, 0.95, -1.0), (0.7, 0.3, 0.5), truss)
    r.screen((0, 3.9, -5.6), 7.2, rest_offset=0.0)
    neon(r, "NEON_01", (0, 0.82, -0.72), (10.0, 0.04, 0.04), (1.0, 0.25, 0.6))
    neon(r, "NEON_02", (0, 6.0, -1.2), (10.4, 0.06, 0.06), (0.3, 0.8, 1.0))
    r.spot(1, (0, 0.8, -2.2), 0, "stand", "Centre stage")
    r.spot(2, (-2.6, 0.8, -2.8), 12, "stand", "Stage left")
    r.spot(3, (2.6, 0.8, -2.8), -12, "stand", "Stage right")
    r.spot(4, (0, 0.8, -4.2), 0, "stand", "Back of the stage")
    r.spot(5, (-3.0, 0, 2.5), 160, "stand", "In the crowd, left")
    r.spot(6, (3.0, 0, 2.5), -160, "stand", "In the crowd, right")
    for z, name in ((-0.4, "PATH_02"), (-1.6, "PATH_03")):
        r.node(name, (-5.6, 0.2 if z > -1 else 0.4, z))
    r.cam("CAM_WIDE", (0, 2.6, 5.6), (0, 2.2, -3.0))
    r.cam("CAM_REACT", (0, 3.9, 5.4), (0, 3.9, -5.6), yfov=36)
    r.cam("CAM_SINGER", (0.8, 2.2, 1.6), (0, 2.0, -2.2), yfov=35)
    r.cam("CAM_CROWD", (-4.5, 1.7, 5.0), (0.5, 1.8, -2.4), yfov=40)
    return r


def pictures(r: Room, title: str, out: Path) -> None:
    """preview.png + thumb.png: a labelled floor plan (placeholders, like the room itself). Needs Pillow; skipped without it."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  (Pillow is not installed: preview.png / thumb.png not made)")
        return
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (18, 19, 26))
    d = ImageDraw.Draw(img)
    xs = [c[0] + sx * s[0] / 2 for _, c, s in r.plan for sx in (-1, 1)] + [n["translation"][0] for n in r.nodes]
    zs = [c[2] + sz * s[2] / 2 for _, c, s in r.plan for sz in (-1, 1)] + [n["translation"][2] for n in r.nodes]
    k = min((W - 160) / (max(xs) - min(xs)), (H - 150) / (max(zs) - min(zs)))
    px = lambda x, z: (W / 2 + (x - (max(xs) + min(xs)) / 2) * k, 90 + (z - min(zs)) * k)
    for name, c, s in sorted(r.plan, key=lambda b: b[1][1]):
        if name.startswith(("Wall_Left_Top", "Truss_Top")):
            continue
        a, b = px(c[0] - s[0] / 2, c[2] - s[2] / 2), px(c[0] + s[0] / 2, c[2] + s[2] / 2)
        shade = 44 if name == "Floor" else 96 if name.startswith("Wall") else 70 if "Strip" not in name else 0
        d.rectangle([a, b], fill=(255, 95, 162) if "Strip" in name else (shade, shade, shade + 8), outline=(120, 120, 135))
    for n in r.nodes:
        x, z = px(n["translation"][0], n["translation"][2])
        if n["name"].startswith("SPOT_"):
            d.ellipse([x - 9, z - 9, x + 9, z + 9], fill=(255, 95, 162))
            d.text((x + 13, z - 7), f'{n["name"][5:]} {n["extras"]["label"]}', fill=(233, 233, 240))
        elif n["name"] == "SCREEN":
            d.line([x - 60, z + 4, x + 60, z + 4], fill=(95, 200, 255), width=5)
            d.text((x - 22, z + 10), "SCREEN", fill=(95, 200, 255))
        elif n["name"].startswith("CAM_"):
            d.polygon([(x, z - 8), (x - 8, z + 8), (x + 8, z + 8)], fill=(255, 200, 87))
            d.text((x + 11, z - 5), n["name"], fill=(255, 200, 87))
        elif n["name"] == "DOOR_OUTSIDE":
            d.text((x - 20, z - 6), "DOOR", fill=(95, 211, 141))
    d.text((40, 28), f"{title}  -  floor plan of the placeholder (replace with the real room art)", fill=(233, 233, 240))
    d.text((40, H - 36), "top = back wall, bottom = towards the cameras", fill=(154, 157, 176))
    img.save(out / "preview.png")
    img.resize((480, 270)).save(out / "thumb.png")


ROOMS = {
    "karaoke_room": ("Karaoke Room (placeholder)", karaoke_room, {"background": "#101018", "fog": "#101018", "fogNear": 9, "fogFar": 26, "exposure": 0.8}),
    "karaoke_stage": ("Karaoke Stage (placeholder)", stage, {"background": "#08080c", "fog": "#08080c", "fogNear": 14, "fogFar": 46, "exposure": 0.8}),
}

# ---------------------------------------------------------------- the asset pack
PACK_ID, PACK_VERSION = "karaoke_props", "2026.11.16-1"
SOFT, WOOD, DARK, METAL = ("couch", (0.5, 0.22, 0.34)), ("wood", (0.4, 0.3, 0.22)), ("stage", (0.16, 0.16, 0.18)), ("truss", (0.4, 0.4, 0.44))
# id: (name, category, where it goes, [(part, centre, size, material), ...]); origin = bottom centre, front = +Z
PROPS = {
    "couch": ("Karaoke couch", "seating", "floor", [("Seat", (0, 0.225, 0.1), (2.0, 0.45, 0.9), SOFT), ("Back", (0, 0.6, -0.45), (2.0, 1.2, 0.2), SOFT)]),
    "coffee_table": ("Coffee table", "furniture", "floor", [("Top", (0, 0.37, 0), (1.4, 0.06, 0.8), WOOD), ("Base", (0, 0.17, 0), (1.1, 0.34, 0.5), WOOD)]),
    "singer_riser": ("Singer riser", "stage", "floor", [("Riser", (0, 0.075, 0), (3.0, 0.15, 1.6), WOOD)]),
    "stage_deck": ("Stage deck piece", "stage", "floor", [("Deck", (0, 0.4, 0), (2.5, 0.8, 2.5), DARK)]),
    "stage_steps": ("Stage steps", "stage", "floor", [("Low", (0, 0.1, 0.5), (1.2, 0.2, 1.0), DARK), ("High", (0, 0.2, -0.5), (1.2, 0.4, 1.0), DARK)]),
    "truss_arch": ("Lighting truss", "stage", "floor", [("Top", (0, 6.2, 0), (11.0, 0.3, 0.3), METAL), ("Left", (-5.4, 3.1, 0), (0.3, 6.2, 0.3), METAL), ("Right", (5.4, 3.1, 0), (0.3, 6.2, 0.3), METAL)]),
    "floor_monitor": ("Floor monitor speaker", "stage", "floor", [("Box", (0, 0.15, 0), (0.7, 0.3, 0.5), METAL)]),
    "mic_stand": ("Microphone stand", "stage", "floor", [("Base", (0, 0.02, 0), (0.36, 0.04, 0.36), METAL), ("Pole", (0, 0.72, 0), (0.03, 1.36, 0.03), METAL), ("Mic", (0, 1.44, 0.04), (0.05, 0.05, 0.16), DARK)]),
    "neon_strip": ("Neon light strip", "lights", "wall", [("Mount", (0, 0.04, -0.02), (2.0, 0.08, 0.02), METAL)]),
}


def build_prop(pid: str) -> tuple[Room, dict]:
    name, category, place, parts = PROPS[pid]
    r = Room()
    for part, centre, size, (mat, rgb) in parts:
        r.box(f"{pid}_{part}", centre, size, r.material(mat, rgb))
    item = {"id": pid, "name": name, "file": f"{pid}.glb", "thumb": f"thumbs/{pid}.png", "category": category, "place": place, "scale": 1}
    if pid == "neon_strip":   # a light prop: a glowing strip (material EMIT_<pack id>) + its lamp marker
        r.box(f"{pid}_Glow", (0, 0.04, 0.01), (1.96, 0.05, 0.04), r.material(f"EMIT_{PACK_ID}", (0.05, 0.05, 0.05), emissive=(1.0, 0.25, 0.6)))
        r.node("LIGHT_NEON", (0, 0.04, 0.05), extras={"kind": "emissive", "color": "#ff40a0", "group": PACK_ID, "effect": "steady"})
        item["tags"] = ["light"]
    lo = np.min([np.array(c) - np.array(s) / 2 for _, c, s in r.plan], axis=0)
    hi = np.max([np.array(c) + np.array(s) / 2 for _, c, s in r.plan], axis=0)
    item.update(tris=12 * len(r.plan), meshes=len(r.plan), size=[round(float(v), 3) for v in hi - lo])
    return r, item


def prop_thumb(r: Room, out: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    img = Image.new("RGB", (256, 256), (24, 25, 33))
    d = ImageDraw.Draw(img)
    lo = np.min([np.array(c) - np.array(s) / 2 for _, c, s in r.plan], axis=0)
    hi = np.max([np.array(c) + np.array(s) / 2 for _, c, s in r.plan], axis=0)
    k = 200 / max(hi[0] - lo[0], hi[1] - lo[1], 0.05)
    for name, c, s in sorted(r.plan, key=lambda b: b[1][2]):          # back to front, seen from the front
        x0, x1 = 128 + (c[0] - s[0] / 2 - (lo[0] + hi[0]) / 2) * k, 128 + (c[0] + s[0] / 2 - (lo[0] + hi[0]) / 2) * k
        y0, y1 = 228 - (c[1] + s[1] / 2 - lo[1]) * k, 228 - (c[1] - s[1] / 2 - lo[1]) * k
        d.rectangle([x0, y0, max(x1, x0 + 2), max(y1, y0 + 2)], fill=(255, 95, 162) if "Glow" in name else (120, 120, 134), outline=(190, 190, 205))
    img.save(out)


if __name__ == "__main__":
    for rid, (name, build, ambience) in ROOMS.items():
        out = HERE / "assets" / "scenes" / rid
        out.mkdir(parents=True, exist_ok=True)
        room = build()
        room.write(out / "scene.glb")
        pictures(room, name, out)
        (out / "scene.json").write_text(json.dumps({"id": rid, "name": name, "model": "scene.glb", "modes": ["talk", "react"], "defaultCamera": "CAM_WIDE",
                                                    "ambience": ambience, "avatarHeight": 1.5, "lights": {"programs": ["steady"]}}, indent=2) + "\n", "utf-8")
        print(f"wrote assets/scenes/{rid}/scene.glb ({(out / 'scene.glb').stat().st_size} bytes) and scene.json")
    pack = HERE / "props" / PACK_ID
    (pack / "thumbs").mkdir(parents=True, exist_ok=True)
    items = []
    for pid in PROPS:
        r, item = build_prop(pid)
        r.write(pack / item["file"])
        prop_thumb(r, pack / item["thumb"])
        items.append(item)
    (pack / "props.json").write_text(json.dumps({"schema": "vtp-props/1", "id": PACK_ID, "name": "Karaoke props (placeholder)", "version": PACK_VERSION,
                                                  "license": "own", "items": items}, indent=2) + "\n", "utf-8")
    print(f"wrote props/{PACK_ID}/props.json with {len(items)} objects")
