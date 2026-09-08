// Depth-only pass from the key light. Same vertex layout and the same
// Object constants as watch.hlsl, because the dial has to cut its aperture
// here too - a hole the shadow map does not know about is a hole that casts
// a shadow, and the movement would sit in the dark.
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
    float    DialRadius;  float TrackRadius; float DebugView; float _pad0;
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
};

struct VsIn  { float3 pos : POSITION; float3 nrm : NORMAL; };
struct VsOut { float4 clip : SV_Position; float3 world : TEXCOORD0; };

VsOut VsMain(VsIn v)
{
    VsOut o;
    float4 w = mul(float4(v.pos, 1), World);
    o.world = w.xyz;
    o.clip = mul(w, LightViewProj);
    return o;
}

void PsMain(VsOut i)
{
    if (Finish == 5)   // FINISH_DIAL
    {
        float2 rel = i.world.xz - ApertureCentre.xz;
        if (dot(rel, rel) < ApertureRadius * ApertureRadius) discard;
        if (dot(i.world.xz, i.world.xz) > DialRadius * DialRadius) discard;
    }
}
