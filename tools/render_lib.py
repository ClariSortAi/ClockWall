"""Shared Blender scene: world, lights, materials, solids, and the checks.

Imported by blender_face.py (renders the assets) and blender_swatch.py (renders
postage-stamp crops of the SAME scene, for iterating in seconds instead of
minutes). Both entry points must agree about every material and every light, so
neither owns any of it - this does.

THREE THINGS HERE WERE LEARNED THE EXPENSIVE WAY.

  * THE ENVIRONMENT IS THE MATERIAL. Every part of this watch is metallic, and
    a metal has no diffuse component at all: it can only show you what it
    reflects. So the world is not lighting the parts, it IS their colour. A
    hand-authored sky stood in for it through several passes and produced, in
    turn, a black plate, white steel, a black bezel and unlit chamfers - and it
    was concealing a plain bug the whole time (a SPHERICAL gradient fed from a
    normalized direction vector, which evaluates to a constant). A measured
    studio HDRI removes the entire class of problem.

  * LIGHTS ARE SPECIFIED IN RADIANCE, NOT WATTS. A polished surface returns a
    source's power per unit AREA, so what a mirror shows has nothing to do with
    the lamp's wattage. Tuning watts while thinking about brightness caused more
    churn than any other single thing here: a softbox at 1.15e7 W sounded
    reasonable and had a radiance of 13, where 1.0 is already white, so every
    hand clipped flat and no facet could show.

  * THE SCENE GRAPH IS CHECKED, NOT EYEBALLED. See `audit`. The bevel bug
    survived three renders because a flat part and a chamfered one look similar
    at a glance and identical when both are blown out; one look at the evaluated
    mesh found it immediately.

Face space throughout: 640x640, centre (320,320), y down. Blender is y-up, so
every y is negated on the way in and the two agree with no flip at the end.
"""

import math
import os

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROFILES = os.path.join(ROOT, "captures", "geom", "profiles.json")
ASSETS = os.path.join(ROOT, "Assets")
HDRI = os.path.join(HERE, "hdri", "studio_small_09_2k.hdr")

FACE = 640.0
DIAL_R = 300.0

# The studio HDRI is a real room, so its brightness is whatever the photographer
# had that day. This scales it to sit where the render wants it.
WORLD_STRENGTH = 0.62
WORLD_ROTATION = -128.0    # degrees, to bring the main softbox round to upper left


# --------------------------------------------------------------------- scene

def reset(samples=256, res=1920, exposure=-0.35):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = exposure
    scene.view_settings.look = "None"

    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type in (kind, "CPU")
                scene.cycles.device = "GPU"
                break
    except Exception as exc:
        print("[render] CPU only:", exc)
    return scene


def world(path=HDRI, strength=WORLD_STRENGTH, rotation=WORLD_ROTATION):
    """
    A measured photographic studio, as the environment.

    This is the single most important setting in the project and it is no longer
    a setting - it is a file. Polished metal under a real studio environment
    looks like polished metal on the first render, because the softboxes, their
    falloff and the dark floor between them are all measured rather than
    guessed.
    """
    if not os.path.exists(path):
        raise SystemExit("missing HDRI: %s (see tools/hdri/SOURCE.txt)" % path)

    w = bpy.data.worlds.new("w")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    mapping = nt.nodes.new("ShaderNodeMapping")
    tex = nt.nodes.new("ShaderNodeTexCoord")

    env.image = bpy.data.images.load(path)
    bg.inputs["Strength"].default_value = strength
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(rotation))

    nt.links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return env


TARGET = (320.0, -450.0, 0.0)      # middle of the aperture


def area_light(name, loc, radiance, size, aim=True, target=TARGET):
    """
    An area light specified by RADIANCE - power per unit area - not by wattage.

    This is the unit that matters, because a polished surface reflects a source
    directly and returns its radiance whole. A value near 1.0 renders as white;
    2 to 4 is a bright highlight; below 0.5 is a soft presence. Wattage is
    derived, and is meaningless on its own: the same 5e6 W is a gentle wash
    through a large panel and a blinding spot through a small one.
    """
    data = bpy.data.lights.new(name, "AREA")
    data.size = size
    data.energy = radiance * (size ** 2) * math.pi
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    obj.rotation_euler = _aim(loc, target) if aim else (0.0, 0.0, 0.0)
    # Lights are drawn by camera rays unless told otherwise, and a white
    # rectangle across the whole frame is not the intended effect.
    obj.visible_camera = False
    bpy.context.collection.objects.link(obj)
    return obj


def _aim(loc, target=TARGET):
    dx, dy, dz = target[0] - loc[0], target[1] - loc[1], target[2] - loc[2]
    return (math.atan2(math.hypot(dx, dy), -dz), 0.0, math.atan2(dy, dx) + math.pi / 2)


def lights():
    """
    The HDRI does most of the work; these three shape it.

    A studio environment gives even, believable metal but no direction, so the
    key is here to cast the shadows that make the stack read as a stack, and the
    accent rakes low across the chamfers to draw the bright line along each one.
    A chamfer lit from overhead is just a slightly different grey.
    """
    # THE OVERHEAD SOFTBOX IS WHAT MAKES FLAT POLISHED SURFACES READ. Under a
    # straight-down camera a flat horizontal mirror reflects straight UP and
    # nothing else, so the bezel and the tops of the indices can only ever show
    # whatever is directly above them. A studio HDRI has its softboxes off to
    # the sides where a photographer puts them for a three-quarter shot, so the
    # zenith is comparatively dark and the bezel came back black. This is the
    # panel a watch photographer hangs over the top, for exactly this reason.
    area_light("softbox", (320, -320, 1200), radiance=0.85, size=900, aim=False)
    area_light("key", (-300, 250, 1250), radiance=14.0, size=210)
    area_light("accent", (700, 500, 420), radiance=9.0, size=90)
    area_light("fill", (500, -600, 700), radiance=0.35, size=900)


def lights_axial(centre=(320.0, -320.0)):
    """
    Lighting for the hands, and for them alone.

    Every source is centred on the hands' own pivot axis, which makes the setup
    rotationally symmetric about it - so rotating a hand is a SYMMETRY of the
    lighting, and one baked image is correct at all twelve hours rather than
    only at the one it was rendered at. Bake a hand under the raking key instead
    and its lit facet turns with it, so at six o'clock it is lit from the lower
    right while every other shadow on the dial still points upper left.
    """
    area_light("axial", (centre[0], centre[1], 1500.0), radiance=0.72, size=520, aim=False)
    area_light("axial_tight", (centre[0], centre[1], 700.0), radiance=1.6, size=90, aim=False)


def clear_lights():
    for obj in [o for o in bpy.context.collection.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(obj, do_unlink=True)


def camera():
    """
    Orthographic, straight down, framed to the whole 640 face box.

    Framing to the FACE rather than to the aperture costs resolution, but it
    means every output shares one coordinate system with the XAML and a part can
    move in the geometry without re-fitting anything downstream.
    """
    data = bpy.data.cameras.new("cam")
    data.type = "ORTHO"
    data.ortho_scale = FACE
    # Face units are not metres and the camera stands 1400 of them back, which
    # is well outside Blender's default 100-unit far plane. Leave it and every
    # pass renders a perfectly clean empty frame, with no error to say why.
    data.clip_start = 1.0
    data.clip_end = 4000.0
    obj = bpy.data.objects.new("cam", data)
    obj.location = (FACE / 2, -FACE / 2, 1400)
    obj.rotation_euler = (0, 0, 0)
    bpy.context.collection.objects.link(obj)
    bpy.context.scene.camera = obj
    return obj


# ------------------------------------------------------------------ materials

def _graining(mat, bsdf, scale, strength=0.30):
    """
    Concentric turning marks, driven into roughness.

    A wheel is finished on a lathe and the marks run in circles, so its
    highlight sweeps AROUND the part as it turns. Without this a disc of metal
    renders as a flat coloured circle. Generated coordinates run 0..1 across the
    bounding box, so for a wheel the centre of the box is the centre of the
    wheel and the rings come out concentric with no per-part origin to keep in
    step.
    """
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Location"].default_value = (-0.5, -0.5, 0.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.rings_direction = "SPHERICAL"
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 1.6
    wave.inputs["Detail"].default_value = 2.0

    base = bsdf.inputs["Roughness"].default_value
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (base, base, base, 1)
    hi = min(0.92, base + strength)
    ramp.color_ramp.elements[1].color = (hi, hi, hi, 1)

    nt.links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])


def _perlage(mat, bsdf):
    """
    Perlage: overlapping circular brush strokes, in a regular grid.

    An earlier attempt used a Voronoi DISTANCE_TO_EDGE, which is a field of
    RANDOM cells - it rendered as crumpled foil, because that is what it is.
    Perlage is not random: it is made by touching a rotating abrasive peg to the
    plate in orderly overlapping rows, so it is a grid of concentric rings.
    Setting a Voronoi's randomness to zero gives exactly that grid, and its
    Distance output is the radial distance from the nearest grid point; a sine
    of that distance is the rings.

    Scale is in OBJECT coordinates, which span the ~250 face units the plate
    covers - not 0..1. An earlier value of 34 asked for eight thousand cells
    across the plate and delivered noise the denoiser then wiped out.
    """
    nt = mat.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.voronoi_dimensions = "2D"
    vor.feature = "F1"
    vor.inputs["Randomness"].default_value = 0.0     # a grid, not a scatter
    vor.inputs["Scale"].default_value = 0.16         # strokes about six units across

    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = 5.5
    rings = nt.nodes.new("ShaderNodeMath")
    rings.operation = "SINE"

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.5

    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(vor.outputs["Distance"], scale.inputs[0])
    nt.links.new(scale.outputs["Value"], rings.inputs[0])
    nt.links.new(rings.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _dial_texture(mat, bsdf):
    """
    Map the PIL sunburst onto the dial disc, exactly.

    Object coordinates here ARE face coordinates with y negated, because
    build_part writes the profile points at (x, -y) and leaves the object at the
    origin in x and y. So the mapping is a straight divide by 640 with the v
    axis flipped back - no bounding box to reason about, and no chance of the
    texture sliding if the dial's outline changes.
    """
    path = os.path.join(ASSETS, "dial-texture.png")
    if not os.path.exists(path):
        raise SystemExit("missing %s - run tools/dial_render.py first" % path)
    nt = mat.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0 / FACE, 1.0 / FACE, 1.0)
    mapping.inputs["Location"].default_value = (0.0, 1.0, 0.0)
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(path)
    img.extension = "EXTEND"
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], img.inputs["Vector"])
    nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])


# Base colour, metallic, roughness. Under a measured studio environment these
# barely need tuning, which is the point of using one - the earlier values were
# fighting a broken sky rather than describing a metal.
SURFACES = {
    #             base colour              metal  rough
    "brass":    ((0.740, 0.560, 0.260), 1.0, 0.22),
    "blued":    ((0.035, 0.075, 0.300), 1.0, 0.11),
    "steel":    ((0.680, 0.700, 0.740), 1.0, 0.16),
    "case":     ((0.760, 0.775, 0.810), 1.0, 0.150),
    "index":    ((0.840, 0.850, 0.880), 1.0, 0.055),
    "gold":     ((0.860, 0.660, 0.290), 1.0, 0.12),
    "plate":    ((0.300, 0.310, 0.332), 0.85, 0.34),
    "floor":    ((0.145, 0.150, 0.168), 0.60, 0.60),
}


def material(kind):
    m = bpy.data.materials.new(kind)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]

    def put(key, value):
        if key in b.inputs:
            b.inputs[key].default_value = value

    if kind == "ruby":
        put("Base Color", (0.42, 0.02, 0.06, 1))
        put("Metallic", 0.0)
        put("Roughness", 0.05)
        put("IOR", 1.77)
        put("Transmission Weight", 0.85)
        return m

    if kind == "dial":
        put("Base Color", (0.5, 0.5, 0.5, 1))
        put("Metallic", 0.55)
        put("Roughness", 0.24)
        _dial_texture(m, b)
        return m

    colour, metallic, rough = SURFACES[kind]
    put("Base Color", colour + (1.0,))
    put("Metallic", metallic)
    put("Roughness", rough)

    if kind == "plate":
        _perlage(m, b)
    elif kind == "brass":
        _graining(m, b, 90.0, 0.26)
    elif kind == "steel":
        _graining(m, b, 130.0, 0.16)
    return m


# ---------------------------------------------------------------------- parts

def chamfer_limit(thickness):
    """
    The widest chamfer a part of this thickness can actually carry.

    A 45-degree facet descends as far as it reaches inward, and a part is
    extruded to half its thickness either side of centre - so a bevel deeper
    than half the thickness runs past the middle and self-intersects. Blender
    does not refuse: it silently returns a degenerate result that gets NARROWER
    as you ask for more, which is a genuinely confusing way to fail. Asking for
    nine on a ten-thick part gave a chamfer of one; asking for 4.9 gave 4.9.
    """
    return 0.92 * thickness / 2.0


def _chamfer(obj, width, segments=2):
    """
    Convert to mesh, weld it, and put a real bevel on every sharp edge.

    THE WELD IS NOT OPTIONAL. Converting a filled curve to a mesh leaves the end
    caps and the side walls as separate geometry sharing no vertices, so the rim
    of the top face is not an edge between two faces - it is two coincident
    edges belonging to one face each. A bevel needs a dihedral angle to work on
    and there isn't one, so the modifier runs, reports nothing, and returns the
    part unchanged. That was the real reason every chamfer in the scene came out
    flat for three passes: not the width, not the clamp, but a mesh with no
    edges to bevel.
    """
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.view_layer.objects.active

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    mod = obj.modifiers.new("chamfer", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)
    mod.use_clamp_overlap = False
    obj.select_set(False)
    return obj


def build_part(spec):
    """
    Profile rings to a solid.

    Rings become splines on one curve object, so Blender's fill handles the
    holes for free - a crossing in the escape wheel is a hole because it is a
    second spline, exactly as it is a second figure in XAML.
    """
    curve = bpy.data.curves.new(spec["name"], "CURVE")
    curve.dimensions = "2D"
    curve.fill_mode = "BOTH"
    curve.resolution_u = 1

    for ring in spec["rings"]:
        spline = curve.splines.new("POLY")
        spline.points.add(len(ring) - 1)
        for i, (x, y) in enumerate(ring):
            spline.points[i].co = (x, -y, 0.0, 1.0)   # face y-down -> Blender y-up
        spline.use_cyclic_u = not spec["open"]

    t = spec["thickness"]
    if spec["open"]:
        # The hairspring is a curve, not an outline: give it a section and let
        # Blender sweep it, which is what a spring actually is. A swept bevel
        # needs a 3D curve - "FULL" is not offered on a 2D one.
        curve.dimensions = "3D"
        curve.fill_mode = "FULL"
        curve.bevel_mode = "ROUND"
        curve.bevel_depth = t / 2
        curve.bevel_resolution = 2
        curve.extrude = 0.0
    else:
        curve.extrude = t / 2

    obj = bpy.data.objects.new(spec["name"], curve)
    obj.location = (0, 0, spec["z"] + t / 2)
    obj.data.materials.append(material(spec["material"]))
    bpy.context.collection.objects.link(obj)

    spec["_chamfer_applied"] = 0.0
    if not spec["open"]:
        custom = spec.get("chamfer")
        want = custom or max(0.55, min(1.4, t * 0.42))
        width = min(want, chamfer_limit(t))
        if want > width + 1e-6:
            print("[render] %s: chamfer %.2f exceeds what thickness %.1f can "
                  "carry; using %.2f" % (spec["name"], want, t, width))
        obj = _chamfer(obj, width, segments=1 if custom else 2)
        spec["_chamfer_applied"] = width
    return obj


def shadow_catcher(aperture, z):
    """
    An invisible disc that collects a shadow onto its own transparent layer.

    This is what lets a moving part carry its own shadow. Render the balance
    alone above one and the image comes back as the wheel PLUS the shadow it
    casts, on alpha - so when XAML turns that image, the shadow turns with it.
    Baking the same shadow into the static plate leaves it pointing the same way
    all day while the wheel spins.
    """
    ax, ay, ar = aperture
    bpy.ops.mesh.primitive_circle_add(vertices=128, radius=ar - 1.0,
                                      location=(ax, -ay, z), fill_type="NGON")
    obj = bpy.context.active_object
    obj.name = "catcher"
    obj.is_shadow_catcher = True
    obj.select_set(False)
    return obj


# --------------------------------------------------------------------- checks

class SceneError(AssertionError):
    pass


def audit(objects, specs):
    """
    Assert the scene is what the code believes it is, before spending minutes
    rendering it.

    EVERY CHECK HERE EXISTS BECAUSE ITS ABSENCE COST A RENDER CYCLE OR SEVERAL.
    A flat part and a chamfered one look similar at a glance and identical when
    both are blown out, so three passes of "the chamfer looks wrong, try a
    different width" went by before anyone evaluated the mesh and saw that the
    bevel had produced no new geometry at all. Looking at the depsgraph found it
    in one shot.

    Checked, per part:
      * the evaluated mesh exists and has geometry
      * a part that asked for a chamfer actually GREW one - a plain extrusion
        has exactly two distinct z levels, so a chamfered part must have more
      * it sits inside the camera's box, in the z range the camera can see
    """
    dg = bpy.context.evaluated_depsgraph_get()
    problems = []

    for spec in specs:
        name = spec["name"]
        obj = objects.get(name)
        if obj is None:
            problems.append("%s: never built" % name)
            continue

        mesh = obj.evaluated_get(dg).to_mesh()
        if len(mesh.vertices) == 0:
            problems.append("%s: evaluated to an empty mesh" % name)
            continue

        zs = {round(v.co.z, 2) for v in mesh.vertices}
        if spec.get("_chamfer_applied", 0.0) > 0.0 and len(zs) < 3:
            problems.append(
                "%s: chamfer %.2f produced no bevel geometry (%d z levels). "
                "The mesh is probably unwelded, so there is no edge to bevel."
                % (name, spec["_chamfer_applied"], len(zs)))

        xs = [v.co.x for v in mesh.vertices]
        ys = [v.co.y for v in mesh.vertices]
        if min(xs) > FACE or max(xs) < 0 or min(ys) > 0 or max(ys) < -FACE:
            problems.append("%s: lies entirely outside the 640 face box" % name)

    cam = bpy.context.scene.camera
    if cam is None:
        problems.append("no camera in the scene")
    elif cam.data.clip_end < cam.location.z:
        problems.append("camera clip_end %.0f is nearer than the camera's own "
                        "height %.0f - every pass will render empty"
                        % (cam.data.clip_end, cam.location.z))

    if bpy.context.scene.world is None:
        problems.append("no world: metal has nothing to reflect")

    if problems:
        raise SceneError("scene audit failed:\n  - " + "\n  - ".join(problems))
    print("[audit] %d parts ok" % len(specs))


def render_to(path, check=True):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if check and os.path.exists(path):
        img = bpy.data.images.load(path)
        px = img.pixels[:]
        if not any(px[3::4]):
            raise SceneError("%s rendered completely empty" % os.path.basename(path))
        bpy.data.images.remove(img)
    print("[render]", path)
