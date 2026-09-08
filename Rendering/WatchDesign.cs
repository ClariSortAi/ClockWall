using System.Collections.Generic;
using System.Numerics;

namespace ClockWall.Rendering;

/// <summary>A dauphine hand's outline, in millimetres from the pivot.</summary>
internal sealed record HandShape(float Length, float HalfWidth, float Shoulder, float Tail);

/// <summary>
/// THE FACE, as data. Everything that makes this watch this watch and not
/// another one lives here: the palette, every dimension, what each surface
/// is made of and how it was finished, where the camera stands and where
/// the lights are. <see cref="WatchScene"/> is the engine that draws
/// whatever design it is handed and contains no number of its own.
///
/// A new face is a new instance of this record - usually
/// <c>BlueSoleil with { ... }</c> - and nothing else. FACE-RECIPE.md is the
/// process: reference photographs first, then the palette, then the
/// dimensions, then the finishes, then the rig, each checked on the wall
/// before the next. The order matters more than any value here.
///
/// UNITS. Millimetres, in the world frame the scene uses: X to the right,
/// Y toward the viewer, Z down the dial toward six. The sprite face and
/// case_geometry.py drew everything in "face units", 640 across the panel,
/// and those numbers are carried over through <see cref="FaceUnit"/> so
/// the two faces stay the same object. Colours are linear.
/// </summary>
internal sealed record WatchDesign
{
    /// <summary>Millimetres per face unit: tools/om10_layout.py places the
    /// movement at 11.78 face units per millimetre, so this is what turns
    /// every number in case_geometry.py into a real size.</summary>
    public const float FaceUnit = 1f / 11.780018f;

    public string Name { get; init; } = "";

    // ------------------------------------------------------------ the case

    public float DialRadius { get; init; }
    public float BezelInner { get; init; }
    public float CaseRadius { get; init; }
    public float TrackRadius { get; init; }

    /// <summary>The bezel's domed top and rounded outer edge, and the height
    /// of the rehaut wall the crystal sits on.</summary>
    public float CrystalEdge { get; init; }
    public float CrystalPeak { get; init; }

    // ------------------------------------------------------------ the dial

    public float IndexInner { get; init; }
    public float IndexOuter { get; init; }
    public float IndexHalfWidth { get; init; }
    public float IndexHeight { get; init; }
    public float IndexChamfer { get; init; }
    /// <summary>The double baton at twelve: each half's width and its
    /// sideways offset from the radius.</summary>
    public float TwelveHalfWidth { get; init; }
    public float TwelveOffset { get; init; }

    /// <summary>The opening. Centre in the world frame; the well is the
    /// wall dropping from the dial to the movement, and the rehaut the
    /// polished ring standing round the opening.</summary>
    public Vector3 ApertureCentre { get; init; }
    public float ApertureRadius { get; init; }
    public float RehautOuter { get; init; }
    public float WellDepth { get; init; }

    // ------------------------------------------------------------ the hands

    public HandShape Hour { get; init; } = new(0, 0, 0, 0);
    public HandShape Minute { get; init; } = new(0, 0, 0, 0);
    public float HourBase { get; init; }
    public float HourRidge { get; init; }
    public float MinuteBase { get; init; }
    public float MinuteRidge { get; init; }
    public float SecondBase { get; init; }
    public float SecondTop { get; init; }
    public float SecondLength { get; init; }
    public float SecondHalfWidth { get; init; }
    public float SecondTail { get; init; }
    public float SecondRingOffset { get; init; }
    public float SecondRingRadius { get; init; }
    public float SecondHoleRadius { get; init; }
    public float CapRadius { get; init; }

    // ------------------------------------------------------------ the movement

    /// <summary>Where the movement's own Y=0 plane sits under the dial.</summary>
    public float MovementY { get; init; }
    /// <summary>tools/om10_layout.py's placement: the CAD arbor that is
    /// carried to <see cref="BalanceFaceUnits"/>, and the clockwise turn
    /// applied to the whole assembly on the way.</summary>
    public Vector2 BalanceArborCad { get; init; }
    public Vector2 BalanceFaceUnits { get; init; }
    public float MovementRotationDeg { get; init; }
    /// <summary>Direction of the cotes de Geneve across the bridges, in the
    /// movement's own frame.</summary>
    public Vector3 CotesDirection { get; init; }

    // ------------------------------------------------------------ materials

    public Material Dial { get; init; }
    public Material Polished { get; init; }
    public Material Bezel { get; init; }
    public Material Rehaut { get; init; }
    public Material SecondHand { get; init; }
    public Material Floor { get; init; }
    /// <summary>Per OM10 part, by the exporter's name. Parts not listed are
    /// drawn polished.</summary>
    public IReadOnlyDictionary<string, Material> Movement { get; init; } = new Dictionary<string, Material>();

    // ------------------------------------------------------------ the rig

    /// <summary>A long lens: the distance sets the perspective, the tilt
    /// gives the case a side, and both breathe so the reflections move.</summary>
    public float CameraDistance { get; init; }
    public float CameraTiltDeg { get; init; }
    public float CameraTiltSwingDeg { get; init; }
    public float CameraSwingDeg { get; init; }

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
    /// polished steel case, the OM10 turning behind an open heart at six.</summary>
    public static WatchDesign BlueSoleil { get; } = MakeBlueSoleil();

    private static WatchDesign MakeBlueSoleil()
    {
        const float U = FaceUnit;
        var aperture = new Vector3(0f, 0f, 130f * U);   // escapement_geometry.APERTURE

        return new WatchDesign
        {
            Name = "Blue soleil, open heart",

            DialRadius = 288f * U,      // case_geometry.DIAL_R
            BezelInner = 289f * U,      // BEZEL_IN
            CaseRadius = 314f * U,      // CASE_R
            TrackRadius = 268f * U,     // dial_render.CHAPTER_R
            CrystalEdge = 2.7f,
            CrystalPeak = 3.5f,

            IndexInner = 246f * U,
            IndexOuter = 279f * U,
            IndexHalfWidth = 7.5f * U,
            IndexHeight = 0.45f,
            IndexChamfer = 0.12f,
            TwelveHalfWidth = 4.4f * U,
            TwelveOffset = 6.2f * U,

            ApertureCentre = aperture,
            ApertureRadius = 126f * U,
            RehautOuter = 133f * U,
            // The number that makes the aperture a recess: the wall it
            // draws, and the depth the shader's occlusion term works against.
            WellDepth = 3.0f,

            // case_geometry.build_hands, in millimetres. The hands sit
            // higher than a thin watch would put them, on purpose: their
            // shadows on the dial are what say they are ABOVE it rather than
            // printed on it, and a shadow displaced by a millimetre reads
            // from across a room where a third of that does not. The facets
            // are shallow - 11 degrees - because a steeper ridge reflected
            // outside the studio's softbox and went gunmetal at half the hours.
            Hour = new HandShape(150f * U, 11f * U, 44f * U, 34f * U),
            Minute = new HandShape(214f * U, 9f * U, 54f * U, 40f * U),
            HourBase = 1.05f, HourRidge = 0.19f,
            MinuteBase = 1.55f, MinuteRidge = 0.16f,
            SecondBase = 2.00f, SecondTop = 2.15f,
            SecondLength = 232f * U,
            SecondHalfWidth = 2f * U,
            SecondTail = 40f * U,
            SecondRingOffset = 54f * U,
            SecondRingRadius = 13f * U,
            SecondHoleRadius = 5.4f * U,
            CapRadius = 13f * U,

            // The highest part (a bridge screw head, Z=2.30 in the CAD)
            // lands 1.3mm below the dial's surface, the balance rim about 3mm.
            MovementY = -3.6f,
            BalanceArborCad = new Vector2(-8.06f, 3.51f),         // om10_layout.AXIS["balance"]
            BalanceFaceUnits = new Vector2(296.2238f, 464.2443f), // escapement_geometry.BALANCE
            MovementRotationDeg = 6.595f,                          // om10_layout ROT_DEG
            CotesDirection = new Vector3(0.94f, 0f, 0.34f),

            // ART-DIRECTION.md's palette. The dial's lobe width is the
            // along-grain roughness; its darkness across the grain the other.
            Dial = new Material(Material.DialBlue, 1f, 0.30f, 0.72f, Finish.Dial, Lacquer: 0.25f),
            Polished = new Material(Material.Steel, 1f, 0.11f, 0.11f),
            Bezel = new Material(Material.Steel, 1f, 0.06f, 0.14f, Finish.Circular, FinishCentre: Vector3.Zero),
            Rehaut = new Material(Material.Steel, 1f, 0.06f, 0.12f, Finish.Circular, FinishCentre: aperture),
            SecondHand = new Material(Material.Blued, 1f, 0.10f, 0.10f),
            Floor = new Material(new Vector3(0.25f, 0.26f, 0.28f), 1f, 0.55f, 0.55f, Recess: true),

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
            // side, breathing by a degree or two.
            CameraDistance = 300f,
            CameraTiltDeg = 4.0f,
            CameraTiltSwingDeg = 1.5f,
            CameraSwingDeg = 1.2f,

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
            // 25 degrees up. World +Y is aimed at it; the white cyclorama
            // that LOOKS bright in a preview is radiance 1 and gave
            // gunmetal. Yaw is negative because the panorama's longitude
            // runs the other way from a rotation about Y.
            EnvPitchDeg = -65f,
            EnvYaw = -0.63f,
            EnvYawSwing = 0.22f,

            Exposure = 1.0f,
        };
    }
}
