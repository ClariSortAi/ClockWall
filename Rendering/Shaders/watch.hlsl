// The watch: every opaque surface goes through this one shader pair, and the
// material is a handful of constants rather than a texture. That is not
// economy, it is the point of the pipeline - a sunburst dial, circular
// graining, cotes de Geneve and perlage are all ANISOTROPIC REFLECTION, a
// tangent field plus two roughnesses, and none of them can be a picture.
// See ART-DIRECTION.md, "the one effect that matters most".
//
// Row-major so a System.Numerics Matrix4x4 can be handed over byte for byte
// and used as mul(row_vector, M), which is the convention .NET already has.
#pragma pack_matrix(row_major)

static const float PI = 3.14159265f;

// Finish ids. Mirrored in Materials.cs; the number IS the contract.
static const int FINISH_ISO      = 0;  // plain isotropic
static const int FINISH_RADIAL   = 1;  // grain runs outward from FinishCentre: the sunburst
static const int FINISH_CIRCULAR = 2;  // grain runs around FinishCentre: circular graining
static const int FINISH_STRAIGHT = 3;  // grain along FinishDir, with scalloped stripes: cotes de Geneve
static const int FINISH_PERLAGE  = 4;  // small circular grains on a hex grid, overlapping
static const int FINISH_DIAL     = 5;  // radial, plus the aperture cut and the printed track
static const int FINISH_BLACK    = 6;  // black polish: a mirror so flat it reads dark

cbuffer Frame : register(b0)
{
    float4x4 ViewProj;
    float4x4 LightViewProj;
    float4x4 EnvRot;          // world -> environment lookup direction
    float3   CameraPos;   float Exposure;
    float3   LightDir;    float ShadowTexel;   // unit vector TOWARD the light
    float3   LightColour; float Time;
    float3   ApertureCentre; float ApertureRadius;
    float    DialRadius;  float TrackRadius; float DebugView; float _pad0;
};

cbuffer Object : register(b1)
{
    float4x4 World;
    float4   BaseColour;      // linear rgb; a = metalness
    float2   Roughness;       // along the grain, across the grain
    int      Finish;
    float    FinishScale;     // spacing of stripes / perlage spots, in mm
    float3   FinishCentre;    // world space
    float    Recess;          // 1 = this part sits in the aperture well
    float3   FinishDir;       // world space, unit
    float    Lacquer;         // clear-coat weight on top (the dial's lacquer)
};

TextureCube<float4> EnvSpecular  : register(t0);   // GGX-prefiltered, mips by roughness
TextureCube<float4> EnvDiffuse   : register(t1);   // cosine-convolved
Texture2D<float2>   BrdfLut      : register(t2);   // split-sum scale / bias
Texture2D<float>    ShadowMap    : register(t3);
Texture2D<float>    DialPrint    : register(t4);   // the lettering, a coverage mask in face units

SamplerState              LinearClamp : register(s0);
SamplerComparisonState    ShadowCmp   : register(s1);

struct VsIn  { float3 pos : POSITION; float3 nrm : NORMAL; };
struct VsOut
{
    float4 clip  : SV_Position;
    float3 world : TEXCOORD0;
    float3 nrm   : TEXCOORD1;
    float4 light : TEXCOORD2;
};

VsOut VsMain(VsIn v)
{
    VsOut o;
    float4 w = mul(float4(v.pos, 1), World);
    o.world = w.xyz;
    // Rigid transforms only, so the normal takes the same 3x3 - no inverse
    // transpose needed, and none is computed.
    o.nrm = mul(v.nrm, (float3x3)World);
    o.clip = mul(w, ViewProj);
    o.light = mul(w, LightViewProj);
    return o;
}

// ------------------------------------------------------------- the BRDF

// Anisotropic GGX (Burley 2012 parameterisation). at/ab are the roughness
// alphas along the tangent and bitangent; H is expressed in that frame.
float D_Aniso(float at, float ab, float ToH, float BoH, float NoH)
{
    float a2 = at * ab;
    float3 d = float3(ab * ToH, at * BoH, a2 * NoH);
    float d2 = dot(d, d);
    float w2 = a2 / d2;
    return a2 * w2 * w2 / PI;
}

// Height-correlated Smith visibility for the anisotropic lobe (Heitz 2014).
float V_Aniso(float at, float ab, float ToV, float BoV, float ToL, float BoL, float NoV, float NoL)
{
    float lambdaV = NoL * length(float3(at * ToV, ab * BoV, NoV));
    float lambdaL = NoV * length(float3(at * ToL, ab * BoL, NoL));
    return 0.5 / max(lambdaV + lambdaL, 1e-5);
}

float3 F_Schlick(float3 f0, float VoH)
{
    float f = pow(1.0 - VoH, 5.0);
    return f0 + (1.0 - f0) * f;
}

// ------------------------------------------------------------- the grain

// Where the scratches run at this point, in world space, before projection
// onto the surface. Returns a zero vector for "no grain here".
float3 GrainDirection(float3 P, float3 N, out float ripple)
{
    ripple = 0;
    float3 d = P - FinishCentre;
    d.y = 0;

    if (Finish == FINISH_RADIAL || Finish == FINISH_DIAL)
    {
        // Every scratch converges on the centre; right at it there is no
        // direction, and a real dial has a small plain boss there too.
        float r = length(d);
        return r < 0.05 ? 0 : d / r;
    }
    if (Finish == FINISH_CIRCULAR)
    {
        float r = length(d);
        return r < 0.05 ? 0 : cross(float3(0, 1, 0), d / r);
    }
    if (Finish == FINISH_STRAIGHT)
    {
        // Cotes de Geneve are shallow scallops, not a flat brushed sheet:
        // each stripe is a very slightly concave band, which is why they
        // alternate light and dark under one light and swap as it moves.
        // The tilt goes into the normal by the caller; here it is the
        // scratch direction along the stripe plus the scallop phase.
        float3 across = normalize(cross(float3(0, 1, 0), FinishDir));
        float t = frac(dot(P, across) / FinishScale);
        ripple = (t - 0.5) * 2.0;    // -1..1 across each stripe
        return FinishDir;
    }
    if (Finish == FINISH_PERLAGE)
    {
        // Overlapping circular grains on a hexagonal grid. Each spot is its
        // own tiny circular graining about its own centre; the eye reads
        // the fish-scale pattern from where those swirls change hands.
        float s = FinishScale;
        float2 p = float2(P.x, P.z) / s;
        float2 q = float2(p.x, p.y / 0.866);
        float2 cell = floor(q);
        float2 best = 0; float bestD = 1e9;
        [unroll] for (int j = -1; j <= 1; j++)
        [unroll] for (int i = -1; i <= 1; i++)
        {
            float2 c = cell + float2(i, j);
            float2 centre = float2(c.x + 0.5 * fmod(abs(c.y), 2.0), c.y * 0.866);
            float dd = distance(p, centre);
            if (dd < bestD) { bestD = dd; best = centre; }
        }
        float2 rel = p - best;
        float r = length(rel);
        // The graining stone leaves a faint ring where its edge stopped.
        ripple = smoothstep(0.40, 0.5, r) * 0.06;
        if (r < 0.01) return 0;
        return normalize(cross(float3(0, 1, 0), float3(rel.x, 0, rel.y)));
    }
    return 0;
}

// ------------------------------------------------------------- shadow

float Shadow(float3 P, float3 N, float NoL)
{
    // Normal-offset shadows. The receiver is pushed off its own surface
    // along the normal before projecting, further at grazing angles, so a
    // 5x5 kernel on a tilted plane never compares a texel against its own
    // neighbour's depth. Without this the dial showed the whole kernel as
    // moire - a plaid of bands across the sunburst, which is what shadow
    // acne looks like when the receiver is a metal lit by reflection.
    float3 offset = N * (0.10 + 0.25 * (1 - NoL));
    float4 lightClip = mul(float4(P + offset, 1), LightViewProj);
    float3 p = lightClip.xyz / lightClip.w;
    float2 uv = float2(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5);
    if (any(uv < 0) || any(uv > 1) || p.z > 1) return 1;

    // A small constant bias on top, in depth units: the map is a 180mm
    // range over 0..1, so this is a tenth of a millimetre.
    float z = p.z - 0.0006;

    // 5x5 PCF at a 2.5-texel step: about 0.4mm of penumbra on a 62mm map.
    // Wider than a point light would give on purpose - the hands stand a
    // millimetre off the dial under a softbox a metre wide, so their
    // shadows are soft, and the kernel is the penumbra.
    float sum = 0;
    [unroll] for (int y = -2; y <= 2; y++)
    [unroll] for (int x = -2; x <= 2; x++)
        sum += ShadowMap.SampleCmpLevelZero(ShadowCmp, uv + float2(x, y) * (2.5 * ShadowTexel), z);
    return sum / 25.0;
}

// ------------------------------------------------------------- pixel

float4 PsMain(VsOut i) : SV_Target
{
    float3 P = i.world;
    float3 N = normalize(i.nrm);
    float3 V = normalize(CameraPos - P);

    // The dial is one disc with the opening and its own rim cut here rather
    // than modelled, which keeps the triangle count of a hole at zero and
    // the edge exactly circular at any zoom.
    if (Finish == FINISH_DIAL)
    {
        float2 rel = P.xz - ApertureCentre.xz;
        if (dot(rel, rel) < ApertureRadius * ApertureRadius) discard;
        if (dot(P.xz, P.xz) > DialRadius * DialRadius) discard;
    }

    // CLOCKWALL_DEBUG_VIEW=1: every surface is a mirror of the environment
    // by its own normal, so the dial shows exactly what world +Y is aimed at
    // and the bezel's dome shows the neighbourhood. This is how the
    // environment's orientation is checked; reasoning about it was tried
    // and was wrong twice.
    if (DebugView > 0.5)
    {
        float3 dbg = EnvSpecular.SampleLevel(LinearClamp, mul(N, (float3x3)EnvRot), 0).rgb;
        return float4(dbg * Exposure, 1);
    }

    float ripple;
    float3 G = GrainDirection(P, N, ripple);

    if (Finish == FINISH_STRAIGHT)
    {
        // The scallop: tilt the normal across the stripe.
        float3 across = normalize(cross(float3(0, 1, 0), FinishDir));
        N = normalize(N + across * ripple * 0.035);
    }

    // Project the grain into the tangent plane. Where it has no component
    // there (a wall parallel to its own radial line) the finish degrades to
    // isotropic, which is what a machined edge looks like anyway.
    float3 T = G - N * dot(G, N);
    float tLen = length(T);
    float aniso = saturate(tLen * 4.0) * (dot(G, G) > 0.5 ? 1.0 : 0.0);
    T = tLen > 1e-4 ? T / tLen : normalize(cross(N, float3(0, 0, 1)));
    float3 B = cross(N, T);

    float rT = lerp(Roughness.y, Roughness.x, aniso);
    float rB = Roughness.y;
    if (Finish == FINISH_PERLAGE) { rT += ripple * 0.10; rB += ripple * 0.10; }
    rT = clamp(rT, 0.02, 1.0);
    rB = clamp(rB, 0.02, 1.0);
    float at = rT * rT, ab = rB * rB;

    float3 base = BaseColour.rgb;
    float metal = BaseColour.a;
    float3 f0 = lerp(0.04, base, metal);
    float3 albedo = base * (1.0 - metal);

    float NoV = max(dot(N, V), 1e-4);

    // One shadow lookup, shared: it cuts the key light outright, and it
    // also dims the environment term below, because the environment's
    // dominant source is the softbox the key stands in for. Without that,
    // a metal dial - lit almost entirely by reflection - would show no
    // shadow from the hands at all, and it is the hands' shadows that
    // put the hands ABOVE the dial rather than printed on it.
    float3 L = LightDir;
    float NoL = saturate(dot(N, L));
    float shadow = Shadow(P, N, NoL);

    // ---- key light
    float3 direct = 0;
    if (NoL > 0)
    {
        float3 H = normalize(L + V);
        float NoH = saturate(dot(N, H));
        float VoH = saturate(dot(V, H));
        float D = D_Aniso(at, ab, dot(T, H), dot(B, H), NoH);
        float Vis = V_Aniso(at, ab, dot(T, V), dot(B, V), dot(T, L), dot(B, L), NoV, NoL);
        float3 F = F_Schlick(f0, VoH);
        float3 spec = D * Vis * F;
        float3 diff = albedo / PI;
        direct = (diff + spec) * NoL * LightColour * shadow;

        if (Lacquer > 0)
        {
            // Clear coat: an isotropic, very smooth dielectric layer on top.
            float a = 0.06 * 0.06;
            float d = NoH * NoH * (a - 1) + 1;
            float Dc = a / (PI * d * d);
            float Fc = 0.04 + 0.96 * pow(1 - VoH, 5);
            direct += Dc * Fc * 0.25 * Lacquer * NoL * LightColour * shadow;
        }
    }

    // ---- environment
    // Anisotropic image-based lighting. A brushed surface's microfacets
    // tilt ACROSS the grain - they rotate about the grain direction T - so
    // its reflection of the studio is the isotropic reflection smeared
    // along the direction perpendicular to the grain. That is done
    // literally: the normal is swung about T through the lobe's width,
    // the environment is sampled at each swing, and the samples are
    // weighted by the lobe. Seven taps. The single bent-normal trick that
    // stood here first kept the reflection crisp along the streak, and the
    // eggcrate of the studio's softbox came through the sunburst as a
    // plaid; smearing it is what a real dial does to it.
    float3 envN = mul(N, (float3x3)EnvRot);
    float maxMip = 5.0;
    float roughMean = sqrt(rT * rB);
    float3 specIbl;
    if (aniso > 0.01)
    {
        // Width of the swing: the slope scale of GGX across the grain, as
        // an angle, and the along-grain roughness sets how blurred each
        // tap is.
        float spread = atan(ab) * 1.4 * aniso;
        float mipAlong = lerp(roughMean, rT, aniso) * maxMip;
        float3 sum = 0; float wsum = 0;
        [unroll] for (int k = -3; k <= 3; k++)
        {
            float w = k / 3.0;
            float weight = exp(-2.0 * w * w);
            float ang = w * spread;
            float3 n2 = normalize(N * cos(ang) + cross(T, N) * sin(ang));
            float3 R2 = reflect(-V, n2);
            sum += EnvSpecular.SampleLevel(LinearClamp, mul(R2, (float3x3)EnvRot), mipAlong).rgb * weight;
            wsum += weight;
        }
        specIbl = sum / wsum;
    }
    else
    {
        float3 R = reflect(-V, N);
        specIbl = EnvSpecular.SampleLevel(LinearClamp, mul(R, (float3x3)EnvRot), roughMean * maxMip).rgb;
    }
    float2 brdf = BrdfLut.Sample(LinearClamp, float2(NoV, roughMean));
    specIbl *= (f0 * brdf.x + brdf.y);
    float3 diffIbl = EnvDiffuse.SampleLevel(LinearClamp, envN, 0).rgb * albedo;

    if (Lacquer > 0)
    {
        // The clear coat's reflection of the room, sampled blurred for the
        // same reason the crystal's is: the softbox's eggcrate grid mirrored
        // crisply across the whole dial read as a plaid, and a lacquer a
        // few microns thick over a brushed metal is never that flat anyway.
        float3 Rc = mul(reflect(-V, N), (float3x3)EnvRot);
        float Fc = 0.04 + 0.96 * pow(1 - NoV, 5);
        specIbl += EnvSpecular.SampleLevel(LinearClamp, Rc, 2.6).rgb * Fc * Lacquer;
    }

    float3 ambient = (specIbl + diffIbl) * lerp(0.45, 1.0, shadow);

    // ---- the aperture is a recess
    // A point at the bottom of a well sees a smaller patch of sky the
    // deeper it sits and the nearer it is to the wall. This is the cheap
    // analytic form of that: the fraction of the opening's width visible
    // from here, against the depth below the dial. It is why the movement
    // is lit by less light than the dial is, and why it falls off at the rim.
    if (Recess > 0)
    {
        float edge = max(ApertureRadius - length(P.xz - ApertureCentre.xz), 0.0);
        float depth = max(ApertureCentre.y - P.y, 0.0);
        float ao = edge / sqrt(edge * edge + depth * depth);
        ao = lerp(0.03, 0.42, ao);
        ambient *= ao;
    }

    // ---- black polish
    if (Finish == FINISH_BLACK)
    {
        // Black polish is a mirror finish; in a studio it reflects the
        // dark room from almost every angle and flares only when a source
        // lines up. The env is already doing that; this just keeps the
        // diffuse floor out of it.
        ambient *= 0.6;
    }

    float3 colour = direct + ambient;

    // ---- the printed minute track on the dial
    if (Finish == FINISH_DIAL)
    {
        float r = length(P.xz);
        float ang = atan2(P.x, -P.z);              // clockwise from twelve
        float minute = ang / (2 * PI) * 60.0;
        float f = abs(frac(minute) - 0.5);          // 0 at a mark
        float tickLen = (abs(frac(minute / 5.0 + 0.5) - 0.5) < 0.05) ? 0.55 : 0.32;
        float halfW = 0.05;
        float alongMark = saturate((r - TrackRadius) / tickLen);
        float onMark = (f < halfW && r > TrackRadius && r < TrackRadius + tickLen) ? 1.0 : 0.0;
        // Ink is a matte pad print sitting on top of the lacquer; it takes
        // the diffuse light and none of the sunburst. The lettering comes
        // from a mask drawn in face units - 640 across the dial's square -
        // so world millimetres map back through the same scale.
        float2 faceUv = P.xz * (11.780018 / 640.0) + 0.5;
        float print = DialPrint.Sample(LinearClamp, faceUv);
        float3 ink = float3(0.80, 0.85, 0.96);
        float3 inkLit = ink * (EnvDiffuse.SampleLevel(LinearClamp, envN, 0).rgb * lerp(0.45, 1.0, shadow)
                               + LightColour * NoL * shadow / PI);
        colour = lerp(colour, inkLit, max(onMark, print));
    }

    return float4(colour * Exposure, 1.0);
}
