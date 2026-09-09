using System.Numerics;
using System.Runtime.InteropServices;

namespace ClockWall.Rendering;

/// <summary>Finish ids, mirrored from watch.hlsl. The number is the contract.</summary>
internal enum Finish
{
    Isotropic = 0,
    Radial = 1,
    Circular = 2,
    Straight = 3,
    Perlage = 4,
    Dial = 5,
    BlackPolish = 6,
    /// <summary>The hairspring: blued steel, and the vertex shader winds it
    /// with the balance - see watch.hlsl. FinishCentre is the staff,
    /// FinishDir.xy the inner and outer coil radii.</summary>
    Hairspring = 7,
}

/// <summary>
/// One surface: the palette entry plus how it was finished. This is the
/// whole of a material in this renderer - there are no textures, because
/// every finish on a watch is a tangent field and two roughnesses, and
/// ART-DIRECTION.md has already decided the palette.
/// </summary>
internal readonly record struct Material(
    Vector3 BaseColour,
    float Metal,
    float RoughAlong,
    float RoughAcross,
    Finish Finish = Finish.Isotropic,
    float FinishScale = 1f,
    Vector3 FinishCentre = default,
    Vector3 FinishDir = default,
    bool Recess = false,
    float Lacquer = 0f,
    Vector3 Eta = default,
    Vector3 Kappa = default)
{
    // ---- metals, by their measured optical constants
    // A metal's look is its Fresnel reflectance: the complex refractive
    // index n + ik at each wavelength, from the literature, evaluated
    // exactly in the shader (the conductor Fresnel equations). Nothing is a
    // colour; the reflectance at normal incidence (F0, below) falls out of
    // n and k, and so does the shift toward white at grazing that says
    // "gold" rather than "yellow". Red, green, blue at 650, 550, 450 nm.
    //   gold   Johnson & Christy, Phys. Rev. B 6, 4370 (1972)
    //   iron   Johnson & Christy, Phys. Rev. B 9, 5056 (1974): the steel
    //   brass  Querry, Optical constants of minerals and other materials
    //          (1985), a 70/30 alloy, read off the curves - approximate
    public static readonly Vector3 GoldN = new(0.18f, 0.42f, 1.37f), GoldK = new(3.42f, 2.35f, 1.77f);
    public static readonly Vector3 IronN = new(2.87f, 2.90f, 2.53f), IronK = new(3.36f, 3.17f, 2.83f);
    public static readonly Vector3 BrassN = new(0.44f, 0.53f, 1.06f), BrassK = new(3.60f, 2.70f, 2.20f);

    /// <summary>Reflectance at normal incidence from n and k: ((n-1)^2 + k^2) / ((n+1)^2 + k^2).</summary>
    public static Vector3 F0(Vector3 n, Vector3 k)
    {
        static float one(float n, float k) => ((n - 1) * (n - 1) + k * k) / ((n + 1) * (n + 1) + k * k);
        return new Vector3(one(n.X, k.X), one(n.Y, k.Y), one(n.Z, k.Z));
    }

    /// <summary>A polished metal from its constants: base colour is its F0,
    /// and the shader gets n and k for the exact Fresnel curve.</summary>
    public static Material Conductor(Vector3 n, Vector3 k, float roughAlong, float roughAcross, Finish finish = Finish.Isotropic,
                                     float finishScale = 1f, Vector3 finishCentre = default, Vector3 finishDir = default, bool recess = false)
        => new(F0(n, k), 1f, roughAlong, roughAcross, finish, finishScale, finishCentre, finishDir, recess, 0f, n, k);

    // ART-DIRECTION.md, "the palette, which is already decided". Linear.
    // Steel and brass stay the palette's tones. Iron's constants were tried
    // for the case (2026-09-09) and made it cream: iron's F0 is warm (0.56,
    // 0.54, 0.51), and a polished stainless case reads white because its
    // chromium-rich surface does not, for which no per-wavelength constants
    // were to hand. A tone chosen from photographs of the real thing beats
    // the wrong metal's physics. Gold has its constants; it is the one
    // metal here whose look IS its Fresnel curve.
    public static readonly Vector3 Steel = new(0.680f, 0.700f, 0.740f);
    public static readonly Vector3 Brass = new(0.740f, 0.560f, 0.260f);
    public static readonly Vector3 Gold = F0(GoldN, GoldK);
    // Blued steel is not a metal's constants: its colour is a thin oxide
    // film's interference over iron, and stays a colour until that film is
    // modelled. Ruby is a dielectric.
    public static readonly Vector3 Blued = new(0.035f, 0.075f, 0.300f);
    public static readonly Vector3 Ruby = new(0.560f, 0.060f, 0.090f);

    /// <summary>The plate and bridges: rhodium-plated brass in a modern
    /// movement, which is a cooler, slightly darker grey than the case
    /// steel. Cold on purpose - the brief allows warmth only from the wheels
    /// and the two stones.</summary>
    public static readonly Vector3 Plate = new(0.36f, 0.37f, 0.40f);

    /// <summary>The dial's body tone, "mid" in dial_render.py: sRGB (28, 56,
    /// 118) taken to linear. The shadow and hot tones are not colours here -
    /// they are what this one colour does under the anisotropic lobe.</summary>
    public static readonly Vector3 DialBlue = new(0.0116f, 0.0395f, 0.1810f);

    public ObjectConstants ToConstants(Matrix4x4 world) => new()
    {
        World = world,
        BaseColour = new Vector4(BaseColour, Metal),
        Roughness = new Vector2(RoughAlong, RoughAcross),
        Finish = (int)Finish,
        FinishScale = FinishScale,
        FinishCentre = FinishCentre,
        Recess = Recess ? 1f : 0f,
        FinishDir = FinishDir,
        Lacquer = Lacquer,
        Opacity = 1f,
        Eta = Eta,
        Conductor = Kappa == default ? 0f : 1f,
        Kappa = Kappa,
    };
}

/// <summary>Per-frame constants. Layout matches cbuffer Frame in the shaders.</summary>
[StructLayout(LayoutKind.Sequential)]
internal struct FrameConstants
{
    public Matrix4x4 ViewProj;
    public Matrix4x4 LightViewProj;
    public Matrix4x4 EnvRot;
    public Vector3 CameraPos; public float Exposure;
    public Vector3 LightDir; public float ShadowTexel;
    public Vector3 LightColour; public float Time;
    public Vector3 ApertureCentre; public float ApertureRadius;
    public Vector3 Aperture2Centre; public float Aperture2Radius;   // the keyhole's bulge round the seconds
    public float TrackRadius; public float DebugView;
    public float EnvScale;      // the HDRI's units to pre-exposed lux: ambient / its own irradiance, times exposure
    public float LightHalfTan;  // tan of the key's angular radius: the softbox's size, for penumbra and highlight width
}

/// <summary>The post pass's constants: the wall colour and the focus.</summary>
[StructLayout(LayoutKind.Sequential)]
internal struct PostConstants
{
    public Vector4 Backdrop;
    public Vector4 Focus;
}

/// <summary>Per-draw constants. Layout matches cbuffer Object in the shaders.</summary>
[StructLayout(LayoutKind.Sequential)]
internal struct ObjectConstants
{
    public Matrix4x4 World;
    public Vector4 BaseColour;
    public Vector2 Roughness; public int Finish; public float FinishScale;
    public Vector3 FinishCentre; public float Recess;
    public Vector3 FinishDir; public float Lacquer;
    public float Opacity; public float Breathe; public Vector2 _pad;
    public Vector3 Eta; public float Conductor;     // the metal's n, and whether n and k are to be used
    public Vector3 Kappa; public float _pad2;       // the metal's k
}
