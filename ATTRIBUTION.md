# Where the movement came from

The watch movement in this face is not drawn. It is OM10, the first open-source
mechanical Swiss watch movement, published by the
[openmovement association](https://openmovement.org/) of La Chaux-de-Fonds.

The wheels, the lever, the balance, the hairspring, the cock and the jewels in
`Assets/movement-*.png` are that movement's own CAD solids, scaled and placed.
They are the parts, not likenesses of them.

## The file

    OM10-00001 VA 01_3.stp
    Autodesk Inventor 2022, exported 2022-06-30 as AP214
    166 solids, 18.8 MB

Downloaded from openmovement.org's member area. The STEP file is not committed
here. `tools/om10_extract.py` reads it from a local path and writes only the
dozen or so parts this face shows into `captures/`, which is gitignored. Anyone
rebuilding the assets needs their own copy from openmovement.

## What was taken

| Part in the render | OM10 drawing number |
|---|---|
| balance wheel | OM10-00113 |
| hairspring | OM10-00115 |
| balance staff, roller table, collet | OM10-00112, OM10-00110, OM10-00116 |
| pallet fork (lever) | OM10-00104 |
| pallet stones, guard dart | OM10-00106 x2, OM10-00105 |
| escape wheel | OM00-00101 |
| escape pinion | OM10-00146 |
| fourth wheel and its pinion | OM10-00165, OM10-00164 |
| balance cock | OM10-00196 |
| cock screws | OM00-00106 |
| jewels | OM00-00124 |

## What was measured off it

These are counted and measured rather than chosen, and they now drive the
animation in `Services/Caliber.cs`:

- escape wheel, 20 teeth
- escape pinion, 8 leaves
- fourth wheel, 84 teeth, so the train ratio is 10.5
- balance, pallet staff and escape wheel are collinear, with the staff at 0.5006
  of the span. That is the midpoint, which is what a lever's two equal arms
  require.

The beat rate follows from those counts instead of being set beside them. The
fourth wheel carries the seconds, so it has to turn once a minute, which puts
the caliber at 25,200 vph (3.5 Hz). The working is on `Caliber.Swiss4Hz`.

One number confirms the whole placement chain. The cock's balance jewel hole,
read out of the cock's own outline, lands at (-8.06, 3.51) in the movement's
plane, which is the balance arbor read off the assembly, to two decimals. The
arbor, the extraction and the transform all agree.

## Licence

openmovement publishes OM10 under open-source terms. The download sits behind a
free registration rather than a licence fee. This project uses the geometry to
render a decorative wall clock and redistributes no OM10 source file, only
rendered images of the parts. If you fork this and mean to redistribute anything
derived from the STEP itself, check the current terms with openmovement first.

## Consulted, then not used

Hugh Sparks' write-up of the BS 978 cycloidal gear formulas at
[csparks.com](https://www.csparks.com/watchmaking/CycloidalGears/index.jxl) is
the standard for clock and watch tooth profiles. It was read while planning to
model the wheels from scratch, and using real ones made it unnecessary.

`bd_warehouse` (Apache-2.0) supplies real ISO fasteners. It was installed and
then dropped: at three pixels per face unit a screw head is twelve pixels
across and its thread cannot be seen, so it was a heavy dependency buying
nothing. Its `build123d` dependency is still in use and is patched locally.
HANDOVER.md explains why.

## The open-heart cut, 2026-09-08

The live face exports every solid of the OM10 (`tools/gltf_export.py`) and,
for three of them - the mainplate `OM10-00214`, the date plate `OM10-00217`
and the dial rest `OM10-00138` - cuts a window over the balance so it can be
seen from the dial side, keeping a bar along the line of centres to carry the
dial-side jewel seats. That is a modification of a derived copy, done at
export time; the OM10 files themselves are not edited. It is the same
operation a manufacturer performs to make an open-heart version of a stock
movement, and it is recorded here so that nobody mistakes the cut plate for
openmovement's design.

## One bore opened, 2026-09-08

The same export opens the intermediate wheel's upper bearing `OM00-00123`
from 0.1812 to 0.2012 mm. The OM10's 2021/02/01 release note enlarges the
seconds and intermediate pivots from 0.167 to 0.190; the lower bearing was
opened to match and this one was not, an interference of 0.0096 mm on the
diameter that `tools/om10_fits.py` measured off the file itself
(`docs/om10-fits.md`). It is a correction to a derived copy, not to the OM10
files, and it is recorded here so that the opened bush is not taken for
openmovement's dimension.

The source STEP (`om10-00001_20220701_va_01_3.stp`, 18.8 MB) and the release
notes (`OM10_Release_notes.pdf`, which name the parts) are the owner's copies
from openmovement's free registration, kept outside the repository.
