using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Numerics;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Vortice.Mathematics;

namespace ClockWall.Rendering;

/// <summary>
/// The watch itself: the geometry, the materials, the lights, the camera,
/// and the four passes that turn a <see cref="Reading"/> into a frame.
///
/// THE WORLD. Millimetres. X to the right, Y toward the viewer, Z down the
/// dial toward six o'clock - so the dial lies in the XZ plane at Y=0 and a
/// clockwise turn on the dial is a rotation about -Y. The movement's own
/// frame (Y-up glTF, millimetres, arbors in the XZ plane) drops straight
/// into this with one rigid placement, <see cref="_movementWorld"/>, which
/// is tools/om10_layout.py's similarity transform stated in 3D.
///
/// THE PASSES. Shadow map from the key light; the opaque watch into a 4x
/// MSAA half-float target; the crystal over it additively; then resolve,
/// tone-map and hand the result to the swap chain as premultiplied alpha
/// so the wall shows through around the case.
///
/// NOTHING ALLOCATES PER FRAME. Every buffer, view and state is made once
/// here or on resize; the frame loop writes two constant buffers and issues
/// about forty draws. The wall runs for days.
/// </summary>
internal sealed class WatchScene : IDisposable
{
    // ------------------------------------------------------------ dimensions

    /// <summary>Millimetres per face unit. tools/om10_layout.py places the
    /// movement at 11.78 face units per millimetre; the case, dial and hands
    /// were all drawn in face units, so this is what turns every number in
    /// case_geometry.py into a real size.</summary>
    private const float U = 1f / 11.780018f;

    private const float DialRadius = 288f * U;
    private const float BezelInner = 289f * U;
    private const float CaseRadius = 314f * U;
    private const float TrackRadius = 268f * U;
    private const float IndexInner = 246f * U;
    private const float IndexOuter = 279f * U;
    private const float IndexHalfWidth = 7.5f * U;

    /// <summary>The opening at six, from escapement_geometry.APERTURE.</summary>
    private static readonly Vector3 ApertureCentre = new(0f, 0f, 130f * U);
    private const float ApertureRadius = 126f * U;
    private const float RehautOuter = 133f * U;

    /// <summary>How far the well drops below the dial before the movement.
    /// This is the number that makes the aperture a recess: the wall it
    /// draws, and the depth the shader's occlusion term works against.</summary>
    private const float WellDepth = 3.0f;

    /// <summary>Where the movement's Y=0 plane sits under the dial. The
    /// highest part (a bridge screw head, Z=2.30 in the CAD) lands 1.3mm
    /// below the dial's surface, the balance rim about 3mm.</summary>
    private const float MovementY = -3.6f;

    // Hand and stack heights, millimetres above the dial. Each clears the
    // one below it so they shadow each other; the crystal clears all of them.
    private const float IndexHeight = 0.45f;
    private const float HourBase = 0.75f, HourRidge = 0.19f;
    private const float MinuteBase = 1.15f, MinuteRidge = 0.16f;
    private const float SecondBase = 1.55f, SecondTop = 1.70f;
    private const float CrystalEdge = 2.3f, CrystalPeak = 3.1f;

    // ------------------------------------------------------------ resources

    private readonly ID3D11Device _device;
    private readonly ID3D11DeviceContext _context;
    private readonly Environment _environment;
    private readonly Dictionary<string, Mesh> _movement;

    private readonly Mesh _dial, _rehaut, _bezel, _indices, _hourHand, _minuteHand, _secondHand, _cap, _crystal, _floor;

    private readonly ID3D11VertexShader _vsWatch, _vsShadow, _vsCrystal, _vsPost;
    private readonly ID3D11PixelShader _psWatch, _psShadow, _psCrystal, _psPost;
    private readonly ID3D11InputLayout _layout;
    private readonly ID3D11Buffer _frameCb, _objectCb, _postCb;
    private readonly ID3D11SamplerState _linearClamp, _shadowCmp, _point;
    private readonly ID3D11RasterizerState _rasterMain, _rasterShadow;
    private readonly ID3D11DepthStencilState _depthOn, _depthReadOnly, _depthOff;
    private readonly ID3D11BlendState _blendOpaque, _blendCrystal;

    private const int ShadowSize = 2048;
    private readonly ID3D11Texture2D _shadowTex;
    private readonly ID3D11DepthStencilView _shadowDsv;
    private readonly ID3D11ShaderResourceView _shadowSrv;
    private readonly ID3D11ShaderResourceView _dialPrint;

    private int _width, _height;
    private ID3D11Texture2D? _colourMsaa, _depthMsaa, _resolved;
    private ID3D11RenderTargetView? _colourRtv;
    private ID3D11DepthStencilView? _depthDsv;
    private ID3D11ShaderResourceView? _resolvedSrv;

    private readonly Matrix4x4 _movementWorld;
    private readonly Caliber _caliber = Caliber.Swiss4Hz;

    /// <summary>Set CLOCKWALL_DEBUG_VIEW=1 in the environment to render every
    /// surface as a mirror of the studio by its normal. See watch.hlsl.</summary>
    private readonly float _debugView =
        System.Environment.GetEnvironmentVariable("CLOCKWALL_DEBUG_VIEW") == "1" ? 1f : 0f;

    // ------------------------------------------------------------ materials

    private static readonly Material Dial = new(Material.DialBlue, 1f, 0.30f, 0.62f, Finish.Dial, Lacquer: 0.30f);
    private static readonly Material Polished = new(Material.Steel, 1f, 0.07f, 0.07f);
    private static readonly Material BezelSteel = new(Material.Steel, 1f, 0.06f, 0.14f, Finish.Circular, FinishCentre: Vector3.Zero);
    private static readonly Material RehautSteel = new(Material.Steel, 1f, 0.06f, 0.12f, Finish.Circular, FinishCentre: ApertureCentre);
    private static readonly Material BluedHand = new(Material.Blued, 1f, 0.10f, 0.10f);
    private static readonly Material Floor = new(new Vector3(0.25f, 0.26f, 0.28f), 1f, 0.55f, 0.55f, Recess: true);

    /// <summary>What each OM10 part is made of and how it was finished. The
    /// two-tier rule from render_lib, kept: almost everything quiet, a few
    /// things bright, and the escapement the dimmest metal in the window.</summary>
    private static readonly Dictionary<string, Material> MovementMaterials = new()
    {
        ["mainplate"] = new(Material.Plate, 1f, 0.34f, 0.42f, Finish.Perlage, FinishScale: 1.0f, Recess: true),
        ["bridge"] = new(Material.Plate, 1f, 0.14f, 0.34f, Finish.Straight, FinishScale: 1.35f, FinishDir: Vector3.UnitX, Recess: true),
        ["cock"] = new(Material.Plate, 1f, 0.14f, 0.34f, Finish.Straight, FinishScale: 1.35f, FinishDir: Vector3.UnitX, Recess: true),
        ["wheel_a"] = new(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true),
        ["wheel_b"] = new(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true),
        ["wheel_c"] = new(Material.Brass, 1f, 0.16f, 0.38f, Finish.Circular, Recess: true),
        ["balance"] = new(Material.Brass, 1f, 0.16f, 0.36f, Finish.Circular, Recess: true),
        ["collet"] = new(Material.Brass, 1f, 0.22f, 0.22f, Recess: true),
        ["pinion_a"] = new(Material.Steel, 1f, 0.16f, 0.16f, Recess: true),
        ["pinion_b"] = new(Material.Steel, 1f, 0.16f, 0.16f, Recess: true),
        ["epinion"] = new(Material.Steel, 1f, 0.16f, 0.16f, Recess: true),
        ["escape"] = new(Material.Steel, 1f, 0.36f, 0.36f, Recess: true),
        ["lever"] = new(new Vector3(0.55f, 0.56f, 0.58f), 1f, 0.04f, 0.04f, Finish.BlackPolish, Recess: true),
        ["guard"] = new(Material.Steel, 1f, 0.14f, 0.14f, Recess: true),
        ["staff"] = new(Material.Steel, 1f, 0.10f, 0.10f, Recess: true),
        ["roller"] = new(Material.Steel, 1f, 0.14f, 0.14f, Recess: true),
        ["hairspring"] = new(Material.Blued, 1f, 0.22f, 0.22f, Recess: true),
        ["jewel"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
        ["stone_a"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
        ["stone_b"] = new(Material.Ruby, 0f, 0.05f, 0.05f, Recess: true),
        ["screw_a"] = new(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
        ["screw_b"] = new(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
        ["screw_c"] = new(Material.Blued, 1f, 0.11f, 0.11f, Recess: true),
    };

    /// <summary>The rotation map from HANDOVER-REALTIME.md: which arbor each
    /// part turns about, in the movement's own XZ (CAD x, -y). Parts not
    /// listed are static. The lever's passengers - the two stones and the
    /// guard pin - turn about the LEVER's arbor, not their own centres, which
    /// is the trap the handover names.</summary>
    private static readonly (string Part, Vector2 Arbor, Drive Drive)[] Rotations =
    {
        ("staff", new(-8.06f, -3.51f), Drive.Balance),
        ("roller", new(-8.06f, -3.51f), Drive.Balance),
        ("balance", new(-8.06f, -3.51f), Drive.Balance),
        ("collet", new(-8.06f, -3.51f), Drive.Balance),
        ("hairspring", new(-8.06f, -3.51f), Drive.Hairspring),
        ("escape", new(-3.68f, -7.90f), Drive.Escape),
        ("epinion", new(-3.68f, -7.90f), Drive.Escape),
        ("lever", new(-5.87f, -5.71f), Drive.Fork),
        ("stone_a", new(-5.87f, -5.71f), Drive.Fork),
        ("stone_b", new(-5.87f, -5.71f), Drive.Fork),
        ("guard", new(-5.87f, -5.71f), Drive.Fork),
        ("wheel_c", new(0f, -8f), Drive.Fourth),
        ("pinion_b", new(0f, -8f), Drive.Fourth),
        ("wheel_b", new(4.453f, -8.124f), Drive.Third),
        ("wheel_a", new(7.028f, -4.223f), Drive.Centre),
        ("pinion_a", new(1.526f, -4.127f), Drive.CentrePinion),
    };

    private enum Drive { Balance, Hairspring, Escape, Fork, Fourth, Third, Centre, CentrePinion }

    /// <summary>How far the pallet lever banks either side of centre, in
    /// degrees, for a full swing of the fork. Real, not exaggerated: the
    /// impulse pin sits at the roller's 0.82mm radius and the fork slot 3.1mm
    /// from the pallet arbor, so a 52 degree lift angle at the balance is
    /// 0.82/3.1 x 52 = 13.7 degrees at the lever, 6.9 each way. It is also,
    /// not by accident, the number the sprite face arrived at.</summary>
    private const float ForkBankDegrees = 6.9f;

    /// <summary>Of the balance's swing, how much the hairspring takes as a
    /// rigid turn. Carried over from OpenworkedFace with its reasoning: the
    /// outer coil is pinned to the stud and cannot move, so a rigid turn is a
    /// stand-in at best and this is the largest one that still reads as the
    /// coil breathing rather than sliding out from under its anchor.</summary>
    private const float SpringTravel = 0.05f;

    // ------------------------------------------------------------ construction

    public WatchScene(ID3D11Device device, ID3D11DeviceContext context, string assetDirectory)
    {
        _device = device;
        _context = context;
        var sw = Stopwatch.StartNew();

        _environment = new Environment(device, context, Path.Combine(assetDirectory, "studio.hdr"));
        _movement = GltfLoader.Load(device, Path.Combine(assetDirectory, "movement.glb"));
        _dialPrint = Gpu.LoadMask(device, Path.Combine(assetDirectory, "dial-print.png"));

        // ---- shaders
        using (var vs = Gpu.Compile("watch.hlsl", "VsMain", "vs_5_0"))
        {
            _vsWatch = device.CreateVertexShader(vs.AsBytes());
            _layout = device.CreateInputLayout(Gpu.VertexLayout, vs);
        }
        using (var ps = Gpu.Compile("watch.hlsl", "PsMain", "ps_5_0")) _psWatch = device.CreatePixelShader(ps.AsBytes());
        using (var vs = Gpu.Compile("shadow.hlsl", "VsMain", "vs_5_0")) _vsShadow = device.CreateVertexShader(vs.AsBytes());
        using (var ps = Gpu.Compile("shadow.hlsl", "PsMain", "ps_5_0")) _psShadow = device.CreatePixelShader(ps.AsBytes());
        using (var vs = Gpu.Compile("crystal.hlsl", "VsMain", "vs_5_0")) _vsCrystal = device.CreateVertexShader(vs.AsBytes());
        using (var ps = Gpu.Compile("crystal.hlsl", "PsMain", "ps_5_0")) _psCrystal = device.CreatePixelShader(ps.AsBytes());
        using (var vs = Gpu.Compile("post.hlsl", "VsFullscreen", "vs_5_0")) _vsPost = device.CreateVertexShader(vs.AsBytes());
        using (var ps = Gpu.Compile("post.hlsl", "PsMain", "ps_5_0")) _psPost = device.CreatePixelShader(ps.AsBytes());

        _frameCb = Gpu.CreateConstantBuffer<FrameConstants>(device);
        _objectCb = Gpu.CreateConstantBuffer<ObjectConstants>(device);
        _postCb = Gpu.CreateConstantBuffer<Vector4>(device);

        // ---- states
        _linearClamp = device.CreateSamplerState(new SamplerDescription(Filter.MinMagMipLinear,
            TextureAddressMode.Clamp, TextureAddressMode.Clamp, TextureAddressMode.Clamp));
        _point = device.CreateSamplerState(new SamplerDescription(Filter.MinMagMipPoint,
            TextureAddressMode.Clamp, TextureAddressMode.Clamp, TextureAddressMode.Clamp));
        _shadowCmp = device.CreateSamplerState(new SamplerDescription
        {
            Filter = Filter.ComparisonMinMagLinearMipPoint,
            AddressU = TextureAddressMode.Border, AddressV = TextureAddressMode.Border, AddressW = TextureAddressMode.Border,
            BorderColor = new Color4(1f, 1f, 1f, 1f),
            ComparisonFunc = ComparisonFunction.LessEqual,
            MaxLOD = float.MaxValue,
        });

        // Cull nothing. The CAD parts are closed solids and would cull fine,
        // but the procedural pieces include single-sided surfaces (the dial,
        // the crystal dome) that the tilted camera can see the back of at the
        // rim, and a missing triangle is a worse defect than a few thousand
        // extra ones on a scene this small.
        _rasterMain = device.CreateRasterizerState(RasterizerDescription.CullNone with { MultisampleEnable = true });
        _rasterShadow = device.CreateRasterizerState(new RasterizerDescription(CullMode.None, FillMode.Solid)
        {
            DepthBias = 200,
            SlopeScaledDepthBias = 1.5f,
            DepthBiasClamp = 0.01f,
        });
        _depthOn = device.CreateDepthStencilState(DepthStencilDescription.Default);
        _depthReadOnly = device.CreateDepthStencilState(DepthStencilDescription.DepthRead);
        _depthOff = device.CreateDepthStencilState(DepthStencilDescription.None);
        _blendOpaque = device.CreateBlendState(BlendDescription.Opaque);
        // The crystal adds light and leaves coverage alone: colour ONE/ONE,
        // alpha ZERO/ONE.
        _blendCrystal = device.CreateBlendState(new BlendDescription(Blend.One, Blend.One, Blend.Zero, Blend.One));

        // ---- shadow map
        _shadowTex = device.CreateTexture2D(new Texture2DDescription
        {
            Width = ShadowSize, Height = ShadowSize, MipLevels = 1, ArraySize = 1,
            Format = Format.R32_Typeless, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Default, BindFlags = BindFlags.DepthStencil | BindFlags.ShaderResource,
        });
        _shadowDsv = device.CreateDepthStencilView(_shadowTex, new DepthStencilViewDescription(_shadowTex, DepthStencilViewDimension.Texture2D, Format.D32_Float));
        _shadowSrv = device.CreateShaderResourceView(_shadowTex, new ShaderResourceViewDescription(_shadowTex, ShaderResourceViewDimension.Texture2D, Format.R32_Float));

        // ---- geometry
        _dial = BuildDial();
        _rehaut = BuildRehaut();
        _bezel = BuildCase();
        _indices = BuildIndices();
        _hourHand = BuildDauphine(150f * U, 11f * U, 44f * U, 34f * U, HourBase, HourRidge);
        _minuteHand = BuildDauphine(214f * U, 9f * U, 54f * U, 40f * U, MinuteBase, MinuteRidge);
        _secondHand = BuildSecondHand();
        _cap = BuildCap();
        _crystal = BuildCrystal();
        _floor = BuildFloor();

        _movementWorld = MovementPlacement();

        Debug.WriteLine($"[ClockWall] watch scene ready in {sw.ElapsedMilliseconds} ms");
    }

    /// <summary>
    /// tools/om10_layout.py's placement, in 3D. The movement is exported
    /// Y-up with its arbors at their real millimetre positions; the face
    /// puts the balance at (296.2, 464.2) face units and turns the whole
    /// assembly 6.6 degrees clockwise so the escapement runs on the bearing
    /// the composition wants. Stated as: shift the balance arbor to the
    /// origin, turn, then move the origin to where the balance goes.
    /// </summary>
    private static Matrix4x4 MovementPlacement()
    {
        const float rotDeg = 6.595f;                          // om10_layout ROT_DEG
        var balanceFace = new Vector2(296.2238f, 464.2443f);  // escapement_geometry.BALANCE
        var balanceWorld = new Vector3((balanceFace.X - 320f) * U, MovementY, (balanceFace.Y - 320f) * U);

        return Matrix4x4.CreateTranslation(8.06f, 0f, 3.51f)  // balance arbor (-8.06, 3.51 CAD) -> origin
             * ScreenClockwise(rotDeg)
             * Matrix4x4.CreateTranslation(balanceWorld);
    }

    /// <summary>A turn that is clockwise as seen on the dial. Y points at the
    /// viewer, so that is a NEGATIVE rotation about Y - the sign every
    /// Reading angle needs before it can drive a transform.</summary>
    private static Matrix4x4 ScreenClockwise(float degrees) =>
        Matrix4x4.CreateRotationY(-degrees * MathF.PI / 180f);

    // ------------------------------------------------------------ geometry

    private Mesh BuildDial()
    {
        // One fan; the aperture and the outer rim are cut in the shader.
        var b = new MeshBuilder();
        const int segments = 256;
        var r = BezelInner + 0.6f;   // tucks under the bezel
        var centre = Vector3.Zero;
        for (var s = 0; s < segments; s++)
        {
            var a0 = MathF.Tau * s / segments;
            var a1 = MathF.Tau * (s + 1) / segments;
            b.Triangle(centre,
                new Vector3(r * MathF.Cos(a1), 0f, r * MathF.Sin(a1)),
                new Vector3(r * MathF.Cos(a0), 0f, r * MathF.Sin(a0)));
        }
        return b.Build(_device);
    }

    /// <summary>The polished ring standing in the opening: a fine bright
    /// chamfer on top, and the wall of the well going down inside it.</summary>
    private Mesh BuildRehaut()
    {
        var p = new List<MeshBuilder.ProfilePoint>();
        var ri = ApertureRadius;
        var ro = RehautOuter;
        MeshBuilder.Line(p, new Vector2(ro, -0.2f), new Vector2(ro, 0.22f));           // outer wall
        MeshBuilder.Line(p, new Vector2(ro, 0.22f), new Vector2(ro - 0.14f, 0.36f));   // outer chamfer
        MeshBuilder.Line(p, new Vector2(ro - 0.14f, 0.36f), new Vector2(ri + 0.16f, 0.36f)); // flat top
        MeshBuilder.Line(p, new Vector2(ri + 0.16f, 0.36f), new Vector2(ri, 0.20f));   // inner chamfer, the bright line
        MeshBuilder.Line(p, new Vector2(ri, 0.20f), new Vector2(ri, -WellDepth));     // the well
        MeshBuilder.Line(p, new Vector2(ri, -WellDepth), new Vector2(ri + 3f, -WellDepth)); // a ledge, so the well has a floor at the rim
        var b = new MeshBuilder();
        b.Lathe(p, 192, ApertureCentre.X, ApertureCentre.Z);
        return b.Build(_device);
    }

    /// <summary>Case and bezel as one lathe: the rehaut wall between dial and
    /// crystal, a fine inner chamfer, a broad softly domed bezel top, a
    /// rounded outer edge and the case band below it.</summary>
    private Mesh BuildCase()
    {
        var p = new List<MeshBuilder.ProfilePoint>();
        var ri = BezelInner;
        var ro = CaseRadius;
        // Walk from the dial outward and up: the flange the dial sits on,
        // the rehaut wall, then the bezel, then down the outside.
        MeshBuilder.Line(p, new Vector2(ri - 0.8f, -0.05f), new Vector2(ri, -0.05f));   // flange under the dial edge
        MeshBuilder.Line(p, new Vector2(ri, -0.05f), new Vector2(ri, CrystalEdge));     // rehaut wall
        MeshBuilder.Line(p, new Vector2(ri, CrystalEdge), new Vector2(ri + 0.35f, CrystalEdge)); // crystal seat
        MeshBuilder.Line(p, new Vector2(ri + 0.35f, CrystalEdge), new Vector2(ri + 0.9f, CrystalEdge + 0.55f)); // inner chamfer
        // The domed top: a gentle arc from the chamfer out to the shoulder.
        var domeR = 22f;
        var x0 = ri + 0.9f; var x1 = ro - 0.55f;
        var yTop = CrystalEdge + 0.62f;
        var domeCentre = new Vector2((x0 + x1) * 0.5f, yTop - domeR);
        var a0 = MathF.Atan2(yTop - 0.02f - domeCentre.Y, x0 - domeCentre.X) * 180f / MathF.PI;
        var a1 = MathF.Atan2(yTop - 0.02f - domeCentre.Y, x1 - domeCentre.X) * 180f / MathF.PI;
        MeshBuilder.Arc(p, domeCentre, domeR, a0, a1, 12);
        // Rounded outer edge, then the case band.
        var edgeR = 0.55f;
        MeshBuilder.Arc(p, new Vector2(ro - edgeR, yTop - 0.02f - edgeR), edgeR, 90f, 0f, 10);
        MeshBuilder.Line(p, new Vector2(ro, yTop - 0.02f - edgeR), new Vector2(ro, -6.5f));
        MeshBuilder.Line(p, new Vector2(ro, -6.5f), new Vector2(ro - 1.5f, -8f));
        var b = new MeshBuilder();
        b.Lathe(p, 384);
        return b.Build(_device);
    }

    /// <summary>Eleven batons, doubled at twelve, none at six. Applied: each
    /// stands proud of the dial with a chamfer all round, so it catches its
    /// own line of light and throws its own shadow.</summary>
    private Mesh BuildIndices()
    {
        var b = new MeshBuilder();
        for (var hour = 1; hour <= 12; hour++)
        {
            if (hour == 6) continue;
            var deg = hour * 30f;
            if (hour == 12)
            {
                Baton(b, deg, 4.4f * U, -6.2f * U);
                Baton(b, deg, 4.4f * U, 6.2f * U);
            }
            else
            {
                Baton(b, deg, IndexHalfWidth, 0f);
            }
        }
        return b.Build(_device);
    }

    private static void Baton(MeshBuilder b, float deg, float halfW, float offset)
    {
        var a = deg * MathF.PI / 180f;
        // Along the radius (toward the rim) and across it, clockwise on the dial.
        var u = new Vector2(MathF.Sin(a), -MathF.Cos(a));
        var v = new Vector2(u.Y, -u.X);
        Vector2 At(float r, float w) => u * r + v * (w + offset);
        // Clockwise as seen from above: inner-left, outer-left, outer-right, inner-right.
        var outline = new[] { At(IndexInner, -halfW), At(IndexOuter, -halfW), At(IndexOuter, halfW), At(IndexInner, halfW) };
        b.ChamferedPrism(outline, 0f, IndexHeight, 0.12f);
    }

    private Mesh BuildDauphine(float length, float halfW, float shoulder, float tail, float y0, float ridge)
    {
        var b = new MeshBuilder();
        b.Dauphine(length, halfW, shoulder, tail, y0, ridge);
        return b.Build(_device);
    }

    /// <summary>A needle with a pierced counterweight, in blued steel.</summary>
    private Mesh BuildSecondHand()
    {
        var b = new MeshBuilder();
        var w = 2f * U;
        var tip = -232f * U;
        var tailEnd = 40f * U;
        // Clockwise from above: tip-left, tip-right, tail-right, tail-left.
        var outline = new[]
        {
            new Vector2(-w, tip), new Vector2(w, tip),
            new Vector2(w * 1.5f, tailEnd), new Vector2(-w * 1.5f, tailEnd),
        };
        b.ChamferedPrism(outline, SecondBase, SecondTop, 0.04f);

        var p = new List<MeshBuilder.ProfilePoint>();
        var ringR = 13f * U; var holeR = 5.4f * U;
        MeshBuilder.Line(p, new Vector2(ringR, SecondBase), new Vector2(ringR, SecondTop));
        MeshBuilder.Line(p, new Vector2(ringR, SecondTop), new Vector2(holeR, SecondTop));
        MeshBuilder.Line(p, new Vector2(holeR, SecondTop), new Vector2(holeR, SecondBase));
        b.Lathe(p, 64, 0f, 54f * U);
        return b.Build(_device);
    }

    /// <summary>The boss over the hand pivots, a low polished dome.</summary>
    private Mesh BuildCap()
    {
        var p = new List<MeshBuilder.ProfilePoint>();
        var r = 13f * U;
        var top = SecondTop + 0.25f;
        MeshBuilder.Line(p, new Vector2(r, 0.4f), new Vector2(r, top - 0.5f));
        MeshBuilder.Arc(p, new Vector2(0f, top - r), r, MathF.Asin((top - 0.5f - (top - r)) / r) * 180f / MathF.PI, 90f, 12);
        var b = new MeshBuilder();
        b.Lathe(p, 96);
        return b.Build(_device);
    }

    /// <summary>A shallow spherical dome from the rehaut seat to a peak over
    /// the centre. Slight on purpose: at this height the crystal reads as
    /// a sheet of light, not a bubble.</summary>
    private Mesh BuildCrystal()
    {
        var p = new List<MeshBuilder.ProfilePoint>();
        var chord = BezelInner;
        var sag = CrystalPeak - CrystalEdge;
        var sphereR = (chord * chord + sag * sag) / (2f * sag);
        var centre = new Vector2(0f, CrystalPeak - sphereR);
        var edgeAngle = MathF.Asin(chord / sphereR) * 180f / MathF.PI;
        MeshBuilder.Arc(p, centre, sphereR, 90f - edgeAngle, 90f, 32);
        var b = new MeshBuilder();
        b.Lathe(p, 256);
        return b.Build(_device);
    }

    /// <summary>The floor of the case under the movement, so the well never
    /// looks out onto nothing where the mainplate's edge falls inside the
    /// opening.</summary>
    private Mesh BuildFloor()
    {
        var b = new MeshBuilder();
        var r = CaseRadius - 0.5f;
        var y = MovementY - 4.6f;
        const int segments = 128;
        for (var s = 0; s < segments; s++)
        {
            var a0 = MathF.Tau * s / segments;
            var a1 = MathF.Tau * (s + 1) / segments;
            b.Triangle(new Vector3(0f, y, 0f),
                new Vector3(r * MathF.Cos(a1), y, r * MathF.Sin(a1)),
                new Vector3(r * MathF.Cos(a0), y, r * MathF.Sin(a0)));
        }
        return b.Build(_device);
    }

    // ------------------------------------------------------------ targets

    public void EnsureTargets(int width, int height)
    {
        if (width == _width && height == _height && _colourRtv is not null) return;
        ReleaseTargets();
        _width = width; _height = height;

        _colourMsaa = _device.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.R16G16B16A16_Float, SampleDescription = new SampleDescription(4, 0),
            Usage = ResourceUsage.Default, BindFlags = BindFlags.RenderTarget,
        });
        _colourRtv = _device.CreateRenderTargetView(_colourMsaa);
        _depthMsaa = _device.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.D32_Float, SampleDescription = new SampleDescription(4, 0),
            Usage = ResourceUsage.Default, BindFlags = BindFlags.DepthStencil,
        });
        _depthDsv = _device.CreateDepthStencilView(_depthMsaa);
        _resolved = _device.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.R16G16B16A16_Float, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Default, BindFlags = BindFlags.ShaderResource | BindFlags.RenderTarget,
        });
        _resolvedSrv = _device.CreateShaderResourceView(_resolved);
    }

    private void ReleaseTargets()
    {
        _resolvedSrv?.Dispose(); _resolvedSrv = null;
        _resolved?.Dispose(); _resolved = null;
        _depthDsv?.Dispose(); _depthDsv = null;
        _depthMsaa?.Dispose(); _depthMsaa = null;
        _colourRtv?.Dispose(); _colourRtv = null;
        _colourMsaa?.Dispose(); _colourMsaa = null;
        _width = _height = 0;
    }

    // ------------------------------------------------------------ frame

    /// <summary>The camera and light for one instant. Both drift slowly, and
    /// that drift is the point of the whole pipeline: the sunburst's lobes
    /// and the hands' facets only read as metal when the light moves.</summary>
    private readonly struct Rig
    {
        public readonly Matrix4x4 View, Proj, LightViewProj, EnvRot;
        public readonly Vector3 Eye, LightDir;

        public Rig(double seconds)
        {
            var t = (float)seconds;

            // ---- camera: a long lens from 300mm, tilted a few degrees so
            // the case has a side, breathing by a degree or two.
            var tilt = (4.0f + 1.5f * MathF.Sin(t / 41f)) * MathF.PI / 180f;
            var swing = (1.2f * MathF.Sin(t / 53f)) * MathF.PI / 180f;
            const float distance = 300f;
            Eye = new Vector3(distance * MathF.Sin(swing), distance * MathF.Cos(tilt), distance * MathF.Sin(tilt));
            View = Matrix4x4.CreateLookAt(Eye, Vector3.Zero, -Vector3.UnitZ);
            // 54.3mm of dial fills the 640-unit panel at this distance.
            var fov = 2f * MathF.Atan(320f * U / distance);
            Proj = Matrix4x4.CreatePerspectiveFieldOfView(fov, 1f, 200f, 420f);

            // ---- key light: from the upper left like the old face's key
            // (dial_render LIGHT_DEG = 315), high, and wandering over a
            // couple of minutes so the lobes sweep.
            var bearing = (315f + 22f * MathF.Sin(t / 29f)) * MathF.PI / 180f;
            var elevation = (52f + 9f * MathF.Sin(t / 37f)) * MathF.PI / 180f;
            LightDir = Vector3.Normalize(new Vector3(
                MathF.Sin(bearing) * MathF.Cos(elevation),
                MathF.Sin(elevation),
                -MathF.Cos(bearing) * MathF.Cos(elevation)));
            var lightView = Matrix4x4.CreateLookAt(LightDir * 100f, Vector3.Zero, -Vector3.UnitZ);
            var lightProj = Matrix4x4.CreateOrthographic(62f, 62f, 20f, 200f);
            LightViewProj = lightView * lightProj;

            // ---- environment: the studio panorama turned so its horizon -
            // where the softboxes are - lies behind the camera, which is
            // what a flat metal facing the viewer reflects. Yawed slowly.
            // studio_small_09, measured off the panorama in radiance: two small
            // strobes at azimuth -149 and -30; two gridded octagonal softboxes,
            // the big one centred at azimuth +36 and 25 degrees up at radiance
            // 28; and a white cyclorama filling -135 to -45 that LOOKS bright
            // in a tone-mapped preview and is radiance 1 - it is lit, not a
            // light. Flat polished steel facing the viewer reflects world +Y,
            // and only the softbox will make it read as silver, so that is
            // where +Y is aimed. (The wall was tried and gave gunmetal.) Its
            // eggcrate grid is dealt with in the shader, by smearing the
            // reflection along the anisotropic lobe.
            // Rx pitches world +Y up to the box's elevation; Ry (negative,
            // because the panorama's longitude runs the other way from a
            // rotation about Y) swings it round to the box's azimuth, and
            // wanders so the reflection crosses the dial.
            var yaw = -0.63f + 0.22f * MathF.Sin(t / 67f);
            EnvRot = Matrix4x4.CreateRotationX(-65f * MathF.PI / 180f) * Matrix4x4.CreateRotationY(yaw);
        }
    }

    /// <summary>The colour behind the panel, sRGB as the theme gives it.
    /// See post.hlsl for why this is a constant and not alpha.</summary>
    public Vector3 Backdrop { get; set; } = new(0.05f, 0.05f, 0.07f);

    public void Render(ID3D11RenderTargetView backBuffer, int width, int height, DateTime now, double seconds)
    {
        EnsureTargets(width, height);
        var ctx = _context;
        var rig = new Rig(seconds);
        var reading = _caliber.Read(now);

        // ---- frame constants
        var frame = new FrameConstants
        {
            ViewProj = rig.View * rig.Proj,
            LightViewProj = rig.LightViewProj,
            EnvRot = rig.EnvRot,
            CameraPos = rig.Eye,
            Exposure = 1.0f,
            LightDir = rig.LightDir,
            ShadowTexel = 1f / ShadowSize,
            LightColour = new Vector3(2.0f, 1.97f, 1.9f),
            Time = (float)seconds,
            ApertureCentre = ApertureCentre,
            ApertureRadius = ApertureRadius,
            DialRadius = DialRadius,
            TrackRadius = TrackRadius,
            DebugView = _debugView,
        };
        ctx.UpdateSubresource(frame, _frameCb);

        ctx.IASetInputLayout(_layout);
        ctx.IASetPrimitiveTopology(PrimitiveTopology.TriangleList);
        ctx.VSSetConstantBuffer(0, _frameCb);
        ctx.VSSetConstantBuffer(1, _objectCb);
        ctx.PSSetConstantBuffer(0, _frameCb);
        ctx.PSSetConstantBuffer(1, _objectCb);

        // ---- 1. shadow map
        ctx.OMSetRenderTargets((ID3D11RenderTargetView?)null, _shadowDsv);
        ctx.ClearDepthStencilView(_shadowDsv, DepthStencilClearFlags.Depth, 1f, 0);
        ctx.RSSetViewport(0, 0, ShadowSize, ShadowSize);
        ctx.RSSetState(_rasterShadow);
        ctx.OMSetDepthStencilState(_depthOn);
        ctx.OMSetBlendState(_blendOpaque);
        ctx.VSSetShader(_vsShadow);
        ctx.PSSetShader(_psShadow);
        DrawOpaque(reading);

        // ---- 2. the watch
        ctx.OMSetRenderTargets(_colourRtv!, _depthDsv);
        ctx.ClearRenderTargetView(_colourRtv!, new Color4(0f, 0f, 0f, 0f));
        ctx.ClearDepthStencilView(_depthDsv!, DepthStencilClearFlags.Depth, 1f, 0);
        ctx.RSSetViewport(0, 0, width, height);
        ctx.RSSetState(_rasterMain);
        ctx.VSSetShader(_vsWatch);
        ctx.PSSetShader(_psWatch);
        ctx.PSSetShaderResource(0, _environment.Specular);
        ctx.PSSetShaderResource(1, _environment.Diffuse);
        ctx.PSSetShaderResource(2, _environment.BrdfLut);
        ctx.PSSetShaderResource(3, _shadowSrv);
        ctx.PSSetShaderResource(4, _dialPrint);
        ctx.PSSetSampler(0, _linearClamp);
        ctx.PSSetSampler(1, _shadowCmp);
        DrawOpaque(reading);

        // ---- 3. the crystal
        ctx.OMSetDepthStencilState(_depthReadOnly);
        ctx.OMSetBlendState(_blendCrystal);
        ctx.VSSetShader(_vsCrystal);
        ctx.PSSetShader(_psCrystal);
        Draw(_crystal, Polished, Matrix4x4.Identity);

        // ---- 4. resolve and present
        ctx.PSSetShaderResource(3, null);
        ctx.OMSetRenderTargets((ID3D11RenderTargetView?)null);
        ctx.ResolveSubresource(_resolved!, 0, _colourMsaa!, 0, Format.R16G16B16A16_Float);
        ctx.OMSetRenderTargets(backBuffer);
        ctx.OMSetDepthStencilState(_depthOff);
        ctx.OMSetBlendState(_blendOpaque);
        ctx.IASetInputLayout(null);
        ctx.VSSetShader(_vsPost);
        ctx.PSSetShader(_psPost);
        ctx.UpdateSubresource(new Vector4(Backdrop, 1f), _postCb);
        ctx.PSSetConstantBuffer(0, _postCb);
        ctx.PSSetShaderResource(0, _resolvedSrv);
        ctx.PSSetSampler(0, _point);
        ctx.Draw(3, 0);
        ctx.PSSetShaderResource(0, null);
    }

    /// <summary>Every opaque surface, in an order that is only about
    /// overdraw. Called twice a frame: once into the shadow map, once into
    /// the colour target.</summary>
    private void DrawOpaque(Reading reading)
    {
        Draw(_floor, Floor, Matrix4x4.Identity);

        // The movement, part by part, each turned about its arbor.
        foreach (var (name, mesh) in _movement)
        {
            var material = MovementMaterials.TryGetValue(name, out var m) ? m : Polished with { Recess = true };
            var world = _movementWorld;
            foreach (var (part, arbor, drive) in Rotations)
            {
                if (part != name) continue;
                var degrees = drive switch
                {
                    Drive.Balance => reading.Balance,
                    Drive.Hairspring => reading.Balance * SpringTravel,
                    Drive.Escape => reading.Escape,
                    // Pushed by the impulse pin, which sits between the two
                    // arbors: a point between two centres moves the opposite
                    // way about each, so the lever turns against the balance.
                    Drive.Fork => -reading.Fork * ForkBankDegrees,
                    Drive.Fourth => reading.Train,
                    Drive.Third => -reading.Train * ThirdPerFourth,
                    Drive.Centre => reading.Train * CentrePerFourth,
                    Drive.CentrePinion => -reading.Train * CentrePerFourth * 3.0,
                    _ => 0.0,
                };
                world = Matrix4x4.CreateTranslation(-arbor.X, 0f, -arbor.Y)
                      * ScreenClockwise((float)degrees)
                      * Matrix4x4.CreateTranslation(arbor.X, 0f, arbor.Y)
                      * _movementWorld;
                break;
            }

            // Finish centres are given in the movement's frame for the
            // wheels (their own arbor) and carried into the world here, so
            // circular graining stays concentric with the part as it turns.
            var mat = material;
            if (mat.Finish == Finish.Circular)
            {
                var arbor = ArborOf(name);
                mat = mat with { FinishCentre = Vector3.Transform(new Vector3(arbor.X, 0f, arbor.Y), _movementWorld) };
            }
            else if (mat.Finish == Finish.Straight)
            {
                mat = mat with { FinishDir = Vector3.Normalize(Vector3.TransformNormal(new Vector3(0.94f, 0f, 0.34f), _movementWorld)) };
            }
            Draw(mesh, mat, world);
        }

        // The dial furniture.
        Draw(_dial, Dial, Matrix4x4.Identity);
        Draw(_rehaut, RehautSteel, Matrix4x4.Identity);
        Draw(_bezel, BezelSteel, Matrix4x4.Identity);
        Draw(_indices, Polished, Matrix4x4.Identity);

        // The hands, clockwise from twelve.
        Draw(_hourHand, Polished, ScreenClockwise((float)reading.Hour));
        Draw(_minuteHand, Polished, ScreenClockwise((float)reading.Minute));
        Draw(_secondHand, BluedHand, ScreenClockwise((float)reading.Second));
        Draw(_cap, Polished, Matrix4x4.Identity);
    }

    /// <summary>
    /// Train ratios beyond the fourth wheel, derived from the counts in the
    /// manifest rather than invented - ATTRIBUTION.md exists to record that
    /// distinction. wheel_b (72 teeth) meshes the fourth's pinion_b, counted
    /// at 9 leaves; wheel_a (75 teeth) is the centre wheel and turns once an
    /// hour, which with 60 = (72/9)(75/p3) fixes the third pinion at 10.
    /// Neither turn is perceptible on the wall (a ninth and a sixtieth of
    /// the fourth's rate); the direction of mesh is what has to be right.
    /// </summary>
    private const double ThirdPerFourth = 9.0 / 72.0;
    private const double CentrePerFourth = 1.0 / 60.0;

    private static Vector2 ArborOf(string part)
    {
        foreach (var (p, arbor, _) in Rotations) if (p == part) return arbor;
        return Vector2.Zero;
    }

    private void Draw(Mesh mesh, Material material, Matrix4x4 world)
    {
        _context.UpdateSubresource(material.ToConstants(world), _objectCb);
        mesh.Draw(_context);
    }

    public void Dispose()
    {
        ReleaseTargets();
        foreach (var mesh in _movement.Values) mesh.Dispose();
        foreach (var mesh in new[] { _dial, _rehaut, _bezel, _indices, _hourHand, _minuteHand, _secondHand, _cap, _crystal, _floor }) mesh.Dispose();
        foreach (var d in new IDisposable[]
        {
            _vsWatch, _vsShadow, _vsCrystal, _vsPost, _psWatch, _psShadow, _psCrystal, _psPost, _layout,
            _frameCb, _objectCb, _postCb, _linearClamp, _shadowCmp, _point, _rasterMain, _rasterShadow,
            _depthOn, _depthReadOnly, _depthOff, _blendOpaque, _blendCrystal,
            _shadowSrv, _shadowDsv, _shadowTex, _dialPrint, _environment,
        }) d.Dispose();
    }
}
