// The sapphire crystal, drawn last over everything, additively. What a
// crystal contributes is a faint specular sheet that moves independently of
// the dial under it, and the violet-blue residual an anti-reflective coating
// leaves at glancing angles. ART-DIRECTION.md: keep it subtle, a strong
// reflection reads as plastic. Refraction is not modelled - at this dome
// height and this viewing distance it moves the dial's edge by less than a
// pixel, and a wrong refraction is worse than none.
#pragma pack_matrix(row_major)

cbuffer Frame : register(b0)
{
    float4x4 ViewProj;
    float4x4 LightViewProj;
    float4x4 EnvRot;
    float3   CameraPos;   float Exposure;
    float3   LightDir;    float ShadowTexel;
    float3   LightColour; float Time;
    float3   ApertureCentre; float ApertureRadius;
    float    TrackRadius; float DebugView; float2 _pad0;
};

cbuffer Object : register(b1)
{
    float4x4 World;
    float4   BaseColour;
    float2   Roughness;
    int      Finish;
    float    FinishScale;
    float3   FinishCentre;
    float    Recess;
    float3   FinishDir;
    float    Lacquer;
    float    Opacity;
    float3   _pad1;
};

TextureCube<float4> EnvSpecular : register(t0);
SamplerState        LinearClamp : register(s0);

struct VsIn  { float3 pos : POSITION; float3 nrm : NORMAL; };
struct VsOut { float4 clip : SV_Position; float3 world : TEXCOORD0; float3 nrm : TEXCOORD1; };

VsOut VsMain(VsIn v)
{
    VsOut o;
    float4 w = mul(float4(v.pos, 1), World);
    o.world = w.xyz;
    o.nrm = mul(v.nrm, (float3x3)World);
    o.clip = mul(w, ViewProj);
    return o;
}

float4 PsMain(VsOut i) : SV_Target
{
    float3 N = normalize(i.nrm);
    float3 V = normalize(CameraPos - i.world);
    float NoV = saturate(dot(N, V));

    // Sapphire is n=1.77, F0 about 0.077; a multilayer AR coat knocks the
    // normal-incidence reflection down to under a percent and leaves a
    // residual that rises toward grazing and is coloured - blue-violet for
    // the common coatings. Both are in this one line.
    float f = pow(1 - NoV, 5);
    float3 coat = float3(0.55, 0.50, 1.00);
    float3 F = (0.006 + 0.07 * f) * coat;

    // Sampled blurred on purpose. The studio's softbox has an eggcrate
    // grid, and a smooth dome reflecting it crisply laid a plaid over the
    // whole dial; the crystal is not where that detail belongs.
    float3 R = mul(reflect(-V, N), (float3x3)EnvRot);
    float3 env = EnvSpecular.SampleLevel(LinearClamp, R, 2.6).rgb;

    // The key light's own glint on the dome: a tight, moving spot that is
    // the one place a crystal is allowed to be obviously present.
    float3 H = normalize(LightDir + V);
    float NoH = saturate(dot(N, H));
    float a = 0.03 * 0.03;
    float d = NoH * NoH * (a - 1) + 1;
    float glint = a / (3.14159 * d * d) * 0.25 * saturate(dot(N, LightDir));

    float3 colour = env * F + LightColour * glint * F * 6.0;
    return float4(colour * Exposure, 0);
}
