# Art direction: the blue and silver watch

The goal is one sentence. **A person walking past the wall should stop, because
for a moment they think there is a real watch hanging there.**

Everything below serves that and nothing else. This is the aesthetic brief; the
engineering order of work is `HANDOVER-REALTIME.md`, and the reason the old
pipeline could never get here is `PIPELINE.md`.

## The palette, which is already decided

These are the numbers in the repo. Do not reinvent them - the face has an
identity and this is a rendering job, not a redesign.

**The dial is a blue soleil**, three tones, from `tools/dial_render.py`:

| role | sRGB | what it is |
|---|---|---|
| shadow | `(9, 17, 42)` | the dark lobe, near-black navy |
| mid | `(28, 56, 118)` | the body of the dial, royal blue |
| hot | `(112, 160, 226)` | the bright lobe, pale and cool |

**Printing** is `(232, 238, 250)` - a cool near-white, never pure white.

**The metals**, linear base colour with metalness and roughness, from
`render_lib.SURFACES`:

| | base colour | metal | rough |
|---|---|---|---|
| steel (case, bezel, hands, indices) | `0.680, 0.700, 0.740` | 1.0 | 0.16 |
| brass (train wheels) | `0.740, 0.560, 0.260` | 1.0 | 0.22 |
| blued (screws) | `0.035, 0.075, 0.300` | 1.0 | 0.11 |

The scheme is **cold**. Blue dial, white-silver steel, and the only warmth in
the whole object is the brass in the aperture and the red of two ruby stones.
That restraint is the design. Do not add gold, do not warm the steel, and do not
let the environment tint the case yellow.

## The one effect that matters most

`dial_render.py` already says it, and it is the single most important paragraph
in this repo for the look:

> The metal is brushed RADIALLY, so every scratch runs from the centre outward -
> which means the noise has to be a function of angle alone and constant along
> the radius. And because those scratches all lie the same way, the dial has two
> bright lobes opposite each other and two dark ones at ninety degrees, sweeping
> as you tilt it. That swing from near-white to near-black across one disc is
> the whole effect, and it is why a sunburst dial looks alive and a flat one
> looks like paint.

**In the current face that sweep is frozen**, because it is baked into
`Assets/dial-texture.png` and a PNG cannot sweep. Making it live is the largest
single upgrade available and it is the reason the real-time pipeline was chosen.

Implement it as a real anisotropic BRDF with **radial tangents** - tangent
direction = normalised (position - dial centre), rotated 90 degrees in the
tangent plane so the grain runs outward. Not a texture. Then the lobes move as
the light and view move, and the dial breathes.

Get this one right before anything else on the dial. It is 80 per cent of what
people mean when they say a blue dial is beautiful.

## Seven things that make it read as real

Roughly in order of how much they buy.

**1. The sunburst sweeps.** Above.

**2. There is a crystal.** There is none today, and its absence is a large part
of why the face reads as a picture. A sapphire crystal wants: a faint specular
sheet across the whole dial that moves independently of everything under it, a
slightly domed or bevelled edge that refracts the dial's outer ring, and the
cool violet-blue cast a real anti-reflective coating throws at glancing angles.
Keep it subtle - a strong reflection reads as plastic. This is cheap and it is
transformative.

**3. The bezel has a wall and casts a shadow.** The wall reported this: *"the
mechanism to create the view of depth between the bezel and the watch face isn't
quite realistic."* It is currently a hard bright-to-dark line. It wants a real
rehaut - the vertical inner wall between dial edge and crystal - and the bezel's
overhang throwing a soft shadow onto the outer dial. A line is what you draw
when you are not lighting a surface.

**4. The indices are geometry, faceted, with bevels.** Applied polished
markers, each catching one hard specular line along its top facet. They must
respond to the light individually - when the dial's bright lobe passes an index,
that index should flare. Painted rectangles will never do this.

**5. The hands cast shadows, and the shadows sweep.** Given no shadow today by
an explicit decision that the old architecture forced. Dauphine hands are
faceted: a ridge down the centre throws a bright line on one side and a dark one
on the other, and that split flips as the hand crosses the light. The shadow
should be soft, offset by the hand's real standoff from the dial, and sharpen
where the hand is closest.

**6. The aperture is a recess, not a hole.** `render_lib` already argues this at
length: it is an opening cut into a lacquered dial with a movement sitting well
below the crystal, so it must be darker than the dial and fall off at its rim.
Occlusion at the edge, and the movement lit by less light than the dial gets.

**7. Depth of field, barely.** A real macro photograph of a watch has the near
edge of the case fractionally soft. Very slight. Enough to feel like a
photograph, never enough to notice as an effect.

## The movement, once the dial is right

Two-tier finishing, and `render_lib` already has the principle written down:
almost everything matte and quiet, only a few chosen elements bright, *because
the point of finishing is to decide how many things compete for the eye at
once.* The escapement is deliberately the dimmest metal in the aperture. Keep
that.

Anisotropy applies here too, and differently per part:

- **mainplate** - perlage, overlapping circular graining, each swirl a small
  circular anisotropy centred on its own spot
- **bridge and cock** - cotes de Geneve, straight parallel graining, one
  direction across the whole part
- **lever** - black polish, which is not a colour but a mirror so flat it reads
  black except where it catches a source dead on
- **wheels** - fine circular graining, brass, concentric with the arbor
- **screws** - blued, polished slots, and the slot should catch light

## What the wall demands

**1080 x 1920 portrait, seen from across a room, running for days.**

That third one constrains everything: no per-frame allocation, no growing
buffers, no leak. It has to hold at hour 200 exactly as it looks at minute one.

The viewing distance constrains the other direction. Detail that only resolves
at 100 per cent zoom is wasted, and contrast that reads at arm's length can
disappear at three metres. **Judge every change from across the room, at the
real size, not on a crop.** `HANDOVER.md` already calls the wall the acceptance
test and it was right.

## How to know it is working

- Put a still beside `captures/gltf/preview-34.png`. The real-time render should
  be recognisably the same object, then better lit.
- Put it beside a photograph of an open-heart or skeleton watch and **name the
  differences out loud**. `HANDOVER-REALISM.md` records that working without a
  reference was the central handicap of an entire session. Do not repeat it.
- Tilt the light and watch the dial. If the bright lobes do not sweep, the
  anisotropy is not working, whatever the still looks like.
- Then walk away from the screen and turn around.

## What not to do

Do not chase realism the sprite pipeline already achieved. Geometry, proportion,
tooth counts, pivot placement and the escapement's mechanics are **done and
correct** - three sessions went into them and they landed. The gap is light.

Do not add a second accent colour. Do not warm the steel. Do not make the
crystal reflective enough to notice. Do not let the movement out-compete the
dial for attention; it is a window into the watch, not the subject.

And do not tune numbers against a single still frame. The whole argument for
this pipeline is that the light moves.
