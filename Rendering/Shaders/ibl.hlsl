// Image-based lighting, precomputed once at load from the studio HDRI:
//   PsEquirect   - equirectangular panorama -> one cube face
//   PsPrefilter  - GGX-prefiltered specular cube, one mip per roughness
//   PsIrradiance - cosine-convolved diffuse cube
//   PsBrdf       - the split-sum scale/bias lookup
// All four draw a full-screen triangle; the constants say which face and
// which roughness. The whole set takes a few milliseconds on the 2070 and
// then never runs again, which is why nothing here is optimised.
#pragma pack_matrix(row_major)

static const float PI = 3.14159265f;

cbuffer Params : register(b0)
{
    int   Face;        // 0..5, D3D cube order +X -X +Y -Y +Z -Z
    float Roughness;   // for PsPrefilter
    float SourceSize;  // width of the source texture, for mip-based sample filtering
    int   Samples;
};

Texture2D<float4>   Equirect : register(t0);
TextureCube<float4> Source   : register(t1);
SamplerState        Linear   : register(s0);

struct VsOut { float4 clip : SV_Position; float2 uv : TEXCOORD0; };

VsOut VsFullscreen(uint id : SV_VertexID)
{
    VsOut o;
    float2 uv = float2((id << 1) & 2, id & 2);
    o.uv = uv;
    o.clip = float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
    return o;
}

// The direction a cube-face texel looks along.
float3 FaceDirection(int face, float2 uv)
{
    float2 st = uv * 2 - 1;     // -1..1, +x right, +y down
    switch (face)
    {
        case 0: return normalize(float3( 1, -st.y, -st.x));
        case 1: return normalize(float3(-1, -st.y,  st.x));
        case 2: return normalize(float3( st.x,  1,  st.y));
        case 3: return normalize(float3( st.x, -1, -st.y));
        case 4: return normalize(float3( st.x, -st.y,  1));
        default:return normalize(float3(-st.x, -st.y, -1));
    }
}

// A direction into the panorama. Latitude from +Y; longitude from -Z going
// through +X, which puts the panorama's centre column straight ahead of a
// camera looking down -Z. The EnvRot matrix in the main pass supplies
// whatever orientation the watch wants on top of this.
float2 EquirectUv(float3 d)
{
    float u = atan2(d.x, -d.z) / (2 * PI) + 0.5;
    float v = acos(clamp(d.y, -1, 1)) / PI;
    return float2(u, v);
}

float4 PsEquirect(VsOut i) : SV_Target
{
    float3 d = FaceDirection(Face, i.uv);
    float3 c = Equirect.SampleLevel(Linear, EquirectUv(d), 0).rgb;
    // The softboxes peak in the hundreds. A camera would clip them, and a
    // blue dial under one wants to read pale blue - the palette's "hot"
    // tone - not white. Scale the whole studio down and knee the peaks, so
    // the dial's dark F0 times a softbox lands in range.
    c *= 0.35;
    c = c / (1 + c / 9.0);
    // A fill: the studio's dark corners lifted to a soft grey, the way a
    // watch photographer puts white card round the subject. Polished
    // steel that happens to reflect the back of the room then reads as
    // silver rather than as a hole, which is what the hands did without it.
    c += 0.12;
    return float4(c, 1);
}

float RadicalInverse(uint bits)
{
    bits = (bits << 16u) | (bits >> 16u);
    bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);
    bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);
    bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);
    bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);
    return float(bits) * 2.3283064365386963e-10;
}

float2 Hammersley(uint i, uint n) { return float2(float(i) / float(n), RadicalInverse(i)); }

float3 ImportanceSampleGGX(float2 xi, float a, float3 N)
{
    float phi = 2 * PI * xi.x;
    float cosTheta = sqrt((1 - xi.y) / (1 + (a * a - 1) * xi.y));
    float sinTheta = sqrt(1 - cosTheta * cosTheta);
    float3 h = float3(sinTheta * cos(phi), sinTheta * sin(phi), cosTheta);
    float3 up = abs(N.z) < 0.999 ? float3(0, 0, 1) : float3(1, 0, 0);
    float3 tx = normalize(cross(up, N));
    float3 ty = cross(N, tx);
    return normalize(tx * h.x + ty * h.y + N * h.z);
}

float4 PsPrefilter(VsOut i) : SV_Target
{
    float3 N = FaceDirection(Face, i.uv);
    float3 V = N;
    float a = max(Roughness * Roughness, 0.002);
    float3 sum = 0; float weight = 0;
    uint n = (uint)Samples;
    for (uint s = 0; s < n; s++)
    {
        float3 H = ImportanceSampleGGX(Hammersley(s, n), a, N);
        float3 L = 2 * dot(V, H) * H - V;
        float NoL = saturate(dot(N, L));
        if (NoL > 0)
        {
            // Sample from a mip chosen by the lobe's solid angle against
            // the texel's, which is what turns 256 samples into a smooth
            // result instead of fireflies from the softboxes.
            float NoH = saturate(dot(N, H));
            float D = a * a / (PI * pow(NoH * NoH * (a * a - 1) + 1, 2));
            float pdf = D * NoH / (4 * NoH) + 1e-4;
            float saTexel = 4 * PI / (6 * SourceSize * SourceSize);
            float saSample = 1 / (float(n) * pdf + 1e-4);
            float mip = Roughness == 0 ? 0 : 0.5 * log2(saSample / saTexel) + 1;
            sum += Source.SampleLevel(Linear, L, mip).rgb * NoL;
            weight += NoL;
        }
    }
    return float4(sum / max(weight, 1e-4), 1);
}

float4 PsIrradiance(VsOut i) : SV_Target
{
    float3 N = FaceDirection(Face, i.uv);
    float3 up = abs(N.z) < 0.999 ? float3(0, 0, 1) : float3(1, 0, 0);
    float3 tx = normalize(cross(up, N));
    float3 ty = cross(N, tx);
    float3 sum = 0; float count = 0;
    // A regular sweep over the hemisphere off a small mip of the cube: the
    // source is already blurred, so a coarse sweep is enough.
    for (float phi = 0; phi < 2 * PI; phi += 0.06)
    for (float theta = 0; theta < 0.5 * PI; theta += 0.06)
    {
        float3 t = float3(sin(theta) * cos(phi), sin(theta) * sin(phi), cos(theta));
        float3 d = tx * t.x + ty * t.y + N * t.z;
        sum += Source.SampleLevel(Linear, d, 3).rgb * cos(theta) * sin(theta);
        count += 1;
    }
    return float4(PI * sum / count, 1);
}

float2 PsBrdf(VsOut i) : SV_Target
{
    float NoV = max(i.uv.x, 1e-3);
    float rough = 1 - i.uv.y;
    float a = max(rough * rough, 0.002);
    float3 V = float3(sqrt(1 - NoV * NoV), 0, NoV);
    float3 N = float3(0, 0, 1);
    float A = 0, B = 0;
    const uint n = 512;
    for (uint s = 0; s < n; s++)
    {
        float3 H = ImportanceSampleGGX(Hammersley(s, n), a, N);
        float3 L = 2 * dot(V, H) * H - V;
        float NoL = saturate(L.z), NoH = saturate(H.z), VoH = saturate(dot(V, H));
        if (NoL > 0)
        {
            float k = a / 2;
            float g1v = NoV / (NoV * (1 - k) + k);
            float g1l = NoL / (NoL * (1 - k) + k);
            float gVis = g1v * g1l * VoH / (NoH * NoV);
            float fc = pow(1 - VoH, 5);
            A += (1 - fc) * gVis;
            B += fc * gVis;
        }
    }
    return float2(A, B) / n;
}
