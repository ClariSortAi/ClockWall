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
    float Lacquer = 0f)
{
    // ART-DIRECTION.md, "the palette, which is already decided". Linear.
    public static readonly Vector3 Steel = new(0.680f, 0.700f, 0.740f);
    public static readonly Vector3 Brass = new(0.740f, 0.560f, 0.260f);
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
    public float TrackRadius; public float DebugView; public Vector2 _pad;
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
}
