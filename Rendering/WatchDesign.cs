using System.Collections.Generic;
using System.Numerics;

namespace ClockWall.Rendering;

/// <summary>
/// THE FACE, as data: the palette, what each part is made of and how it was
/// finished, where the movement sits, where the camera stands and where the
/// lights are. <see cref="WatchScene"/> is the engine that draws whatever
/// design it is handed and contains no number of its own.
///
/// WHERE THE SHAPES ARE. Not here. Every part that is not the movement is a
/// watertight solid built by tools/case_solids.py and exported to
/// Assets/case.glb (and models/step/case.step, which can be measured, checked
/// against the movement, and printed). This record names those parts and
/// says what they are made of; it does not know how long the minute hand is.
/// That split is the direction of travel: an object that could be made, whose
/// time will one day come from its own mechanism rather than the system clock.
///
/// A new face is a new instance of this record - usually
/// <c>BlueSoleil with { ... }</c> - plus, if its shapes differ, a new set of
/// dimensions in case_solids.py. FACE-RECIPE.md is the process.
///
/// UNITS. Millimetres, in the world frame the scene uses: X to the right,
/// Y toward the viewer, Z down the dial toward six. Colours are linear.
/// </summary>
internal sealed record WatchDesign
{
    /// <summary>Millimetres per face unit: tools/om10_layout.py places the
    /// movement at 11.78 face units per millimetre, and the dial's printing
    /// mask is drawn in face units.</summary>
    public const float FaceUnit = 1f / 11.780018f;

    public string Name { get; init; } = "";

    // ------------------------------------------------------------ the dial

    /// <summary>Radius of the printed minute track, for the shader.</summary>
    public float TrackRadius { get; init; }

    /// <summary>The opening: centre in the world frame and radius. The dial
    /// solid has the hole; the shader uses these for the recess occlusion of
    /// whatever sits in the well.</summary>
    public Vector3 ApertureCentre { get; init; }
    public float ApertureRadius { get; init; }

    // ------------------------------------------------------------ the movement

    /// <summary>Where the movement's own Y=0 plane sits under the dial.</summary>
    public float MovementY { get; init; }

    /// <summary>The placement: one arbor of the movement, in the CAD's (x, y),
    /// is carried to a point on the dial, and the whole assembly is turned
    /// clockwise about it. For a face with hands on real arbors the arbor is
    /// the centre wheel's and the point is the dial centre.</summary>
    public Vector2 PlacedArborCad { get; init; }
    public Vector2 PlacedArborWorldXZ { get; init; }
    public float MovementRotationDeg { get; init; }

    /// <summary>The arbor the seconds hand turns about, in the CAD's (x, y):
    /// the fourth wheel's. Its world position is derived through the
    /// placement, and case_solids.py must have put the hand there.</summary>
    public Vector2 SecondsArborCad { get; init; }

    /// <summary>Direction of the cotes de Geneve across the bridges, in the
    /// movement's own frame.</summary>
    public Vector3 CotesDirection { get; init; }

    // ------------------------------------------------------------ materials

    /// <summary>Per part of Assets/case.glb, by node name. The crystal is
    /// listed for completeness; it is drawn by its own shader.</summary>
    public IReadOnlyDictionary<string, Material> Case { get; init; } = new Dictionary<string, Material>();

    /// <summary>Per OM10 part of Assets/movement.glb, by node name. Parts not
    /// listed are drawn polished.</summary>
    public IReadOnlyDictionary<string, Material> Movement { get; init; } = new Dictionary<string, Material>();

    public Material Polished { get; init; }

    // ------------------------------------------------------------ the rig

    /// <summary>A long lens: the distance sets the perspective, the tilt
    /// gives the case a side, and both breathe so the reflections move.
    /// The view is <see cref="ViewHeightMm"/> tall at the dial.</summary>
    public float CameraDistance { get; init; }
    public float CameraTiltDeg { get; init; }
    public float CameraTiltSwingDeg { get; init; }
    public float CameraSwingDeg { get; init; }
    public float ViewHeightMm { get; init; }

    /// <summary>The key light: bearing clockwise from twelve, elevation
    /// above the dial, each with the amplitude of its slow wander.</summary>
    public float KeyBearingDeg { get; init; }
    public float KeyBearingSwingDeg { get; init; }
    public float KeyElevationDeg { get; init; }
    public float KeyElevationSwingDeg { get; init; }
    public Vector3 KeyColour { get; init; }

    /// <summary>How the studio panorama is turned: pitch so world +Y (what
    /// flat polished metal facing the viewer reflects) lands at the chosen
    /// elevation, yaw to the chosen azimuth, and a wander. Find these with
    /// CLOCKWALL_DEBUG_VIEW=1, never by arithmetic.</summary>
    public float EnvPitchDeg { get; init; }
    public float EnvYaw { get; init; }
    public float EnvYawSwing { get; init; }

    public float Exposure { get; init; } = 1f;

    // ------------------------------------------------------------ the blue soleil

    /// <summary>The face ART-DIRECTION.md describes: a blue soleil dial in a
    /// polished steel case, the OM10 turning behind an open heart at six -
    /// now with the hands on the centre wheel and the seconds on the fourth.</summary>
    public static WatchDesign BlueSoleil { get; } = MakeBlueSoleil();

    private static WatchDesign MakeBlueSoleil()
    {
        const float U = FaceUnit;
        // tools/case_solids.py APERTURE, in CAD (x, y up) -> world (x, z down).
        var aperture = new Vector3(-1.23f, 0f, 12.63f);

        var steel = new Material(Material.Steel, 1f, 0.11f, 0.11f);
        var bezel = new Material(Material.Steel, 1f, 0.06f, 0.14f, Finish.Circular, FinishCentre: Vector3.Zero);

        return new WatchDesign
        {
            Name = "Blue soleil, open heart, real arbors",

            TrackRadius = 268f * U,     // dial_render.CHAPTER_R
            ApertureCentre = aperture,
            ApertureRadius = 9.6f,

            // The highest part (a bridge screw head, Z=2.30 in the CAD)
            // lands 1.3mm below the dial's surface, the balance rim about 3mm.
            MovementY = -3.6f,
            // The centre wheel (wheel_a, 75 teeth, once an hour) under the
            // dial centre, and the assembly turned so the balance sits
            // straight below it at 15.10mm. Derived in the session notes from
            // the manifest's arbors; case_solids.py carries the same numbers.
            PlacedArborCad = new Vector2(7.028f, 4.223f),
            PlacedArborWorldXZ = Vector2.Zero,
            MovementRotationDeg = 272.70f,
            SecondsArborCad = new Vector2(0.016f, 7.999f),   // pinion_b, the fourth's arbor
            CotesDirection = new Vector3(0.94f, 0f, 0.34f),

            Polished = steel,

            // ART-DIRECTION.md's palette. The dial's lobe width is the
            // along-grain roughness; its darkness across the grain the other.
            Case = new Dictionary<string, Material>
            {
                ["case"] = bezel,
                ["caseback"] = new(new Vector3(0.25f, 0.26f, 0.28f), 1f, 0.55f, 0.55f, Recess: true),
                ["dial"] = new(Material.DialBlue, 1f, 0.30f, 0.72f, Finish.Dial, Lacquer: 0.25f),
                ["rehaut"] = new(Material.Steel, 1f, 0.06f, 0.12f, Finish.Circular, FinishCentre: aperture),
                ["indices"] = steel,
                ["hour_hand"] = steel,
                ["minute_hand"] = steel,
                // Steel rather than blued: it lives in the well now, over
                // a dark movement, and a blued needle there vanished.
                ["seconds_hand"] = steel with { Recess = true },
                ["cap"] = steel,
                ["crown"] = new(Material.Steel, 1f, 0.10f, 0.22f, Finish.Circular, FinishCentre: new Vector3(28.5f, 0f, 0f)),
            },

            // The two-tier rule from render_lib, kept: almost everything
            // quiet, a few things bright, and the escapement the dimmest
            // metal in the window. Warmth only from the brass and the rubies.
            Movement = new Dictionary<string, Material>
            {
                ["mainplate"] = new(Material.Plate, 1f, 0.34f, 0.42f, Finish.Perlage, FinishScale: 1.0f, Recess: true),
                ["bridge"] = new(Material.Plate, 1f, 0.14f, 0.34f, Finish.Straight, FinishScale: 1.35f, FinishDir: Vector3.UnitX, Recess: true),
                ["cock"] = new(Material.Plate, 1f, 0.14f, 0.34f, Finish.Straight, FinishScale: 1.35f, FinishDir: Vector3.UnitX, Recess: true),
                ["wheel_a"] = new(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true),
                ["wheel_b"] = new(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true),
                ["wheel_c"] = new(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true),
                ["balance"] = new(Material.Brass, 1f, 0.16f, 0.36f, Finish.Circular, Recess: true),
                ["collet"] = new(Material.Brass, 1f, 0.22f, 0.22f, Recess: true),
                ["pinion_a"] = new(Material.Steel, 1f, 0.16f, 0.16f, Recess: true),
                ["pinion_b"] = new(Material.Steel, 1f, 0.16f, 0.16f, Recess: true),
                ["epinion"] = new(Material.Steel, 1f, 0.16f, 0.16f, Recess: true),
                ["escape"] = new(Material.Steel, 1f, 0.36f, 0.36f, Recess: true),
                ["lever"] = new(new Vector3(0.55f, 0.56f, 0.58f), 1f, 0.04f, 0.04f, Finish.BlackPolish, Recess: true),
                ["guard"] = new(Material.Steel, 1f, 0.14f, 0.14f, Recess: true),
                ["staff"] = new(Material.Steel, 1f, 0.10f, 0.10f, Recess: true),
                ["roller"] = new(Material.Steel, 1f, 0.14f, 0.14f, Recess: true),
                ["hairspring"] = new(Material.Blued, 1f, 0.22f, 0.22f, Recess: true),
                ["jewel"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
                ["stone_a"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
                ["stone_b"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
                ["screw_a"] = new(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
                ["screw_b"] = new(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
                ["screw_c"] = new(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
            },

            // A long lens from 300mm, tilted a few degrees so the case has a
            // side, breathing by a degree or two. 640 face units tall at the
            // dial, so the watch is the size the sprite face was; the panel is
            // wider than it is tall so the crown is not cut off at three.
            CameraDistance = 300f,
            CameraTiltDeg = 4.0f,
            CameraTiltSwingDeg = 1.5f,
            CameraSwingDeg = 1.2f,
            ViewHeightMm = 640f * U,

            // From the upper left like the sprite face's key (dial_render
            // LIGHT_DEG = 315), lowish so the hands throw a shadow that
            // reads, wandering over a couple of minutes so the lobes sweep.
            KeyBearingDeg = 315f,
            KeyBearingSwingDeg = 22f,
            KeyElevationDeg = 46f,
            KeyElevationSwingDeg = 8f,
            KeyColour = new Vector3(2.0f, 1.97f, 1.9f),

            // studio_small_09, measured off the panorama in radiance: the
            // one broad bright source is a gridded softbox at azimuth +36,
            // 25 degrees up. World +Y is aimed at it. Yaw is negative because
            // the panorama's longitude runs the other way from a rotation
            // about Y.
            EnvPitchDeg = -65f,
            EnvYaw = -0.63f,
            EnvYawSwing = 0.22f,

            Exposure = 1.0f,
        };
    }
}
