// The sapphire crystal, as a piece of glass rather than a sheet of light.
//
// Drawn after the opaque frame has been resolved into Behind, and it
// REPLACES what is under it with what a ray through the glass would see.
// Per pixel of the crystal's top surface:
//
//   1. The top surface reflects the room and the key light, by the
//      Fresnel reflectance of a quarter-wave anti-reflective film on
//      sapphire, computed as thin-film interference at three wavelengths.
//      That is where the violet residual comes from - it is not a colour
//      typed in, it is what a single MgF2 layer tuned to 550 nm leaves at
//      the ends of the spectrum, rising toward grazing.
//   2. The rest refracts in (n = 1.77), crosses the sapphire to its flat
//      underside, and refracts out again toward the dial. The point it
//      lands on is projected back to the screen and Behind is read there:
//      the dial seen THROUGH the crystal. Under the dome the shift is a
//      fraction of a pixel, as the arithmetic in the old version said; at
//      the bevel and the side, where the normal tilts forty degrees, it
//      is millimetres, and the dial's rim, the rehaut and the indices bend
//      round the edge - which is the thing the eye reads as glass.
//   3. The underside is a second mirror. Part of the light that got in is
//      reflected back up by it (the same film, from inside), refracts out
//      through the top, and shows the room a second time, fainter and
//      offset by twice the dome's tilt: the double glint every domed
//      crystal shows under one lamp.
//   4. The key light's glint on both surfaces, and the wear (one scratch,
//      some dust; tools/crystal_wear.py) lit as grooves and specks.
//
// Sapphire absorbs nothing at this thickness, so transmission is one minus
// the two reflectances and no more. What is NOT here: the light the dial
// throws up at the underside and gets back (veiling glare, well under a
// percent with the film), dispersion in the refraction direction (the
// three wavelengths differ by 1.2% in index; in a 2 mm plate that is a
// tenth of a pixel), and polarisation of the room's light.
//
// ART-DIRECTION.md: keep it subtle, a strong reflection reads as plastic.
// With both surfaces coated the reflections are subtle because the physics
// says so, not because a constant does.
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
    float3   Aperture2Centre; float Aperture2Radius;
    float    TrackRadius; float DebugView; float EnvScale; float LightHalfTan;
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
    float3   Eta;       float Conductor;   // a metal's n, and whether the exact conductor Fresnel applies
    float3   Kappa;     float _pad2;       // its k
};

TextureCube<float4> EnvSpecular : register(t0);
Texture2D<float4>   Wear        : register(t1);   // R scratch, G dust, B scratch direction / pi; face units
Texture2D<float4>   Behind      : register(t2);   // the opaque frame, resolved, before the crystal
SamplerState        LinearClamp : register(s0);

static const float PI = 3.14159265;

// ---- the material, by the numbers
// Sapphire (Al2O3, ordinary ray) and the coating's two materials at 650,
// 550, 450 nm. The coating is a four-layer broadband anti-reflective stack,
// MgF2 / TiO2 / MgF2 / TiO2 from the air down, thicknesses found by
// minimising the mean reflectance over 430-670 nm at 0 and 30 degrees on a
// sapphire substrate (the transfer-matrix method, in a scratch script):
// 0.1-0.2% at normal incidence, 0.7% at 45, 4-6% at 60, red-biased toward
// grazing. A single quarter-wave MgF2 film was tried first: 0.6% red and
// 1.1% blue at normal incidence, which on a dark blue dial reads as a
// magenta veil over everything, and it does on real single-coated glass.
static const float3 N_SAPPHIRE = float3(1.762, 1.771, 1.784);
static const float3 N_MGF2     = float3(1.376, 1.380, 1.386);
static const float3 N_TIO2     = float3(2.29, 2.35, 2.45);
static const float3 LAMBDA_NM  = float3(650.0, 550.0, 450.0);
static const float4 LAYER_NM   = float4(114.1, 29.0, 33.6, 24.6);   // air side first
static const float  N_REFRACT  = 1.771;                    // the direction is traced at the middle index
// The crystal's flat underside in world millimetres: case_solids.CRYSTAL_UNDER.
static const float  UNDER_Y    = 1.9;
// Where "what is behind" is taken to lie for the reprojection: between the
// dial (0) and the hands (1.1 to 1.7). Being off by a millimetre here moves
// the refracted sample by a fraction of a pixel.
static const float  BEHIND_Y   = 0.5;

// Complex helpers on float2 (re, im).
float2 cmul(float2 a, float2 b) { return float2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
float2 cdiv(float2 a, float2 b) { float d = dot(b, b); return float2(a.x * b.x + a.y * b.y, a.y * b.x - a.x * b.y) / d; }

// Reflectance of the four-layer stack between n0 (where the light is) and
// nExit, for one polarisation, at incidence cos0 in n0 and wavelength
// lambda: the characteristic-matrix (transfer-matrix) method. Each layer
// is [cos d, i sin d / eta; i eta sin d, cos d] with eta = n cos (s) or
// n / cos (p); the stack's product times [1; eta_exit] gives B and C and
// r = (eta0 B - C) / (eta0 B + C). Returns 1 past total internal
// reflection at the exit. The layers are listed from the n0 side, so from
// inside the glass they run in reverse.
float StackReflectance(float n0, float nExit, float4 nLayer, float4 dLayer, float lambda, float cos0, bool pPol, bool reverse)
{
    float sin0 = n0 * sqrt(saturate(1 - cos0 * cos0));
    if (sin0 >= nExit) return 1.0;
    float2 m00 = float2(1, 0), m01 = 0, m10 = 0, m11 = float2(1, 0);
    [unroll] for (int j = 0; j < 4; j++)
    {
        int k = reverse ? 3 - j : j;
        float n = nLayer[k], d = dLayer[k];
        float c = sqrt(saturate(1 - (sin0 / n) * (sin0 / n)));
        float eta = pPol ? n / max(c, 1e-4) : n * c;
        float delta = 2 * PI * n * d * c / lambda;
        float cd = cos(delta), sd = sin(delta);
        // layer L = [cd, i sd/eta; i eta sd, cd]; M = M * L
        float2 l00 = float2(cd, 0), l01 = float2(0, sd / eta), l10 = float2(0, eta * sd), l11 = float2(cd, 0);
        float2 a00 = cmul(m00, l00) + cmul(m01, l10);
        float2 a01 = cmul(m00, l01) + cmul(m01, l11);
        float2 a10 = cmul(m10, l00) + cmul(m11, l10);
        float2 a11 = cmul(m10, l01) + cmul(m11, l11);
        m00 = a00; m01 = a01; m10 = a10; m11 = a11;
    }
    float cE = sqrt(saturate(1 - (sin0 / nExit) * (sin0 / nExit)));
    float etaExit = pPol ? nExit / max(cE, 1e-4) : nExit * cE;
    float eta0 = pPol ? n0 / max(cos0, 1e-4) : n0 * cos0;
    float2 B = m00 + m01 * etaExit;
    float2 C = m10 + m11 * etaExit;
    float2 r = cdiv(eta0 * B - C, eta0 * B + C);
    return dot(r, r);
}

// The coated surface's reflectance in RGB, unpolarised, from outside
// (air -> stack -> sapphire) or from inside (sapphire -> stack -> air).
float3 CoatedReflectance(float cosI, bool fromInside)
{
    float3 r;
    [unroll] for (int k = 0; k < 3; k++)
    {
        float n0 = fromInside ? N_SAPPHIRE[k] : 1.0;
        float nExit = fromInside ? 1.0 : N_SAPPHIRE[k];
        float4 nLayer = float4(N_MGF2[k], N_TIO2[k], N_MGF2[k], N_TIO2[k]);
        r[k] = 0.5 * (StackReflectance(n0, nExit, nLayer, LAYER_NM, LAMBDA_NM[k], cosI, false, fromInside)
                    + StackReflectance(n0, nExit, nLayer, LAYER_NM, LAMBDA_NM[k], cosI, true, fromInside));
    }
    return saturate(r);
}

float2 ScreenUv(float3 world)
{
    float4 clip = mul(float4(world, 1), ViewProj);
    return clip.xy / clip.w * float2(0.5, -0.5) + 0.5;
}

// GGX lobe of a polished surface, for the key light's glint.
float Glint(float NoH, float rough)
{
    float a = rough * rough;
    float d = NoH * NoH * (a - 1) + 1;
    return a / (PI * d * d);
}

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
    float3 P = i.world;
    float3 N = normalize(i.nrm);
    float3 V = normalize(CameraPos - P);
    float NoV = saturate(dot(N, V));
    float3 up = float3(0, 1, 0);

    // ---- 1. the top surface
    float3 R1 = CoatedReflectance(NoV, false);
    float3 Rtop = mul(reflect(-V, N), (float3x3)EnvRot);
    // Sampled blurred on purpose: the studio's softbox has an eggcrate
    // grid, and a polished dome reflecting it crisply laid a plaid over
    // the whole dial. A crystal is not where that detail belongs.
    float3 envTop = EnvSpecular.SampleLevel(LinearClamp, Rtop, 2.6).rgb * EnvScale;
    float3 H = normalize(LightDir + V);
    // The key's glint: a polished surface (alpha 0.03^2) widened by the
    // softbox's angular radius (Karis 2013), so the glint is the softbox's
    // own luminance E / Omega spread over its size, not a pinprick of
    // infinite brightness. D * F / (4 NoV) is the mirror-limit BRDF times
    // cos, times E, and the energy is renormalised for the widening.
    float aTop = 0.03 * 0.03 + LightHalfTan * 0.5;
    float glintTop = Glint(saturate(dot(N, H)), sqrt(aTop)) * (0.03 * 0.03 / aTop) / (4.0 * max(NoV, 0.05)) * saturate(dot(N, LightDir));

    // ---- 2. through the glass
    float3 Tin = refract(-V, N, 1.0 / N_REFRACT);          // into the sapphire, heading down
    float3 behind = Behind.SampleLevel(LinearClamp, ScreenUv(P), 0).rgb;
    float  behindA = Behind.SampleLevel(LinearClamp, ScreenUv(P), 0).a;
    float3 R2 = 0;
    float3 transmitted = behind;
    float3 envInner = 0;
    float  glintUnder = 0;
    if (Tin.y < -1e-4)
    {
        // To the underside.
        float tUnder = (P.y - UNDER_Y) / -Tin.y;
        float3 Pu = P + Tin * tUnder;
        float cosU = -Tin.y;                                // incidence on the flat underside, from inside
        R2 = CoatedReflectance(cosU, true);
        // Out through the underside and on to what is behind.
        float3 Tout = refract(Tin, up, N_REFRACT);
        if (dot(Tout, Tout) > 0.5 && Tout.y < -1e-4)
        {
            float3 Pb = Pu + Tout * ((Pu.y - BEHIND_Y) / -Tout.y);
            float2 uv = saturate(ScreenUv(Pb));
            transmitted = Behind.SampleLevel(LinearClamp, uv, 0).rgb;
        }
        else
        {
            // Total internal reflection at the underside: nothing from the
            // dial gets out here, the ray goes back up and shows the room.
            R2 = 1;
        }
        // ---- 3. the underside as a second mirror
        float3 Tr = reflect(Tin, up);                        // back up inside the glass
        float3 Rout = refract(Tr, -N, N_REFRACT);            // out through the top
        if (dot(Rout, Rout) > 0.5)
            envInner = EnvSpecular.SampleLevel(LinearClamp, mul(Rout, (float3x3)EnvRot), 2.6).rgb * EnvScale;
        else
            envInner = envTop;                               // trapped: it leaves elsewhere, near enough the same room
        // The key light's glint on the underside: the light refracted in
        // at this tilt, mirrored by the flat underside toward the eye's
        // own refracted path.
        float3 Lin = refract(-LightDir, N, 1.0 / N_REFRACT);
        if (Lin.y < 0)
        {
            float3 Hu = normalize(-Tin + -Lin);
            float aUnder = 0.02 * 0.02 + LightHalfTan * 0.5;
            glintUnder = Glint(saturate(Hu.y), sqrt(aUnder)) * (0.02 * 0.02 / aUnder) / (4.0 * max(NoV, 0.05)) * saturate(dot(N, LightDir));
        }
    }

    float3 T1 = 1 - R1;
    float3 colour = transmitted * T1 * (1 - R2)                                  // the dial, through both surfaces
                  + (envTop * R1 + LightColour * glintTop * R1) * Exposure          // the top surface's room and glint
                  + (envInner + LightColour * glintUnder) * T1 * R2 * T1 * Exposure; // the underside's, twice through the top

    // ---- 4. the wear: one hairline scratch and a little dust (tools/crystal_wear.py)
    // A scratch is a groove: a tiny cylinder lying in the surface. It
    // scatters light like a hair does (Kajiya-Kay) - brightest where the
    // half-vector lies ACROSS it - so it is invisible from most angles and
    // flares as the rig drifts the key light over it. It also catches a
    // little of the whole room, which is why a scratch shows faintly
    // against a dark dial out of the glint. Dust sits proud of the glass,
    // lit from above by the key and by the room, and not anisotropic at all.
    float2 faceUv = P.xz * (11.780018 / 640.0) + 0.5;
    float3 wear = Wear.SampleLevel(LinearClamp, faceUv, 0).rgb;
    if (wear.r + wear.g > 0.002)
    {
        float a = wear.b * PI;
        float3 Tsc = float3(cos(a), 0, -sin(a));
        float TH = dot(Tsc, H);
        float sinTH = sqrt(saturate(1 - TH * TH));
        float groove = pow(sinTH, 40.0) * saturate(dot(N, LightDir));
        float3 roomAvg = EnvSpecular.SampleLevel(LinearClamp, mul(N, (float3x3)EnvRot), 4.5).rgb * EnvScale;
        float3 scratch = (LightColour * groove * 0.9 + roomAvg * 0.35) * wear.r;
        float3 dust = (LightColour * saturate(dot(N, LightDir)) * 0.30 + roomAvg * 0.45) * wear.g * float3(0.92, 0.92, 0.88);
        colour += (scratch + dust) * Exposure;
    }
    return float4(colour, behindA);
}
