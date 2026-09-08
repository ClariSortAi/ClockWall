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
/// The engine: given a <see cref="WatchDesign"/>, loads its geometry and
/// runs the four passes that turn a <see cref="Reading"/> into a frame.
/// It contains no number that belongs to a particular face - those are the
/// design's, and the shapes are the CAD's - only the mechanism: which arbor
/// each part turns about, what order the passes run in.
///
/// THE GEOMETRY. Two GLBs, both from tools/: movement.glb is the OM10, 23
/// named parts; case.glb is everything else, 11 named solids from
/// case_solids.py. Nothing is built here any more. A shape that is wrong is
/// fixed in CAD, where it can be measured, and exported again.
///
/// THE WORLD. Millimetres. X to the right, Y toward the viewer, Z down the
/// dial toward six o'clock - so the dial lies in the XZ plane at Y=0 and a
/// clockwise turn on the dial is a rotation about -Y. The movement's own
/// frame (Y-up glTF, millimetres, arbors in the XZ plane) drops into this
/// with one rigid placement, <see cref="_movementWorld"/>: the centre wheel's
/// arbor to the dial centre, the assembly turned so the balance sits at six.
/// The hands turn about that same arbor, and the seconds hand about the
/// fourth wheel's, DERIVED through the placement so a hand can never sit
/// where there is no axle.
///
/// THE PASSES. Shadow map from the key light; the opaque watch into a 4x
/// MSAA half-float target; the crystal over it additively; then resolve,
/// tone-map and composite over the wall colour into the swap chain.
///
/// NOTHING ALLOCATES PER FRAME. Every buffer, view and state is made once
/// here or on resize; the frame loop writes three constant buffers and
/// issues about forty draws. The wall runs for days.
/// </summary>
internal sealed class WatchScene : IDisposable
{
    private readonly WatchDesign _design;

    // ------------------------------------------------------------ resources

    private readonly ID3D11Device _device;
    private readonly ID3D11DeviceContext _context;
    private readonly Environment _environment;
    private readonly Dictionary<string, Mesh> _movement;
    private readonly Dictionary<string, Mesh> _case;

    private readonly ID3D11VertexShader _vsWatch, _vsShadow, _vsCrystal, _vsPost;
    private readonly ID3D11PixelShader _psWatch, _psShadow, _psCrystal, _psPost;
    private readonly ID3D11InputLayout _layout;
    private readonly ID3D11Buffer _frameCb, _objectCb, _postCb;
    private readonly ID3D11SamplerState _linearClamp, _shadowCmp, _point;
    private readonly ID3D11RasterizerState _rasterMain, _rasterShadow, _rasterCrystal;
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
    private readonly Vector3 _secondsArbor;
    private readonly Caliber _caliber = Caliber.Swiss4Hz;

    /// <summary>Set CLOCKWALL_DEBUG_VIEW=1 in the environment to render every
    /// surface as a mirror of the studio by its normal. See watch.hlsl.</summary>
    private readonly float _debugView =
        System.Environment.GetEnvironmentVariable("CLOCKWALL_DEBUG_VIEW") == "1" ? 1f : 0f;

    // ------------------------------------------------------------ the mechanism

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
    /// 0.82/3.1 x 52 = 13.7 degrees at the lever, 6.9 each way.</summary>
    private const float ForkBankDegrees = 6.9f;

    /// <summary>Of the balance's swing, how much the hairspring takes as a
    /// rigid turn. The outer coil is pinned to the stud and cannot move, so
    /// a rigid turn is a stand-in, and this is the largest one that still
    /// reads as the coil breathing rather than sliding under its anchor.</summary>
    private const float SpringTravel = 0.05f;

    /// <summary>
    /// Train ratios beyond the fourth wheel, derived from the counts in the
    /// manifest rather than invented - ATTRIBUTION.md exists to record that
    /// distinction. wheel_b (72 teeth) meshes the fourth's pinion_b, counted
    /// at 9 leaves; wheel_a (75 teeth) is the centre wheel and turns once an
    /// hour, which with 60 = (72/9)(75/p3) fixes the third pinion at 10.
    /// The minute hand rides that arbor, so it and the centre wheel agree.
    /// </summary>
    private const double ThirdPerFourth = 9.0 / 72.0;
    private const double CentrePerFourth = 1.0 / 60.0;

    // ------------------------------------------------------------ construction

    public WatchScene(ID3D11Device device, ID3D11DeviceContext context, string assetDirectory, WatchDesign design)
    {
        _device = device;
        _context = context;
        _design = design;
        var sw = Stopwatch.StartNew();

        _environment = new Environment(device, context, Path.Combine(assetDirectory, "studio.hdr"));
        _movement = GltfLoader.Load(device, Path.Combine(assetDirectory, "movement.glb"));
        _case = GltfLoader.Load(device, Path.Combine(assetDirectory, "case.glb"));
        _dialPrint = Gpu.LoadMask(device, Path.Combine(assetDirectory, "dial-print.png"));

        foreach (var required in new[] { "case", "dial", "rehaut", "indices", "hour_hand", "minute_hand", "seconds_hand", "cap", "crystal" })
        {
            if (!_case.ContainsKey(required))
                throw new InvalidDataException($"case.glb has no part named '{required}'; re-run tools/case_solids.py");
        }

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

        // Opaque passes cull nothing: every part is a closed solid now and
        // would cull fine, but a thin hand seen edge-on under 4x MSAA is
        // better with both sides drawn than with a missing sliver. The
        // crystal is the exception - it is drawn additively, so its
        // underside must NOT add a second reflection - and it culls its
        // back faces, counter-clockwise front as glTF and OCCT wind them.
        _rasterMain = device.CreateRasterizerState(RasterizerDescription.CullNone with { MultisampleEnable = true });
        _rasterCrystal = device.CreateRasterizerState(new RasterizerDescription(CullMode.Back, FillMode.Solid)
        {
            FrontCounterClockwise = true,
            MultisampleEnable = true,
        });
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

        // ---- placement
        _movementWorld = MovementPlacement(design);
        var seconds = Vector3.Transform(new Vector3(design.SecondsArborCad.X, 0f, -design.SecondsArborCad.Y), _movementWorld);
        _secondsArbor = new Vector3(seconds.X, 0f, seconds.Z);
        Debug.WriteLine($"[ClockWall] watch scene '{design.Name}' ready in {sw.ElapsedMilliseconds} ms; seconds arbor at ({_secondsArbor.X:0.00}, {_secondsArbor.Z:0.00})");
    }

    /// <summary>
    /// tools/om10_layout.py's placement, in 3D. The movement is exported
    /// Y-up with its arbors at their real millimetre positions; one chosen
    /// arbor is carried to a chosen point on the dial and the whole assembly
    /// turned about it. Stated as: shift the arbor to the origin, turn, move
    /// the origin to where it goes.
    /// </summary>
    private static Matrix4x4 MovementPlacement(WatchDesign d)
    {
        var target = new Vector3(d.PlacedArborWorldXZ.X, d.MovementY, d.PlacedArborWorldXZ.Y);

        // The CAD arbor (x, y) is (x, -y) in the Y-up export, so carrying it
        // to the origin is a translation by (-x, 0, +y).
        return Matrix4x4.CreateTranslation(-d.PlacedArborCad.X, 0f, d.PlacedArborCad.Y)
             * ScreenClockwise(d.MovementRotationDeg)
             * Matrix4x4.CreateTranslation(target);
    }

    /// <summary>A turn that is clockwise as seen on the dial. Y points at the
    /// viewer, so that is a NEGATIVE rotation about Y - the sign every
    /// Reading angle needs before it can drive a transform.</summary>
    private static Matrix4x4 ScreenClockwise(float degrees) =>
        Matrix4x4.CreateRotationY(-degrees * MathF.PI / 180f);

    /// <summary>A clockwise turn about a vertical axis through <paramref name="pivot"/>.</summary>
    private static Matrix4x4 ScreenClockwiseAbout(float degrees, Vector3 pivot) =>
        Matrix4x4.CreateTranslation(-pivot) * ScreenClockwise(degrees) * Matrix4x4.CreateTranslation(pivot);

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

    /// <summary>The camera and light for one instant, from the design's
    /// rig. Both drift slowly, and that drift is the point of the whole
    /// pipeline: the sunburst's lobes and the hands' facets only read as
    /// metal when the light moves.</summary>
    private readonly struct Rig
    {
        public readonly Matrix4x4 View, Proj, LightViewProj, EnvRot;
        public readonly Vector3 Eye, LightDir;

        public Rig(WatchDesign d, double seconds, float aspect)
        {
            var t = (float)seconds;
            const float toRad = MathF.PI / 180f;

            // ---- camera
            var tilt = (d.CameraTiltDeg + d.CameraTiltSwingDeg * MathF.Sin(t / 41f)) * toRad;
            var swing = (d.CameraSwingDeg * MathF.Sin(t / 53f)) * toRad;
            var distance = d.CameraDistance;
            Eye = new Vector3(distance * MathF.Sin(swing), distance * MathF.Cos(tilt), distance * MathF.Sin(tilt));
            View = Matrix4x4.CreateLookAt(Eye, Vector3.Zero, -Vector3.UnitZ);
            var fov = 2f * MathF.Atan(d.ViewHeightMm * 0.5f / distance);
            Proj = Matrix4x4.CreatePerspectiveFieldOfView(fov, aspect, distance * 0.66f, distance * 1.4f);

            // ---- key light
            var bearing = (d.KeyBearingDeg + d.KeyBearingSwingDeg * MathF.Sin(t / 29f)) * toRad;
            var elevation = (d.KeyElevationDeg + d.KeyElevationSwingDeg * MathF.Sin(t / 37f)) * toRad;
            LightDir = Vector3.Normalize(new Vector3(
                MathF.Sin(bearing) * MathF.Cos(elevation),
                MathF.Sin(elevation),
                -MathF.Cos(bearing) * MathF.Cos(elevation)));
            var lightView = Matrix4x4.CreateLookAt(LightDir * 100f, Vector3.Zero, -Vector3.UnitZ);
            var lightProj = Matrix4x4.CreateOrthographic(66f, 66f, 20f, 200f);
            LightViewProj = lightView * lightProj;

            // ---- environment
            var yaw = d.EnvYaw + d.EnvYawSwing * MathF.Sin(t / 67f);
            EnvRot = Matrix4x4.CreateRotationX(d.EnvPitchDeg * toRad) * Matrix4x4.CreateRotationY(yaw);
        }
    }

    /// <summary>The colour behind the panel, sRGB as the theme gives it.
    /// See post.hlsl for why this is a constant and not alpha.</summary>
    public Vector3 Backdrop { get; set; } = new(0.05f, 0.05f, 0.07f);

    public void Render(ID3D11RenderTargetView backBuffer, int width, int height, DateTime now, double seconds)
    {
        EnsureTargets(width, height);
        var ctx = _context;
        var d = _design;
        var rig = new Rig(d, seconds, (float)width / height);
        var reading = _caliber.Read(now);

        // ---- frame constants
        var frame = new FrameConstants
        {
            ViewProj = rig.View * rig.Proj,
            LightViewProj = rig.LightViewProj,
            EnvRot = rig.EnvRot,
            CameraPos = rig.Eye,
            Exposure = d.Exposure,
            LightDir = rig.LightDir,
            ShadowTexel = 1f / ShadowSize,
            LightColour = d.KeyColour,
            Time = (float)seconds,
            ApertureCentre = d.ApertureCentre,
            ApertureRadius = d.ApertureRadius,
            TrackRadius = d.TrackRadius,
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
        ctx.RSSetState(_rasterCrystal);
        ctx.OMSetDepthStencilState(_depthReadOnly);
        ctx.OMSetBlendState(_blendCrystal);
        ctx.VSSetShader(_vsCrystal);
        ctx.PSSetShader(_psCrystal);
        Draw(_case["crystal"], d.Polished, Matrix4x4.Identity);

        // ---- 4. resolve and present
        ctx.PSSetShaderResource(3, null);
        ctx.OMSetRenderTargets((ID3D11RenderTargetView?)null);
        ctx.ResolveSubresource(_resolved!, 0, _colourMsaa!, 0, Format.R16G16B16A16_Float);
        ctx.OMSetRenderTargets(backBuffer);
        // Back to cull-none: the crystal pass left the back-culling state
        // set, and the post pass's full-screen triangle winds clockwise -
        // it was culled whole, and the panel showed the swap chain's
        // never-painted black. Measured, not reasoned.
        ctx.RSSetState(_rasterMain);
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
        var d = _design;

        // The movement, part by part, each turned about its arbor.
        foreach (var (name, mesh) in _movement)
        {
            var material = d.Movement.TryGetValue(name, out var m) ? m : d.Polished with { Recess = true };
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
                world = ScreenClockwiseAbout((float)degrees, new Vector3(arbor.X, 0f, arbor.Y)) * _movementWorld;
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
                mat = mat with { FinishDir = Vector3.Normalize(Vector3.TransformNormal(d.CotesDirection, _movementWorld)) };
            }
            Draw(mesh, mat, world);
        }

        // The case and dial furniture: everything in case.glb that does not
        // move, then the three hands about their arbors. The hour and minute
        // hands are modelled on the centre wheel's arbor at the dial centre;
        // the seconds hand on the fourth wheel's, wherever the placement put
        // it, and it turns about that same derived point.
        foreach (var (name, mesh) in _case)
        {
            if (name is "crystal" or "hour_hand" or "minute_hand" or "seconds_hand") continue;
            Draw(mesh, CaseMaterial(name), Matrix4x4.Identity);
        }
        Draw(_case["hour_hand"], CaseMaterial("hour_hand"), ScreenClockwise((float)reading.Hour));
        Draw(_case["minute_hand"], CaseMaterial("minute_hand"), ScreenClockwise((float)reading.Minute));
        Draw(_case["seconds_hand"], CaseMaterial("seconds_hand"), ScreenClockwiseAbout((float)reading.Second, _secondsArbor));
    }

    private Material CaseMaterial(string name) =>
        _design.Case.TryGetValue(name, out var m) ? m : _design.Polished;

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
        foreach (var mesh in _case.Values) mesh.Dispose();
        foreach (var disposable in new IDisposable[]
        {
            _vsWatch, _vsShadow, _vsCrystal, _vsPost, _psWatch, _psShadow, _psCrystal, _psPost, _layout,
            _frameCb, _objectCb, _postCb, _linearClamp, _shadowCmp, _point, _rasterMain, _rasterShadow, _rasterCrystal,
            _depthOn, _depthReadOnly, _depthOff, _blendOpaque, _blendCrystal,
            _shadowSrv, _shadowDsv, _shadowTex, _dialPrint, _environment,
        }) disposable.Dispose();
    }
}
