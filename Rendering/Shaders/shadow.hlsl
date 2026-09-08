// Depth-only pass from the key light. Same vertex layout and the same
// constant buffers as watch.hlsl so one Object upload serves both passes.
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
}
