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
import numpy as np

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

def reset(samples=256, res=1920, exposure=-0.35, engine="CYCLES"):
    """
    Start a clean scene at a given engine, sample count and resolution.

    `engine` defaults to "CYCLES" and every existing caller leaves it there,
    so the full render's behaviour is untouched - this exists for
    tools/shade_preview.py, which passes "BLENDER_EEVEE_NEXT" to answer a
    shading question in seconds instead of minutes. EEVEE Next has no
    `scene.cycles` block worth touching, so the GPU device dance and the
    Cycles-only settings below are skipped for it rather than guessed at.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = exposure
    scene.view_settings.look = "None"

    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
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
    else:
        # EEVEE (Next or legacy). Render, not viewport, samples - the
        # viewport count (taa_samples) is a different property and does not
        # affect what render_to() writes.
        scene.eevee.taa_render_samples = samples
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

    env.image = bpy.data.images.load(path, check_existing=True)
    bg.inputs["Strength"].default_value = strength
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(rotation))

    nt.links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return env


def _ring_of(path=HDRI, percentile=99.0):
    """
    The same measured studio, rebuilt as a ring light on the camera's axis.

    An equirectangular environment's rows ARE lines of constant elevation, so
    collapsing each row to a single value and repeating it across the row makes
    an environment that cannot tell one compass bearing from another. What each
    row collapses TO is the whole question, and the mean is the wrong answer: a
    mirror shows the radiance it points at, not the average of the room, so
    averaging a softbox over the dark wall either side of it dims every
    reflection by about three times and the parts come back flat and dark. It
    is the right average for the total light in the room and the wrong one for
    what a polished bevel does.

    A high percentile instead says: take the brightest thing at this elevation
    and put it at EVERY bearing at this elevation - which is a ring of the
    studio's own softboxes rather than one of them. The panel's radiance
    survives, so a chamfer still throws its hard white line, and now it throws
    it all the way round the contour. That is what reference photo 13 shows a
    polished edge doing, and it is the finish this face is trying to have. The
    percentile rather than the maximum only so that a single blown lamp pixel
    cannot become a bright ring; a softbox spans a tenth of its row, so it sits
    well inside the top per cent.

    THIS IS WHY A MOVING PART GETS ONE AT ALL. The environment is the material
    here - every part is metal, and metal shows what it reflects - so lighting
    a rotating sprite under the real studio bakes the softbox into it as a
    bright side, and the app then turns the sprite and the bright side orbits
    the arbor once a turn. Nothing measured is thrown away here: the studio's
    own elevation profile is kept whole, and only the bearing it came from is
    forgotten, which is exactly the thing a mover is not allowed to remember.

    AND THEN IT IS BROUGHT BACK TO THE STUDIO'S OWN LEVEL, which is the step
    that keeps this from needing a second brightness dial next to
    WORLD_STRENGTH. Replicating the softbox round the axis multiplies the light
    in the room by about nine and a half, so a mover lit by the raw ring
    renders as a different, brighter watch from the plate it sits on. Scaling
    the ring so its mean radiance equals the source studio's says: same room,
    same amount of light in it, arranged in a circle instead of in a corner.
    One number, derived from the HDRI rather than tuned against it, so
    replacing the HDRI cannot silently change the exposure of half the face.

    Built once and cached; a 2k HDR is about eight million floats to reduce.
    """
    cached = bpy.data.images.get("studio_axial")
    if cached is not None:
        return cached

    src = bpy.data.images.load(path, check_existing=True)
    w, h = src.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    src.pixels.foreach_get(buf)
    px = buf.reshape(h, w, 4)
    rows = np.percentile(px, percentile, axis=1)

    def _lum(a):
        return float((a[..., 0] * 0.299 + a[..., 1] * 0.587
                      + a[..., 2] * 0.114).mean())

    ring_lum = _lum(rows)
    if ring_lum > 0.0:
        rows = rows * (_lum(px) / ring_lum)

    # Wider than one pixel only so no sampler has to interpolate against
    # nothing; every column is the same, which is the whole point.
    out_w = 8
    dst = bpy.data.images.new("studio_axial", out_w, h, alpha=False,
                              float_buffer=True)
    dst.colorspace_settings.name = src.colorspace_settings.name
    tile = np.repeat(rows[:, None, :], out_w, axis=1).astype(np.float32)
    tile[..., 3] = 1.0
    dst.pixels.foreach_set(tile.ravel())
    dst.update()
    return dst


def world_axial(strength=WORLD_STRENGTH):
    """`world()`, but with nothing in it that can tell one bearing from another.

    For the layers the app ROTATES. Rotation has to be a symmetry of everything
    that lights a mover, and the environment lights these parts more than the
    lamps do."""
    env = world(strength=strength, rotation=0.0)
    env.image = _ring_of()
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
    Lighting for a layer the app turns. `centre` is the arbor it turns about.

    Every source sits on that axis, which makes the setup rotationally
    symmetric about it - so rotating the layer is a SYMMETRY of the lighting,
    and one baked image is correct at every angle rather than only at the one
    it was rendered at. Bake a hand under the raking key instead and its lit
    facet turns with it, so at six o'clock it is lit from the lower right while
    every other shadow on the dial still points upper left; bake a wheel under
    it and the bright side of the rim orbits the arbor once a turn.

    It started as the hands' exception and is now the rule for everything that
    moves. `lights()` - the directional drama - is for the layers that hold
    still, where a fixed light direction is what makes the face look like one
    object photographed once.
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
#
# WHAT WAS BACKWARDS, AND HOW THE PHOTOGRAPHS SETTLED IT.
#
# captures/refs holds thirteen reference photographs and four of them answer
# this on their own: a hand-perlaged mainplate, a gilt plate with a polished
# steel lever across it, a Jaeger-LeCoultre balance cock through a display
# back, and an isolated cotes de Genève bridge shot against a plain ground.
# All four show the same two-surface arrangement, and it is the opposite of
# what these materials used to do:
#
#   THE TOP FACE CARRIES THE PATTERN and scatters light unevenly - patch by
#   patch for perlage, band by band for cotes - and stays comparatively MATTE.
#
#   THE BEVEL CARRIES THE POLISH and returns one continuous, near-white
#   specular line round the whole contour, unrelated to the top's pattern.
#
# What was here gave a near-uniform top and a hard, plain edge: the two
# surfaces exactly swapped. `_anglage` below is the fix, and it is deliberately
# not a Bevel or Pointiness node - both are Cycles-only, and tools/shade_preview
# runs EEVEE. The camera is orthographic and points straight down, so the
# cosine between a surface normal and +Z already separates the three surfaces a
# machined part has: 1 is the flat top, 0 is a vertical wall, and everything
# between the two is a chamfer. That is arithmetic on the shading normal, it
# works identically in both engines, and it needs no second mesh.

POLISH_ROUGHNESS = 0.035     # a mirror. See the note above about radiance.


def _math(nt, op, a=None, b=None):
    """One Math node, with either floats or sockets on its two inputs."""
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if hasattr(v, "is_output"):
            nt.links.new(v, node.inputs[i])
        else:
            node.inputs[i].default_value = v
    return node.outputs["Value"]


def _blend(nt, base, target, fac):
    """base + (target - base) * fac, where any argument may be a socket."""
    return _math(nt, "ADD", base,
                 _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", target, base), fac))


def _anglage(nt):
    """
    1 on a chamfer, 0 on a flat top face, 0 on a vertical wall.

    The ramp's four stops are the three surfaces: below 0.08 is a wall seen
    edge-on, 0.26 to 0.90 is a facet tilted enough to throw the light somewhere
    other than back at the camera, and above 0.965 is the flat top. The gaps
    between them are what keeps the polished line from bleeding into the top
    face on a smooth-shaded rim, where the normal sweeps continuously.
    """
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    stops = ramp.color_ramp.elements
    stops[0].position = 0.08
    stops[0].color = (0, 0, 0, 1)
    stops[1].position = 0.26
    stops[1].color = (1, 1, 1, 1)
    stops.new(0.90).color = (1, 1, 1, 1)
    stops.new(0.965).color = (0, 0, 0, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def _finish(mat, bsdf, top_rough, polish=POLISH_ROUGHNESS):
    """Pattern on the flat, mirror on the chamfer. The whole point, in one line."""
    nt = mat.node_tree
    nt.links.new(_blend(nt, top_rough, polish, _anglage(nt)),
                 bsdf.inputs["Roughness"])


def _smooth_falloff(nt, value, start, end):
    """1 at `start`, 0 at `end`, with a smoothstep between - not a hard clamp."""
    node = nt.nodes.new("ShaderNodeMapRange")
    node.interpolation_type = "SMOOTHSTEP"
    node.clamp = True
    nt.links.new(value, node.inputs["Value"])
    node.inputs["From Min"].default_value = start
    node.inputs["From Max"].default_value = end
    node.inputs["To Min"].default_value = 1.0
    node.inputs["To Max"].default_value = 0.0
    return node.outputs["Result"]


def _bump(nt, height, strength, distance=0.4):
    """
    Height into a shading normal.

    WHY EVERY PATTERN HERE GOES THROUGH ONE OF THESE AND NOT THROUGH ROUGHNESS
    ALONE. This camera is orthographic and straight down, and the strongest
    source in the scene is a 900-unit softbox hung directly over the face. A
    flat horizontal metal surface under a large, even, overhead panel returns
    very nearly that panel's radiance whatever its roughness is - so roughness
    variation on a top face is close to invisible, which is exactly what
    happened to the first cotes pass: the arm rendered as a plain grey stick
    with a correct, unreadable stripe pattern in its roughness. What a top face
    CAN show is a change of normal, because that swings the reflected ray off
    the panel and onto something else. Perlage and cotes are both a few microns
    of real relief, so this is the honest channel for them as well as the
    legible one; roughness rides along and does the rest.

    `strength` may be a socket as well as a float, which is how a pattern gets
    switched OFF along a chamfer - see `_cotes`.
    """
    node = nt.nodes.new("ShaderNodeBump")
    if hasattr(strength, "is_output"):
        nt.links.new(strength, node.inputs["Strength"])
    else:
        node.inputs["Strength"].default_value = strength
    node.inputs["Distance"].default_value = distance
    nt.links.new(height, node.inputs["Height"])
    return node.outputs["Normal"]


def _graining(mat, bsdf, base, scale, strength=0.30):
    """
    Concentric turning marks, driven into roughness. Returns the roughness.

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

    nt.links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    return _blend(nt, base, min(0.92, base + strength), wave.outputs["Fac"])


def _perlage(mat, bsdf, base):
    """
    Perlage: overlapping circular brush strokes, in a regular grid.

    An earlier attempt used a Voronoi DISTANCE_TO_EDGE, which is a field of
    RANDOM cells - it rendered as crumpled foil, because that is what it is.
    Perlage is not random: it is made by touching a rotating abrasive peg to the
    plate in orderly overlapping rows, so it is a grid of concentric rings.
    Setting a Voronoi's randomness to zero gives exactly that grid, and its
    Distance output is the radial distance from the nearest grid point; a sine
    of that distance is the rings.

    TWO THINGS THE PHOTOGRAPH SAYS THAT THE OLD VERSION MISSED.
    First, the rings have to FADE OUT toward the edge of their own stroke. A
    Voronoi cell is a square, so ringing it edge to edge draws the square, and
    the plate came back reading as a waffle rather than as a field of overlapping
    discs. Multiplying by a falloff in the same Distance is what turns a lattice
    of squares back into a scatter of circles.
    Second, the shimmer is PATCH BY PATCH: in the reference each stroke catches
    the light slightly differently from its neighbour, which is what makes
    perlage read as hand work rather than as a texture. The Voronoi's Colour
    output is a different random value per cell, so it gives exactly that, one
    roughness offset per stroke.

    Scale is in OBJECT coordinates, which span the ~250 face units the plate
    covers - not 0..1. An earlier value of 34 asked for eight thousand cells
    across the plate and delivered noise the denoiser then wiped out; 0.085 puts
    a stroke about a real millimetre across, which is what the reference plate
    has.
    """
    nt = mat.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.voronoi_dimensions = "2D"
    vor.feature = "F1"
    # Not near zero either: the reference plate is hand-perlaged and its rows
    # visibly wander, which is most of what stops the eye reading a lattice.
    vor.inputs["Randomness"].default_value = 0.32
    vor.inputs["Scale"].default_value = 0.085        # a stroke ~1 mm of watch
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])

    # A Voronoi returns its Distance in the SCALED space, not in object units,
    # so d runs from 0 at a stroke's centre to about 0.5 at the flat of its cell
    # and 0.71 at the corner, whatever the Scale is. Every constant below lives
    # in that range, which is why none of them move when the stroke size does.
    #
    # THE FADE HAS TO REACH THE CORNER. Faded out at 0.42 the strokes stopped
    # short of each other and the plate came back as a grid of raised buttons
    # with bare metal between them - which is the one thing the reference never
    # shows. Real perlage is laid overlapping, so there is no untouched plate
    # anywhere; only the boundary between strokes is visible.
    d = vor.outputs["Distance"]
    rings = _math(nt, "MULTIPLY_ADD",
                  _math(nt, "SINE", _math(nt, "MULTIPLY", d, 75.0)), 0.5)
    rings.node.inputs[2].default_value = 0.5          # 0..1 instead of -1..1
    fade = _smooth_falloff(nt, d, 0.10, 0.70)
    height = _math(nt, "MULTIPLY", rings, fade)

    patch = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(vor.outputs["Color"], patch.inputs["Color"])
    # Patch-to-patch roughness, halved for the same reason as the bump above:
    # per-stroke variation is what makes perlage read as hand work, but at
    # +-0.12 it was contributing most of the plate's luminance noise.
    rough = _math(nt, "ADD",
                  _blend(nt, base - 0.055, base + 0.065, patch.outputs["Val"]),
                  _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", height, 0.5), 0.07))

    # Shallow. Perlage is a few microns of abrasive, and at 0.55/1.4 it read as
    # a sheet of pressed studs: the reference plate's strokes are legible from
    # their rings and their boundary arcs, not from standing proud.
    #
    # SHALLOWER STILL, AND THIS ONE WAS MEASURED RATHER THAN JUDGED. Sampling
    # the preview, a clear patch of plate came back at luminance 108 with a
    # standard deviation of 11, and the lever lying on it came back at 105 -
    # so the plate's own texture was swinging wider than the entire difference
    # between the plate and the part sitting on it, and the escapement
    # disappeared into it. The perlage is the QUIET majority of the frame
    # (reference photo 1: a soft dapple that stays matte while the polished rim
    # throws the one hard line); it earns none of that variance. 0.22/0.55 ->
    # 0.11/0.42 takes the plate to about half the swing and leaves the strokes
    # perfectly legible, because what makes them read is their boundary arcs
    # rather than their depth.
    #
    # +0.03 AFTER SEEING IT IN CYCLES. The EEVEE preview that picked 0.11 read
    # fine, but the actual Cycles pass at 256 samples with denoising was
    # softer than the preview promised and the strokes blotched together
    # instead of staying legible as overlapping circles (ref: captures/refs/
    # photo 01). Bump strength only, not distance - the boundary arcs needed
    # more contrast, not a wider stroke.
    nt.links.new(_bump(nt, height, 0.14, 0.42), bsdf.inputs["Normal"])
    return rough


def _cotes(mat, bsdf, base, degrees, scale=0.026, strength=0.06):
    """
    Cotes de Geneve: evenly spaced waves across the top face of a bridge.

    From the isolated bridge in the reference set: "the top face carries evenly
    spaced wave stripes ... so brightness changes band by band as the stripes
    turn under the light", against a mirror-polished contour that owes nothing
    to the banding. The bands run ACROSS the part here rather than along it,
    because the arm is only about a millimetre of real watch wide and stripes
    lengthwise would be indistinguishable from brushing.

    THE SCALE IS SET BY WHAT THE PART CAN CARRY, and the first attempt got this
    badly wrong in a way worth recording. Cotes on the reference bridge are
    about a third of a millimetre apart on a part 17 mm across - forty bands.
    This arm is 1.1 mm wide and 7 mm long. Asking for the same PITCH gave it
    forty-five bands too, and a 1.1 mm arm with forty-five ribs on it is a
    file, not a bridge: it serrated the polished contour and turned the boss
    over the jewel into a knurled nut, which threw away the best thing in the
    aperture to gain a pattern nobody could resolve. What the part can carry is
    a dozen soft bands along its length, shallow enough that the anglage still
    reads as one continuous line. Bands are sized to the PART, not to the
    finishing operation's own pitch.

    `degrees` rotates the bands in the face's own frame. Object coordinates are
    face coordinates for a placed CAD solid - the STL arrives already positioned
    and render_lib never moves it - so this is an angle in the picture, not in
    some per-part space that would have to be tracked.
    """
    nt = mat.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(degrees))
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.wave_profile = "SIN"
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 0.4
    wave.inputs["Detail"].default_value = 1.0

    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    fac = wave.outputs["Fac"]
    # THE DEPTH HAS TO SCALE WITH THE PITCH, and 0.16/0.30 did not: it was
    # inherited from the fine-pitch version and left behind when the bands were
    # widened, so the arm rendered as a plain grey stick with the côtes
    # technically present and optically absent. A Bump node's slope is the
    # height's gradient, so a wave whose period is 16 face units instead of 1.5
    # needs roughly ten times the distance to tilt the surface by the same
    # angle - and the tilt is the whole mechanism, because the overhead softbox
    # subtends about 20 degrees, so a normal that swings less than ten never
    # leaves it and never changes what it reflects. 0.45/1.5 swings each band
    # just off the panel and back, which is the band-by-band brightness change
    # reference photo 13 shows, and it is still gentle enough that the polished
    # contour stays one continuous line rather than a row of teeth.
    #
    # AND THE BANDS STOP AT THE BEVEL, which is the whole reason the previous
    # attempt "wrecked the contour and the boss". A bump perturbs the normal
    # everywhere on the part, chamfer included, so every band that crossed the
    # rim put a notch in the one surface that is supposed to be a single
    # unbroken mirror line - the arm came back with a scalloped edge and a
    # boss like a knurled nut. That is not a scale problem, it is a MASKING
    # problem, and it is also just what the part is: côtes are milled into the
    # flat top and the anglage is filed on afterwards, which removes them along
    # the bevel by construction. Multiplying the bump strength by (1 - anglage)
    # says exactly that, and it is why the band count below can go back up
    # without the contour paying for it.
    flat = _math(nt, "SUBTRACT", 1.0, _anglage(nt))
    nt.links.new(_bump(nt, fac, _math(nt, "MULTIPLY", flat, 0.42), 1.5),
                 bsdf.inputs["Normal"])
    return _blend(nt, base - strength, base + strength, fac)


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

    # The escapement, and it is DELIBERATELY the dimmest metal in the aperture.
    #
    # Real movement finishing is a two-tier system: almost everything is matte
    # and quiet - perlage, brushed stripes, flat rhodium - and only a few chosen
    # elements get the bright treatment, because the point of finishing is to
    # decide how many things compete for the eye at once. This face had it
    # exactly backwards. The escape wheel and the lever are the fastest-jumping
    # things in the opening and they were wearing the brightest metal on it,
    # against a plate half their luminance. Attention capture scales with
    # contrast, so the two parts that most needed to recede were shouting.
    #
    # Rhodium-grey. It sits between the plate and the bright bridges, which is a
    # three-tier hierarchy rather than a two-tier one, and that is the whole
    # difference between finishing and suppression.
    #
    # It was taken down to 0.395 first, which was a band-aid over a layout
    # problem: three wheels packed corner to corner with no quiet anywhere, so
    # the only lever left was to turn the fast ones down. At that value the
    # escapement was barely separable from the plate - the movement stopped
    # being chaotic by becoming muddy, which is not the same as calm. With the
    # assembly scaled to leave real margin, the hierarchy comes from the LAYOUT
    # and the metal can look like metal again.
    #
    # Now DARKER than the plate rather than lighter, and for a reason that only
    # appeared once the plate was brought up: at 0.550 against a 0.430 plate the
    # lever and the escape wheel were within a few percent of their background
    # and dissolved into it. A polished steel part photographs DARK - it has no
    # diffuse component, so it shows the room, and the room is mostly not a
    # softbox - with its bevels drawing the bright lines. That is what every
    # escapement in the reference set looks like, and it is now what separation
    # is made of here: contrast against the plate plus anglage, not brightness.
    # Roughness matters as much as the colour here, and for a reason the
    # straight-down camera makes: a smooth flat top reflects the overhead
    # softbox almost whole, so at 0.18 the lever came back BRIGHTER than a
    # 0.430 plate however far its base colour was taken down. Matching the
    # plate's scatter is what lets the base colour actually decide the tone.
    # ...and then darker again, because 0.345 was still not enough and the
    # preview says so in numbers: plate 108, escape wheel 104, lever 105. Three
    # counts of luminance apart, against a plate whose perlage was swinging 11.
    # The part was not "low contrast", it was INVISIBLE, and no amount of
    # finishing on a shape nobody can find is worth anything. 0.205 puts the
    # escapement about a quarter below the plate, which is where reference
    # photo 2 has its polished steel lever sitting against a perlaged plate:
    # "its top face stays a flat, comparatively dull grey". The roughness comes
    # back down with it - the darkness is now doing the separating, so the
    # surface is free to be as polished as the part really is, and a smoother
    # top is what lets the anglage read as a line rather than a smudge.
    # ...and then down again with the plate, by the same factor, because what
    # this number was ever set against is the plate behind it. See "plate"
    # below: the plate had to come down to stop the opening being the brightest
    # thing on the dial, and holding the escapement still while it moved would
    # have re-run the failure recorded three paragraphs up with the signs
    # swapped - the lever brighter than its background instead of equal to it.
    # 0.205/0.430 was measured; 0.122/0.255 is the same fraction.
    #
    # AND THAT LAST STEP WAS THE MISTAKE, which is only obvious with the
    # numbers beside it. Scaling the escapement down with the plate kept the
    # RATIO the earlier work had measured and threw away the reason for it. The
    # ratio was never the point: it was chosen when the plate was pale, to stop
    # a bright part dissolving into a brighter background. A dark plate does
    # not need defending from a steel part, and holding the fraction while the
    # plate halved took the escapement to a tone it cannot carry any shading
    # in.
    #
    # Measured off Assets/, inside the aperture, at 0.096: bare plate metal
    # 108.7 with a scatter of 10.4, the plate's own bores 47.2, and the escape
    # wheel 82.2 / 83.2 / 85.5 at its tenth, fiftieth and ninetieth percentile.
    # Three counts from end to end. Every tooth, every chamfer and both pallet
    # stones were inside three counts of luminance, so the part was not dim, it
    # was FLAT - a silhouette at the same tone as the holes drilled through the
    # plate beside it, which is exactly how the wall read it.
    #
    # A metal has no diffuse term, so its rendered radiance is the environment
    # multiplied by this colour: the base colour scales the part's own internal
    # contrast as well as its level. At 0.096 the whole of the escape wheel's
    # modelling was being multiplied into the bottom twentieth of the range.
    #
    # So it goes ABOVE the plate now instead of below it, which is what a
    # polished steel escapement on a dark rhodium plate actually looks like,
    # and is the same rule as before with the plate on the other side of it:
    # readable AGAINST the background, in whichever direction the background
    # leaves room. 0.249 puts the escape wheel at about 132 against a plate at
    # 108.7 - two and a half of the plate's own scatter above it, eighty-five
    # counts clear of the bores, and still below the brass fourth wheel at 143,
    # so the finishing hierarchy the paragraphs above argue for survives: the
    # escapement is the quietest of the parts that read as metal rather than
    # the brightest of the ones that read as holes.
    #
    # The roughness does not move. One variable, and it was settled against
    # this same rig for reasons that have not changed.
    "escapement": ((0.249, 0.257, 0.280), 1.0, 0.22),
    "case":     ((0.760, 0.775, 0.810), 1.0, 0.150),
    "index":    ((0.840, 0.850, 0.880), 1.0, 0.055),
    "gold":     ((0.860, 0.660, 0.290), 1.0, 0.12),

    # The balance bridge. Its own metal rather than plain "steel" because it is
    # the one part that gets cotes across the top: everything else wearing
    # "steel" here is turned (a staff, a roller, a pinion) and wants the lathe's
    # concentric marks instead. Same alloy, different finishing operation, which
    # is exactly the distinction a movement is finished on.
    "bridge":   ((0.700, 0.715, 0.750), 1.0, 0.21),

    # The plate. It was brought UP to 0.430 when the aperture still held the
    # OM10's decorated cock and the plate read as a hole behind it; that fight
    # ended when the cock was replaced by a thin arm, and 0.430 then turned out
    # to be winning a different one. tools/wall_sheet.py measures the opening
    # against the dial touching it and read 1.177 - the aperture BRIGHTER than
    # the dial, on a face whose aperture is a fifth of its width. From the
    # doorway that is the only thing on the wall.
    #
    # Every open-heart photograph in captures/refs has it the other way: the
    # Orient measures 0.588 and the Tissot 0.689, and both of those are silver
    # dials, so the opening is not dark by accident - it is a recess, cut into
    # a lacquered dial, with a movement sitting well below the crystal. A dial
    # this face's own dark blue needs it darker still to read the same way.
    #
    # So: deep rhodium-grey, which is what a mainplate plated for the dial side
    # actually is, and which reference photo 1's plate is once you stop reading
    # its studio highlight as its colour. The perlage and the polished bevel do
    # not change - a matte pattern on a dark metal is still a matte pattern -
    # and the drilling that arrived with the real plate does more of the work
    # than the colour does: seventeen real bores inside the opening, each one a
    # well 6.5 units deep over a floor.
    "plate":    ((0.200, 0.206, 0.219), 0.92, 0.30),
    "floor":    ((0.105, 0.109, 0.122), 0.60, 0.60),
}

# Which way the balance bridge's arm runs, in the picture, so the cotes cross it
# rather than run along it. The arm goes from the balance arbor at face
# (296.2, 464.2) to its foot at (224.5, 509.2); object coordinates are face
# coordinates with y negated, so that direction is (-71.7, -45.0) there, and the
# bands are turned to lie across it.
BRIDGE_COTES_DEG = 148.0


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

    # The top face's own finish first, then the polished chamfer over it. Order
    # matters: _finish takes whatever the top face ended up as and blends the
    # mirror in only where the surface is tilted, so a part keeps its perlage or
    # its turning marks everywhere except on the bevel.
    if kind == "plate":
        top = _perlage(m, b, rough)
    elif kind == "bridge":
        top = _cotes(m, b, rough, BRIDGE_COTES_DEG)
    elif kind == "brass":
        top = _graining(m, b, rough, 90.0, 0.26)
    elif kind == "steel":
        top = _graining(m, b, rough, 130.0, 0.16)
    else:
        # Everything else keeps its flat roughness, and "escapement" keeps it on
        # purpose. The lever is a stamped and polished part, not a turned one,
        # and the reference photograph of one crossing a plate is explicit: "its
        # top face stays a flat, comparatively dull grey" while the edges throw
        # a hard white line. Concentric turning marks on it were describing a
        # lathe operation it never saw.
        top = rough

    # Anglage on the movement's own metals only. The case, the indices and the
    # hands were settled against this same studio under the existing materials
    # and nothing in the reference pack says they are wrong; widening the change
    # to them would be a second, unmeasured edit riding along with this one.
    if kind in ("plate", "bridge", "brass", "steel", "escapement", "blued"):
        _finish(m, b, top)
    elif top is not rough:
        m.node_tree.links.new(top, b.inputs["Roughness"])
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

    AND NEITHER IS THE RETRIANGULATION, which is newer and cost a day of the
    wall looking wrong. Blender fills a ring-shaped curve by scanfill, and a
    scanfill of an annulus has to join the hole to the outer boundary
    somewhere. It joins it at the two splines' FIRST VERTEX - and every ring in
    this face is generated by escapement_geometry.disc, which starts at twelve
    o'clock. What that leaves behind is a couple of enormous slivers: on the
    bezel, two cap triangles of 640 square units against a median of 102; on
    the dial, two of four thousand against sixteen.

    Coplanar slivers are invisible on their own. Run a 3.4-unit bevel over
    them with use_clamp_overlap off and they are not: the bevel has no room to
    work in along a sliver's long thin edge, so it produces overlapping and
    inverted geometry there, and the render comes back with holes and tongues
    laid across the top of the polished case ring. The user marked it on the
    wall as the bezel issue; the same defect drew the dark radial seam from
    twelve down the dial to the aperture, and a smudge at the top of the
    rehaut. All three are one bug, at one azimuth, for one reason.

    Diagnosis, in case it comes back: with a matte material, a flat grey world
    and no lamps at all - nothing left that could shade anything - the streaks
    were still there and still at twelve. That rules out the environment, the
    lights, the shadow catcher and the shading normals in one render, and
    leaves the mesh. Setting the chamfer to nothing cleared it, which says
    which part of the mesh.

    beautify_fill rotates edges within a set of triangles to improve their
    shape. It moves no vertex, so the outline, the thickness and the chamfer
    width are all exactly what they were; it only stops the bevel being asked
    to work along a sliver. It is restricted to the FLAT CAPS, because those
    are the faces the curve fill made and the only ones that can be
    retriangulated without changing a surface: rotating an edge between two
    triangles that are not coplanar would move the shape, and this function
    also runs over the balance bridge, which arrives as a real solid.

    The other cure - use_clamp_overlap = True - was tried and rejected. It
    clears the streaks and takes the chamfer with it: the whole case reads as
    a flat ring, at the same mean luminance as a render with no chamfer asked
    for at all.
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
    caps = [f for f in bm.faces if len(f.verts) == 3 and abs(f.normal.z) > 0.999]
    if caps:
        bmesh.ops.beautify_fill(bm, faces=caps, edges=bm.edges[:])
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


def _import_stl(path, name):
    """
    A real solid, already placed, from the CAD assembly.

    The mesh arrives in face coordinates with its z already set, because
    models/step/movement.step.py did the placing - so this must NOT move, scale
    or rotate it. Anything it did here would be a second opinion about where a
    part goes, and the render's rotation centres come from the same placement.

    SHADE SMOOTH BY ANGLE IS THE WHOLE JOB. An STL carries no normals, so every
    facet renders flat, and a balance rim tessellated at 0.004mm becomes a
    many-sided polygon catching a different highlight on every side. Smoothing
    by angle is what makes a turned surface read as turned while leaving a
    chamfer's edge sharp - which is the one distinction the entire point of
    using real CAD depends on. Smoothing everything would round the chamfers
    away; smoothing nothing leaves a faceted hoop.
    """
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.stl_import(filepath=path)          # Blender 4.2+
    except AttributeError:
        bpy.ops.import_mesh.stl(filepath=path)        # older operator name
    fresh = [o for o in bpy.data.objects if o not in before]
    if not fresh:
        raise SceneError("%s: importing %s produced no object" % (name, path))

    obj = fresh[0]
    if len(fresh) > 1:
        # One STL should be one solid; join rather than silently render a part
        # of it, and say so, because it means the export changed shape.
        print("[render] %s: STL held %d objects, joining" % (name, len(fresh)))
        bpy.context.view_layer.objects.active = obj
        for o in fresh:
            o.select_set(True)
        bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active
        for o in bpy.context.selected_objects:
            o.select_set(False)

    obj.name = name
    obj.location = (0.0, 0.0, 0.0)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(31))
    except AttributeError:
        bpy.ops.object.shade_smooth(use_auto_smooth=True,
                                    auto_smooth_angle=math.radians(31))
    obj.select_set(False)
    return obj


def build_part(spec):
    """
    Profile rings to a solid - or, where the part has one, the real CAD solid.

    Rings become splines on one curve object, so Blender's fill handles the
    holes for free - a crossing in the escape wheel is a hole because it is a
    second spline, exactly as it is a second figure in XAML.
    """
    # A part with an STL is a measured solid out of the OM10 movement, not an
    # outline to be extruded. Its chamfers, its turned steps and its tooth
    # flanks are already there, so none of the extrude-and-bevel path below
    # applies - and applying it would be actively wrong, since a blanket bevel
    # on real geometry rounds off the very edges that were the reason to use it.
    if spec.get("stl"):
        obj = _import_stl(spec["stl"], spec["name"])
        spec["_chamfer_applied"] = 0.0
        # ...unless the solid is one WE extruded, which has no chamfer to
        # protect. models/step/movement.step.py's balance bridge is a plain
        # prism because OCCT refuses to chamfer its outline at any width, and
        # the reference photographs make that edge the single brightest surface
        # on the part - the continuous mirror line an anglage throws. The
        # manifest carries the width so the decision stays with the part.
        if spec.get("bevel"):
            obj = _chamfer(obj, min(spec["bevel"],
                                    chamfer_limit(spec["thickness"])))
            spec["_chamfer_applied"] = spec["bevel"]
        obj.data.materials.append(material(spec["material"]))
        return obj

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

    FOR STATIC LAYERS ONLY, and the comment that used to sit here said the
    opposite: "this is what lets a moving part carry its own shadow". It does,
    and that was the bug. Render the balance above one and the image comes back
    as the wheel PLUS the shadow it casts, so when XAML turns the image the
    shadow orbits the arbor - measured at 46% of that layer's alpha, sitting 18
    units off the pivot. No still frame shows it and nothing else on the wall
    is visible while it happens.

    A cast shadow belongs to the surface it lands on, which is the mainplate,
    which never moves. blender_face.py bakes them there instead, by letting the
    movers cast into the base pass while staying invisible to the camera. What
    is left for this disc is the cock, the case and the hand cap - the layers
    that are painted once and held still, where a shadow is free to point
    wherever the light says.
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
