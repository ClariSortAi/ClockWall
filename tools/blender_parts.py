"""Open the watch in a live Blender, every part named, to look at it.

    python tools/blender_parts.py        # launches Blender's GUI with the parts loaded

Imports Assets/movement.glb (the OM10, 166 named solids) and Assets/case.glb
(the case set from case_solids.py) into a fresh Blender scene, one object per
part under two collections, in material preview, with the dial and crystal
hidden so the mechanism can be seen. Nothing is rendered or saved; this is
for looking, and for picking a part by name in the outliner to see where it
is. The live-render face is the picture; this is the workshop bench.
"""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INSIDE = r'''
import bpy, os
root = r"%(root)s"
bpy.ops.wm.read_homefile(use_empty=True)
scene = bpy.context.scene
for name, path in (("Movement", "movement.glb"), ("Case", "case.glb")):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(root, "Assets", path))
    new = [o for o in bpy.data.objects if o not in before]
    coll = bpy.data.collections.new(name)
    scene.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
# The dial and crystal hide the movement; leave them in the outliner, unticked.
for n in ("dial", "crystal", "caseback"):
    o = bpy.data.objects.get(n)
    if o: o.hide_set(True); o.hide_render = True
# Material preview, from the front (the dial side is +Y in glTF, which Blender turns to +Z).
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.shading.type = "MATERIAL"
                space.clip_start = 0.1
                space.clip_end = 1000
                r3d = space.region_3d
                r3d.view_perspective = "PERSP"
        with bpy.context.temp_override(area=area):
            bpy.ops.view3d.view_axis(type="TOP")
            bpy.ops.view3d.view_all(center=True)
scene.unit_settings.system = "METRIC"
scene.unit_settings.length_unit = "MILLIMETERS"
print("loaded", len(bpy.data.objects), "objects")
'''


def main():
    base = r"C:\Program Files\Blender Foundation"
    exe = None
    for d in sorted(os.listdir(base), reverse=True):
        cand = os.path.join(base, d, "blender.exe")
        if os.path.exists(cand):
            exe = cand
            break
    if exe is None:
        raise SystemExit("Blender not found under " + base)
    script = os.path.join(tempfile.gettempdir(), "clockwall_blender_parts.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(INSIDE % {"root": ROOT})
    subprocess.Popen([exe, "--python", script], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    print("Blender launched with the parts:", exe)


if __name__ == "__main__":
    main()
