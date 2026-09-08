using System.Collections.Generic;
using System.Numerics;

namespace ClockWall.Rendering;

/// <summary>
/// THE FACE, as data: the palette, what each part is made of and how it was
/// finished, where the camera stands and where the lights are.
/// <see cref="WatchScene"/> is the engine that draws whatever design it is
/// handed and contains no number of its own.
///
/// WHERE THE SHAPES ARE. Not here. The movement is the OM10, every one of
/// its 166 solids, exported by tools/gltf_export.py into Assets/movement.glb
/// in the renderer's world frame with its plate centre - the hands' arbor -
/// at the dial centre. Every part that is not the movement is a watertight
/// solid built by tools/case_solids.py and exported to Assets/case.glb (and
/// models/step/case.step, which can be measured, checked against the
/// movement, and printed). This record names those parts and says what
/// they are made of; it does not know how long the minute hand is.
///
/// WHERE THE PLACEMENT IS. In the movement's own geometry. The OM10's stem
/// fixes which way is three o'clock, and its plate centre is the hands'
/// arbor; the exporter lands both where the dial wants them, so the only
/// placement left to a design is how far under the dial the movement sits.
/// That is the direction of travel: an object that could be made, whose time
/// will one day come from its own mechanism rather than the system clock.
///
/// UNITS. Millimetres, in the world frame the scene uses: X to the right,
/// Y toward the viewer, Z down the dial toward six. Colours are linear.
/// </summary>
internal sealed record WatchDesign
{
    /// <summary>Millimetres per face unit: the dial's printing mask and the
    /// sprite face's case numbers are in face units, 640 across the panel.</summary>
    public const float FaceUnit = 1f / 11.780018f;

    public string Name { get; init; } = "";

    // ------------------------------------------------------------ the dial

    /// <summary>Radius of the printed minute track, for the shader.</summary>
    public float TrackRadius { get; init; }

    /// <summary>The opening: centre in the world frame and radius. The dial
    /// solid has the hole; the shader uses these for the recess occlusion of
    /// whatever sits in the well. Must agree with case_solids.py.</summary>
    public Vector3 ApertureCentre { get; init; }
    public float ApertureRadius { get; init; }

    // ------------------------------------------------------------ the movement

    /// <summary>Where the movement's own Y=0 plane sits under the dial's
    /// face. The OM10's dial seat is its plate's dial face at y = 4.41; the
    /// dial is 0.4 thick; so -4.81. Must agree with case_solids.MOVEMENT_Z.</summary>
    public float MovementY { get; init; }

    /// <summary>Direction of the cotes de Geneve across the bridges.</summary>
    public Vector3 CotesDirection { get; init; }

    // ------------------------------------------------------------ materials

    /// <summary>Per part of Assets/case.glb, by node name. The crystal is
    /// listed for completeness; it is drawn by its own shader.</summary>
    public IReadOnlyDictionary<string, Material> Case { get; init; } = new Dictionary<string, Material>();

    /// <summary>Per OM10 part of Assets/movement.glb, by node name. A part
    /// not listed is drawn as <see cref="PlateMetal"/>, except that a name
    /// beginning "screw" is blued and one beginning "jewel" is ruby.</summary>
    public IReadOnlyDictionary<string, Material> Movement { get; init; } = new Dictionary<string, Material>();

    public Material Polished { get; init; }
    public Material PlateMetal { get; init; }
    public Material Screw { get; init; }
    public Material Jewel { get; init; }

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
    /// polished steel case, the OM10 turning behind an open heart - now
    /// where the OM10 keeps its balance, under eleven, with the small seconds
    /// at nine and the crown at three, because that is how it is built.</summary>
    public static WatchDesign BlueSoleil { get; } = MakeBlueSoleil();

    private static WatchDesign MakeBlueSoleil()
    {
        const float U = FaceUnit;
        // tools/case_solids.py APERTURE, in its CAD (x, y up) -> world (x, z down).
        var aperture = new Vector3(-4.83f, 0f, -6.75f);

        var steel = new Material(Material.Steel, 1f, 0.11f, 0.11f);
        var plate = new Material(Material.Plate, 1f, 0.30f, 0.30f, Recess: true);
        var brass = new Material(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true);
        var pinion = new Material(Material.Steel, 1f, 0.16f, 0.16f, Recess: true);

        return new WatchDesign
        {
            Name = "Blue soleil, open heart at eleven, small seconds at nine",

            TrackRadius = 268f * U,     // dial_render.CHAPTER_R
            ApertureCentre = aperture,
            ApertureRadius = 10.2f,

            MovementY = -4.81f,
            CotesDirection = new Vector3(0.94f, 0f, 0.34f),

            Polished = steel,
            PlateMetal = plate,
            Screw = new Material(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
            Jewel = new Material(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),

            // ART-DIRECTION.md's palette. The dial's lobe width is the
            // along-grain roughness; its darkness across the grain the other.
            Case = new Dictionary<string, Material>
            {
                ["case"] = new(Material.Steel, 1f, 0.06f, 0.14f, Finish.Circular, FinishCentre: Vector3.Zero),
                ["caseback"] = new(new Vector3(0.25f, 0.26f, 0.28f), 1f, 0.55f, 0.55f, Recess: true),
                ["dial"] = new(Material.DialBlue, 1f, 0.30f, 0.72f, Finish.Dial, Lacquer: 0.25f),
                ["rehaut"] = new(Material.Steel, 1f, 0.06f, 0.12f, Finish.Circular, FinishCentre: aperture),
                ["indices"] = steel,
                ["hour_hand"] = steel,
                ["minute_hand"] = steel,
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
                ["barrel_bridge"] = new(Material.Plate, 1f, 0.14f, 0.34f, Finish.Straight, FinishScale: 1.35f, FinishDir: Vector3.UnitX, Recess: true),
                ["cock"] = new(Material.Plate, 1f, 0.14f, 0.34f, Finish.Straight, FinishScale: 1.35f, FinishDir: Vector3.UnitX, Recess: true),
                ["wheel_centre"] = brass,
                ["wheel_third"] = brass,
                ["wheel_seconds"] = brass,
                ["intermediate"] = brass,
                ["cannon_wheel"] = brass,
                ["minute_wheel"] = brass,
                ["hour_wheel"] = brass,
                ["balance"] = new(Material.Brass, 1f, 0.16f, 0.36f, Finish.Circular, Recess: true),
                ["collet"] = new(Material.Brass, 1f, 0.22f, 0.22f, Recess: true),
                ["pinion_centre"] = pinion,
                ["pinion_third"] = pinion,
                ["pinion_seconds"] = pinion,
                ["intermediate_pinion"] = pinion,
                ["cannon_pinion"] = pinion,
                ["epinion"] = pinion,
                ["escape"] = new(Material.Steel, 1f, 0.36f, 0.36f, Recess: true),
                ["lever"] = new(new Vector3(0.55f, 0.56f, 0.58f), 1f, 0.04f, 0.04f, Finish.BlackPolish, Recess: true),
                ["guard"] = pinion,
                ["impulse_pin"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
                ["staff"] = new(Material.Steel, 1f, 0.10f, 0.10f, Recess: true),
                ["roller"] = pinion,
                ["hairspring"] = new(Material.Blued, 1f, 0.22f, 0.22f, Recess: true),
                ["stone_a"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
                ["stone_b"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
                ["stem"] = steel,
                ["barrel"] = plate,
                ["barrel_cover"] = plate,
                ["ratchet_wheel"] = pinion,
                ["mainspring"] = new(Material.Blued, 1f, 0.3f, 0.3f, Recess: true),
                ["crown_wheel"] = pinion,
                ["winding_pinion"] = pinion,
                ["sliding_pinion"] = pinion,
                ["setting_wheel"] = brass,
                ["setting_wheel_2"] = brass,
                ["regulator"] = steel with { Recess = true },
                ["stud_carrier"] = steel with { Recess = true },
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
