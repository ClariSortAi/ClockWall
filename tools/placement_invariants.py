"""Geometric assertions on the placed movement, checked after every placement change.

    .venv-cad\\Scripts\\python.exe tools/placement_invariants.py    # everything
    python tools/placement_invariants.py --assets                   # the PNGs only
    .venv-cad\\Scripts\\python.exe tools/placement_invariants.py --cad

TWO HALVES. The first half reads the placed CAD and asks whether the movement
could work: jewel on arbor, fork at the balance, screws in holes, stones
locking. It needs trimesh and the STLs, so it runs under `.venv-cad`. The
second half reads `Assets/*.png` and asks whether the layers the APP MOVES can
survive being moved. It needs only numpy, PIL and scipy, so it runs under plain
`python` and is cheap enough to gate every render - which is why `--assets`
exists and why render.ps1 calls it.

WHY THE SECOND HALF EXISTS. Every check above it passed while the wall still
showed wobbling gears, because all of them are about WHERE a part is and the
defect was about what is PAINTED ON IT. The rendered rim centres sit within
0.7px of the pivots the XAML turns them about - placement was never the
problem. What was wrong is that each rotating sprite carried a cast shadow and
a directional highlight that belong to the world, not to the wheel: rotate the
sprite and the shadow orbits the wheel and the specular spins with the teeth.
Not one still frame shows it. The user watching the wall sees nothing else.

So an image gate has to ask a question a still cannot answer: what does this
layer do WHEN TURNED? Two forms of it, because the movers are two kinds of
thing:

  A ROTATIONALLY SYMMETRIC MOVER (a wheel) has, by its own geometry, its mass
  centred on its arbor. Any displacement of its alpha-weighted centroid from
  the pivot is therefore shading rather than shape, and it is exactly the
  quantity that swings round the pivot once per turn. One number, no
  judgement, and it is the check the brief asked for.

  AN ASYMMETRIC MOVER (a lever, a hairspring, a hand) is legitimately
  off-pivot, so that test would fail on every one of them for the wrong
  reason. What is still illegitimate is alpha sitting where the part is NOT:
  paint the part's own silhouette, grow it by a small margin so anti-aliasing,
  chamfer glow and a tight contact shadow are all inside it, and any weight
  left outside cannot be the part. It is a shadow cast onto whatever the
  render put underneath, and it is riding on a sprite that turns. That
  measure never looks at where the part's mass is, so the part's own
  asymmetry cannot trip it.

WHICH LAYERS ARE CHECKED IS READ OUT OF THE XAML, not listed here. Every Image
in Controls/OpenworkedFace.xaml that carries a RotateTransform is a mover, and
its CenterX/CenterY is the pivot the app will actually turn it about - which is
the number that has to be measured against, not profiles.json's. A layer that
gains a RotateTransform therefore gains a gate on the same edit, and one whose
symmetry has not been declared below fails rather than being skipped.

WHY THIS EXISTS. A 13.2-degree rotation-sign bug sat in the placement for
hours, because nothing asserted what a correct placement actually implies:
that the cock's jewel bore sits ON the balance arbor, that the fork points at
the balance it drives, that a screw threads into the hole drilled for it, and
that the escapement can lock at all. Each of those held up as the eventual
diagnosis, but only after being run once by hand, mid-session, while chasing
a symptom. HANDOVER-REALISM.md is explicit that this is the fix: "those
assertions are three lines each ... they belong in a file that runs after
every placement change." This is that file.

A WEAK CHECK IS WORSE THAN NO CHECK. The same handover describes testing
"nearest vertex to the balance axis is 2.98 units" after placing the cock and
calling it confirmed - a test that cannot fail, because the cock's boss is
near the balance under any rotation of the cock. Every check below is instead
built to fail: it names a SPECIFIC feature (the jewel bore, not the cock's
boss; the fork's horns, not its centre of mass) and a SPECIFIC relationship
that a wrong placement would visibly break.

WHAT IT READS. captures/cad/manifest.json and the STLs beside it - the FINAL
placed movement, already scaled, rotated and translated into face coordinates
by models/step/movement.step.py via cad_parts.py. Nothing here re-derives the
placement from om10_layout; that would be a second opinion about where a part
goes, which is exactly the kind of thing the rotation bug was. It reads what
was actually written to disk and asks whether it is self-consistent - the
same reason render_lib.audit() checks the evaluated mesh instead of the code
that built it.

The one exception is the two cock screw holes: escapement_geometry.COCK_SCREWS
and movement.step.py's STACK both carry that pair of OM10-plane coordinates
as independent hand-written literals, so checking a screw against its hole
also checks that those two files still agree with each other.

RUN THIS after any change to STACK, om10_layout constants, ESCAPE_BEARING, or
anything else upstream of cad_parts.py's manifest - before spending eight
minutes on a full render to find out whether the answer changed. It runs in
about a second.

Exits 0 with everything printed "ok"; exits non-zero and lists every failing
invariant by name otherwise, each with measured vs. expected.
"""

import json
import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# The CAD half's dependencies, imported softly so the ASSET half can run under
# a plain interpreter. trimesh, shapely and build123d live in .venv-cad only,
# and render.ps1 - which is what has to run the asset gate on every render -
# uses the system python. Failing here would make a cheap PNG check
# unavailable exactly where it is cheapest to run.
try:
    import trimesh                                             # noqa: E402
    from trimesh.path import polygons as tp                    # noqa: E402

    import escapement_geometry as eg                           # noqa: E402
    import om10_layout as L                                    # noqa: E402

    CAD_IMPORT_ERROR = None
except ImportError as exc:                                     # pragma: no cover
    CAD_IMPORT_ERROR = exc

CAD = os.path.join(ROOT, "captures", "cad")
ASSETS = os.path.join(ROOT, "Assets")
FACE_XAML = os.path.join(ROOT, "Controls", "OpenworkedFace.xaml")

# The face's own coordinate space, and the one every measurement below is
# reported in. Assets render at 1920px for the same 640 units, so a face unit
# is 3 asset pixels and "1 unit" is a third of a pixel on the wall.
FACE = 640.0

FAILURES = []


def check(name, ok, detail):
    print("[%-4s] %-46s %s" % ("ok" if ok else "FAIL", name, detail))
    if not ok:
        FAILURES.append(name)


def _manifest():
    with open(os.path.join(CAD, "manifest.json")) as f:
        return json.load(f)


def _placed(name):
    """
    A part's mesh, already placed, as vertices in FACE coordinates (x, y down).

    captures/cad/*.stl is exported straight from the placed build123d assembly
    in Blender's y-up convention (see cad_parts.py / movement.step.py's
    `place()`), so every y is negated on the way in - the same flip
    render_lib does on the way into Blender, undone.
    """
    mesh = trimesh.load(os.path.join(CAD, "%s.stl" % name), process=False)
    v = mesh.vertices
    return np.column_stack([v[:, 0], -v[:, 1]])


def _circle_fit(pts):
    """Kasa least-squares circle through a ring of points: (cx, cy, r)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    r = math.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 0.0))
    return cx, cy, r


def _angdiff(a, b):
    """Signed shortest angular difference a - b, in (-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


# ------------------------------------------------------- 1. the cock's jewel bore

def check_cock_jewel(manifest):
    """
    The cock's balance jewel bore must sit on the balance arbor.

    The cock's silhouette carries several holes - the jewel bore and two
    screw holes at least. Picking "the biggest" or "the first" would
    silently track the wrong one if the mesh ever changes, so instead every
    interior ring is circle-fit and the one whose fitted centre lands
    nearest the balance pivot is taken to be the bore. If that is wrong, the
    reported distance will be enormous rather than merely off, because no
    other hole on the cock is anywhere near the balance arbor.
    """
    balance = manifest["pivots"]["balance"]
    scale = manifest["scale"]

    poly = tp.projected(trimesh.load(os.path.join(CAD, "cock.stl"), process=False),
                        normal=[0, 0, 1])
    best = None
    for ring in poly.interiors:
        pts = np.array(ring.coords)
        face_pts = np.column_stack([pts[:, 0], -pts[:, 1]])
        cx, cy, r = _circle_fit(face_pts)
        d = math.hypot(cx - balance[0], cy - balance[1])
        if best is None or d < best[0]:
            best = (d, cx, cy, r)
    d, cx, cy, r = best

    tol_mm = 0.05
    d_mm = d / scale
    check("cock jewel bore on balance arbor",
          d_mm <= tol_mm,
          "bore centre (%.2f, %.2f) is %.4f mm from arbor (%.2f, %.2f); tolerance %.2f mm"
          % (cx, cy, d_mm, balance[0], balance[1], tol_mm))


# --------------------------------------------------- 2. the pallet fork's long axis

def check_fork_axis(manifest):
    """
    The pallet fork's long axis must point at the balance it drives.

    A lever escapement's entire mechanical connection to the balance runs
    through one point: the fork's horns cradle the roller jewel on the
    balance staff. "Long axis" is deliberately NOT a moment-of-inertia fit of
    the whole lever body - the lever carries most of its mass over the
    pallet stones, near the escape wheel, so a PCA axis leans toward the
    wrong end by about 3-4 degrees here. The fork's tip is instead the point
    of the lever mesh physically nearest the balance arbor - the horns, by
    construction - and what is checked is the bearing from the pallet arbor
    to that point against the bearing from the pallet arbor to the balance
    arbor. This is exactly the relationship the rotation-sign bug broke: it
    spun the lever about its own pivot by roughly twice the intended angle.
    """
    pallet = manifest["pivots"]["pallet"]
    balance = manifest["pivots"]["balance"]
    pts = _placed("lever")

    d = np.hypot(pts[:, 0] - balance[0], pts[:, 1] - balance[1])
    tip = pts[int(np.argmin(d))]

    bearing_tip = L.bearing_of(tip[0] - pallet[0], tip[1] - pallet[1])
    bearing_balance = L.bearing_of(balance[0] - pallet[0], balance[1] - pallet[1])
    delta = _angdiff(bearing_tip, bearing_balance)

    tol_deg = 15.0
    check("pallet fork points at the balance",
          abs(delta) <= tol_deg,
          "fork tip bears %.2f deg from the pallet arbor, balance bears %.2f deg "
          "(%.2f deg off); tolerance %.1f deg" % (bearing_tip, bearing_balance, delta, tol_deg))


# ------------------------------------------- 2b. the plate is drilled for this movement

def check_plate_bores(manifest):
    """
    Every pivot must run in a bore the OM10 actually drilled, and the bore
    must be able to take the stone.

    This is the invariant the plate change stands on. The mainplate is not
    positioned against the movement by eye or by fitting - it goes through the
    SAME similarity transform the parts do, so if both are the OM10's then a
    real bore has to arrive under every real pivot. It does, to within 0.05
    face units, which is 4 microns of watch and about a sixtieth of a rendered
    pixel. Nothing was aimed there.

    The second half is what makes it a check rather than a coincidence
    detector: the bore has to be wide enough for the jewel. It is, and barely -
    the escape and pallet bores measure 5.77 against a 5.91-unit stone, which
    is the interference a jewel is pressed in with. A plate scaled or rotated
    even slightly wrong would break one of the two halves.
    """
    plate = manifest.get("mainplate")
    if plate is None:
        check("mainplate drilling present", False,
              "captures/cad/manifest.json has no mainplate - re-run cad_parts.py")
        return

    jewel = next(p for p in manifest["parts"] if p["name"] == "jewel_e")
    jewel_r = (jewel["bbox"][2] - jewel["bbox"][0]) / 2.0
    scale = manifest["scale"]

    tol = 0.5                       # face units
    worst = max(plate["bores"].items(), key=lambda kv: kv[1][3])
    arbor, (_bx, _by, _br, d) = worst
    check("every pivot runs in a real OM10 bore",
          d <= tol,
          "worst is %s at %.3f face units (%.4f mm); tolerance %.1f units "
          "over %d bores" % (arbor, d, d / scale, tol, len(plate["bores"])))

    # A stone that cannot enter its hole is a plate belonging to another watch.
    tight = {k: v[2] for k, v in plate["bores"].items() if v[2] < jewel_r * 0.9}
    check("every bore can take the jewel",
          not tight,
          "jewel radius %.2f units; smallest bore %.2f (%s)%s"
          % (jewel_r, min(v[2] for v in plate["bores"].values()),
             min(plate["bores"], key=lambda k: plate["bores"][k][2]),
             "" if not tight else "; too tight: %s" % tight))


# --------------------------------------------------- 3. cock screws in plate holes

def check_screws_in_holes(manifest):
    """
    Each cock screw must land inside the hole drilled for it.

    escapement_geometry.COCK_SCREWS (the plate's holes) and
    models/step/movement.step.py's STACK (the screws' own placement) are two
    independent hand-written copies of the same two OM10-plane coordinates,
    kept in agreement only by whoever edits one remembering to edit the
    other. This is the check that would catch it if they stopped agreeing -
    the earlier version of this hole was drawn from a bearing-and-radius rule
    that had nothing to do with where the real cock's screws are, and it took
    a stray render to notice the screws threaded into open plate 40 units away.
    """
    scale = manifest["scale"]
    # Face units. See escapement_geometry.plate_openings(): the cock screw
    # bores are drawn at this radius around the same COCK_SCREWS points.
    hole_r = 4.2

    for i, (sx, sz) in enumerate(eg.COCK_SCREWS, start=1):
        hole = eg._PLACE.to_face(sx, sz)
        pts = _placed("screw_%d" % i)
        cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
        d = math.hypot(cx - hole[0], cy - hole[1])
        check("screw_%d inside its plate hole" % i,
              d < hole_r,
              "screw centre is %.3f face units (%.4f mm) from the hole centre "
              "(%.1f, %.1f); hole radius %.1f units"
              % (d, d / scale, hole[0], hole[1], hole_r))


# ------------------------------------------------- 4/5. the pallet stones and lock

def check_pallet_stones(manifest):
    """
    Both pallet stones must reach inside the escape wheel's tooth-tip circle,
    by nearly equal amounts, at a span that is an odd number of half
    tooth-spaces.

    REACH. Unless a stone's innermost point sits inside the circle every
    tooth tip sweeps, the wheel can complete a full turn without ever
    meeting it - there is no escapement, only two wheels sharing a plate.

    EQUAL LOCK. Near-equal reach on entry and exit is what a correctly SET
    escapement has; a stone catching much deeper than its partner is a fork
    that is not centred between its banking pins.

    ODD SPACING. escapement_geometry.py's own reasoning is that the tooth
    count between the stones must be odd or a tooth arrives pointing straight
    into the gap between them and the wheel locks against nothing, in either
    direction - it could not alternate. Rounding the measured span to the
    nearest half-tooth count and checking that count is odd is exactly that
    test, done on the placed geometry instead of assumed from the design.
    """
    scale = manifest["scale"]
    escape = manifest["pivots"]["escape"]
    teeth = manifest["teeth"]["escape"]
    half_tooth_deg = 360.0 / (2 * teeth)

    escape_pts = _placed("escape")
    tip_r = float(np.hypot(escape_pts[:, 0] - escape[0], escape_pts[:, 1] - escape[1]).max())

    locks, bearings = {}, {}
    for name in ("stone_a", "stone_b"):
        pts = _placed(name)
        d = np.hypot(pts[:, 0] - escape[0], pts[:, 1] - escape[1])
        i = int(np.argmin(d))
        locks[name] = (tip_r - d[i]) / scale
        bearings[name] = L.bearing_of(pts[i, 0] - escape[0], pts[i, 1] - escape[1])

    for name in ("stone_a", "stone_b"):
        check("%s reaches inside the escape wheel tip circle" % name,
              locks[name] > 0.0,
              "lock depth %.4f mm (must be positive to ever contact a tooth)" % locks[name])

    tol_mm = 0.05
    diff = abs(locks["stone_a"] - locks["stone_b"])
    check("pallet stones lock by nearly equal amounts",
          diff <= tol_mm,
          "stone_a %.4f mm, stone_b %.4f mm, differ by %.4f mm; tolerance %.2f mm"
          % (locks["stone_a"], locks["stone_b"], diff, tol_mm))

    span = abs(_angdiff(bearings["stone_b"], bearings["stone_a"]))
    half_spaces = span / half_tooth_deg
    nearest = round(half_spaces)
    is_odd = nearest % 2 == 1
    close = abs(half_spaces - nearest) <= 0.3
    check("stone span is an odd number of half tooth-spaces",
          is_odd and close,
          "span %.2f deg = %.2f half tooth-spaces on a %d-tooth wheel -> "
          "nearest whole count %d (%s)"
          % (span, half_spaces, teeth, nearest, "odd" if is_odd else "EVEN"))


# ============================================================================
#  BAKED DIRECTIONALITY IN THE LAYERS THE APP MOVES
#
#  Everything above this line is about the CAD. Everything below is about the
#  rendered PNGs, and about one question: can this layer be rotated about its
#  pivot without the lighting rotating with it?
# ============================================================================

# What counts as the part rather than as light falling near it. Chosen against
# the layers themselves: every solid component reaches full opacity somewhere,
# and the hairspring - the thinnest thing rendered, a wire about a pixel and a
# half wide at 1920 - peaks at 0.80, so a half-alpha floor keeps its coils and
# nothing softer. Raising it drops the spring; lowering it starts admitting the
# shadow, which peaks around 0.47.
SOLID_ALPHA = 0.5

# How far outside the part's own silhouette still counts as the part, in face
# units. It has to clear the anti-aliased edge (a pixel or two, so about half a
# unit), the chamfer glow that a polished edge legitimately throws, and a
# contact shadow tight enough to read as the part sitting ON something rather
# than as a shadow orbiting it. Three units is about a millimetre of movement.
# A shadow displaced less than that is not what anybody can see wobbling; the
# ones measured here are displaced ten to twenty times further.
PART_MARGIN = 3.0

# How much of a mover's alpha may sit outside its own footprint. This is a
# WEIGHT share, so it cannot be gamed by spreading the same shadow thinner -
# only by making it about ten times fainter, which is the fix.
STRAY_FRACTION_MAX = 0.05

# How far a symmetric mover's centroid may sit from the pivot it turns about,
# and the distance below which a stray lobe is centred enough on the pivot to
# be harmless. Both in face units: a halo centred on the arbor rotates into
# itself and nobody sees it turn, which is precisely what the two smear layers
# rely on.
CENTROID_MAX = 1.0
ORBIT_MIN = 1.0

# Whether each moving layer's own shape is centred on its arbor. This is the
# one hand-written table here, because it is a judgement about the PART and
# cannot be read off the pixels - a wheel whose shadow is heavy enough looks
# exactly like an asymmetric part to any measurement that does not already
# know which it is.
SYMMETRIC = {
    # A rim with two arms and their timing screws: two-fold symmetric about the
    # staff, so its own mass sits on the pivot to within a rounding error.
    "movement-balance.png": True,
    # Twenty teeth on a hub. Twenty-fold, and its smear is the same wheel.
    "movement-escape.png": True,
    "movement-escape-blur.png": True,
    # Wheel, crossings and pinion, all concentric with the arbor.
    "movement-train.png": True,
    # A lever: pallet stones at one end, horns at the other, and no symmetry at
    # all about the pallet arbor between them.
    "movement-fork.png": False,
    "movement-fork-blur.png": False,
    # A spiral is nearly symmetric, but the stud and the outer terminal are
    # not, and the wire never reaches full opacity - a centroid test on this
    # layer would be measuring the shadow with the spring as a rounding error.
    "movement-spring.png": False,
    # A hand is entirely on one side of the pivot. That IS the shape.
    "hand-hour.png": False,
    "hand-minute.png": False,
    "hand-second.png": False,
}


def _layers():
    """
    Every layer the face paints, in paint order, as (asset, pivot, label).

    `pivot` is None for a layer the app never turns. Read out of
    Controls/OpenworkedFace.xaml rather than listed here, for the reason the
    .xaml's own header gives: those CenterX/CenterY attributes are a hand-copy
    of the geometry, and they are what the app actually turns the image about.
    Measuring against profiles.json instead would be measuring against the
    number that was MEANT to be there.

    A layer with no RotateTransform is reported and not checked - the two
    held-still smears (balance and spring) are exactly that, and holding a
    shadow still is the fix rather than the fault.
    """
    xn = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    out = []
    for image in ET.parse(FACE_XAML).getroot().iter():
        if not image.tag.endswith("}Image"):
            continue
        source = image.get("Source")
        if not source:
            continue
        rotate = None
        for child in image:
            if child.tag.endswith("}Image.RenderTransform"):
                for grand in child:
                    if grand.tag.endswith("}RotateTransform"):
                        rotate = grand
        name = os.path.basename(source)
        if rotate is None:
            out.append((name, None, image.get(xn, name)))
        else:
            out.append((name,
                        (float(rotate.get("CenterX", 0.0)), float(rotate.get("CenterY", 0.0))),
                        rotate.get(xn, name)))
    return out


def _rim_centre(solid, unit, pivot):
    """
    The centre of the circle the layer's OUTERMOST solid pixels lie on.

    For a wheel that is the tooth-tip circle, and it is a far better statement
    about registration than any centroid: it is fitted to the part's own
    boundary, so no amount of shading anywhere else can move it. This is the
    measurement that says placement was never the problem - it lands within a
    fifth of a face unit of the pivot on every wheel in the face, while the
    same layer's alpha centroid is tens of units away.

    One point per half-degree of angle about the pivot, taken at the largest
    radius that is still part, then a least-squares circle through those.
    """
    ys, xs = np.nonzero(solid)
    x = (xs + 0.5) * unit - pivot[0]
    y = (ys + 0.5) * unit - pivot[1]
    r = np.hypot(x, y)

    bins = 720
    idx = ((np.arctan2(y, x) + math.pi) / (2 * math.pi) * bins).astype(int) % bins
    best_r = np.zeros(bins)
    best_i = np.full(bins, -1)
    order = np.argsort(r)
    # Ascending radius, so the last write into each bin is that bin's furthest
    # point. Cheaper than a groupby and exact.
    best_i[idx[order]] = order
    best_r[idx[order]] = r[order]
    # Only the bins that actually reached the outer circle. A toothed wheel has
    # gullets, and a bin that falls in one contributes a point off the wheel
    # body instead of off the tip circle - mixing the two radii into one fit is
    # what dragged the escape wheel's fitted centre 0.9 units off its pivot
    # while the tips themselves were dead on it.
    keep = (best_i >= 0) & (best_r >= 0.92 * best_r.max())
    if keep.sum() < 32:
        return None
    pts = np.column_stack([x[best_i[keep]] + pivot[0], y[best_i[keep]] + pivot[1]])
    cx, cy, _ = _circle_fit(pts)
    return float(cx), float(cy)


def _alpha(name):
    """A layer's alpha as floats in 0..1, plus how many face units a pixel is."""
    with Image.open(os.path.join(ASSETS, name)) as im:
        a = np.asarray(im.convert("RGBA").split()[-1], dtype=np.float64) / 255.0
    return a, FACE / a.shape[0]


def _centroid(weight, unit):
    """The weighted centroid of an image, in face units. Pixel centres, so a
    single lit pixel reports the middle of that pixel rather than its corner."""
    total = weight.sum()
    if total <= 0.0:
        return None
    ys, xs = np.indices(weight.shape)
    return (float((weight * (xs + 0.5)).sum() / total * unit),
            float((weight * (ys + 0.5)).sum() / total * unit))


def check_mover_shading(name, pivot, label):
    """
    One moving layer: is anything painted on it that would swing with it?

    Prints the solid part's own centroid first, every time and whether or not
    anything fails, because that number is the alibi. It is what says the
    registration is clean and the render is what is wrong - and without it the
    failures below read as "the wheel is in the wrong place", which is the
    diagnosis this whole file exists to prevent being made twice.
    """
    a, unit = _alpha(name)
    px, py = pivot
    total = a.sum()

    solid = a >= SOLID_ALPHA
    if not solid.any():
        check("%s has a part in it at all" % name, False,
              "no pixel reaches alpha %.2f, so there is nothing to measure "
              "the shading against" % SOLID_ALPHA)
        return

    solid_c = _centroid(np.where(solid, a, 0.0), unit)
    solid_d = math.hypot(solid_c[0] - px, solid_c[1] - py)

    # The alibi. For a wheel it is the tooth-tip circle, fitted to the part's
    # own boundary; for a lever or a hand there is no such circle, so the
    # solid mass's centroid stands in and is reported as what it is.
    rim = _rim_centre(solid, unit, pivot) if SYMMETRIC[name] else None

    # The part, grown by the margin. distance_transform_edt measures in pixels
    # from each empty pixel to the nearest solid one, so this is "every pixel
    # within PART_MARGIN of the silhouette", exactly.
    grown = ndimage.distance_transform_edt(~solid) <= PART_MARGIN / unit
    stray = np.where(grown, 0.0, a)
    stray_w = stray.sum()
    fraction = stray_w / total

    stray_c = _centroid(stray, unit)
    if stray_c is None:
        orbit, bearing = 0.0, 0.0
    else:
        orbit = math.hypot(stray_c[0] - px, stray_c[1] - py)
        bearing = math.degrees(math.atan2(stray_c[0] - px, -(stray_c[1] - py))) % 360.0

    if rim is None:
        print("       %-24s the part itself sits %5.2f units from the pivot "
              "(%.1f,%.1f) - which is the shape, not a fault"
              % (name, solid_d, px, py))
    else:
        print("       %-24s rim fits at (%6.2f,%6.2f), %5.3f units from the "
              "pivot (%.1f,%.1f) it turns about"
              % (name, rim[0], rim[1], math.hypot(rim[0] - px, rim[1] - py), px, py))

    if SYMMETRIC[name]:
        centroid = _centroid(a, unit)
        d = math.hypot(centroid[0] - px, centroid[1] - py)
        check("%s: mass centred on its pivot" % label,
              d <= CENTROID_MAX,
              "alpha centroid (%.2f, %.2f) is %.2f face units off the pivot; "
              "this part is rotationally symmetric, so that displacement is "
              "shading and it orbits once a turn (limit %.1f)"
              % (centroid[0], centroid[1], d, CENTROID_MAX))

    # WHERE THE LOBE LIES RELATIVE TO THE PART, which is the one thing that
    # could make a big off-part shadow legitimate. The hands are lit by a
    # source centred on their own pivot axis (see the .xaml), and a shadow cast
    # by an axial light lies straight along the part, so rotating the hand
    # rotates that shadow correctly - it is a symmetry of the lighting, not a
    # defect. A shadow thrown SIDEWAYS is a directional light, and it orbits.
    # This number is printed rather than exempted: it is evidence for whoever
    # reads the failure, not a hole to drive a shadow through. Today it reads
    # 28 to 121 degrees on the three hands, so their lobes are not axial and
    # the failures are real.
    part_bearing = math.degrees(math.atan2(solid_c[0] - px, -(solid_c[1] - py))) % 360.0
    off_axis = abs((bearing - part_bearing + 180.0) % 360.0 - 180.0)

    check("%s: nothing painted off the part" % label,
          not (fraction > STRAY_FRACTION_MAX and orbit > ORBIT_MIN),
          "%.1f%% of the layer's alpha sits more than %.0f units outside the "
          "part's own silhouette, centred %.1f units from the pivot at %.0f deg "
          "- %.0f deg off the part's own direction, which lies %.1f units out "
          "(limit %.0f%%); that weight is a shadow, and it swings"
          % (fraction * 100.0, PART_MARGIN, orbit, bearing, off_axis, solid_d,
             STRAY_FRACTION_MAX * 100.0))


def check_assets():
    layers = _layers()
    movers = [l for l in layers if l[1] is not None]
    print("baked directionality, over the %d of %d layers "
          "Controls/OpenworkedFace.xaml rotates" % (len(movers), len(layers)))
    print("(solid = alpha >= %.2f; off-part = further than %.0f face units from it)\n"
          % (SOLID_ALPHA, PART_MARGIN))

    for name, pivot, label in movers:
        if name not in SYMMETRIC:
            # Not a skip. A new rotating layer whose symmetry nobody has
            # declared is a layer nobody has thought about turning.
            check("%s: symmetry declared" % label, False,
                  "%s is rotated by the XAML but is not in SYMMETRIC, so this "
                  "file does not know which test applies to it" % name)
            continue
        check_mover_shading(name, pivot, label)

    print("\n       held still by the XAML, so not checked: %s"
          % ", ".join(name for name, pivot, _ in layers if pivot is None))


def check_cad():
    manifest = _manifest()
    print("placement invariants, from captures/cad/manifest.json")
    print("(scale %.4f face units/mm, rotation %.2f deg)\n"
          % (manifest["scale"], manifest["rotation"]))

    check_cock_jewel(manifest)
    check_fork_axis(manifest)
    check_plate_bores(manifest)
    check_screws_in_holes(manifest)
    check_pallet_stones(manifest)


def main():
    args = sys.argv[1:]
    want_cad = "--assets" not in args
    want_assets = "--cad" not in args

    if want_cad:
        if CAD_IMPORT_ERROR is not None:
            print("the CAD half needs .venv-cad (%s).\n"
                  "Run .venv-cad\\Scripts\\python.exe tools/placement_invariants.py, "
                  "or --assets for the image half alone." % CAD_IMPORT_ERROR)
            return 2
        check_cad()
        if want_assets:
            print()

    if want_assets:
        check_assets()

    print()
    if FAILURES:
        print("%d invariant(s) failed:" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("all invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
