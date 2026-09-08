// The last pass: the resolved HDR frame -> the swap chain. Tone mapping,
// the sRGB curve, and compositing over the wall's own background colour at
// the corners of the panel around the round case. Alpha arrives as MSAA
// coverage - geometry writes 1, the clear was 0 - so the case edge is
// anti-aliased against the backdrop.
//
// WHY THE BACKDROP IS A CONSTANT AND NOT ALPHA. The swap chain is created
// premultiplied and this pass used to emit real alpha, and the XAML
// compositor painted the panel opaque black regardless - measured, not
// assumed (a strip forced to alpha 0 stayed black on the wall). So the panel
// composites itself: the wall behind it is one flat theme colour, the
// control hands that colour over, and the result is indistinguishable from
// transparency until somebody puts a gradient behind the clock.

cbuffer Post : register(b0)
{
    float4 Backdrop;   // sRGB wall colour behind the panel
};

Texture2D<float4> Frame  : register(t0);
SamplerState      Point  : register(s0);

struct VsOut { float4 clip : SV_Position; float2 uv : TEXCOORD0; };

VsOut VsFullscreen(uint id : SV_VertexID)
{
    VsOut o;
    float2 uv = float2((id << 1) & 2, id & 2);
    o.uv = uv;
    o.clip = float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
    return o;
}

// Khronos PBR Neutral: keeps the hue of a saturated blue where ACES pulls
// it toward cyan, which on a dial whose whole identity is one blue matters.
float3 ToneMap(float3 c)
{
    const float startCompression = 0.8 - 0.04;
    const float desaturation = 0.15;
    float x = min(c.r, min(c.g, c.b));
    float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
    c -= offset;
    float peak = max(c.r, max(c.g, c.b));
    if (peak < startCompression) return c;
    const float d = 1 - startCompression;
    float newPeak = 1 - d * d / (peak + d - startCompression);
    c *= newPeak / peak;
    float g = 1 - 1 / (desaturation * (peak - newPeak) + 1);
    return lerp(c, newPeak.xxx, g);
}

float3 ToSrgb(float3 c)
{
    return c <= 0.0031308 ? c * 12.92 : 1.055 * pow(c, 1 / 2.4) - 0.055;
}

float4 PsMain(VsOut i) : SV_Target
{
    float4 s = Frame.Sample(Point, i.uv);
    float a = saturate(s.a);
    // Colour was written premultiplied by coverage at resolve time (the
    // cleared samples are black), so un-premultiply before the curve and
    // re-premultiply after, or the edge pixels go dark.
    float3 c = a > 1e-4 ? s.rgb / a : 0;
    c = ToSrgb(saturate(ToneMap(max(c, 0))));
    return float4(lerp(Backdrop.rgb, c, a), 1);
}
