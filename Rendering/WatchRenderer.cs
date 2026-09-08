using System;
using System.Diagnostics;
using System.IO;
using System.Numerics;
using System.Runtime.InteropServices;
using Microsoft.UI.Xaml.Controls;
using SharpGen.Runtime;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Vortice.Mathematics;
using ISwapChainPanelNative = Vortice.WinUI.ISwapChainPanelNative;
using WinRT;
using static Vortice.Direct3D11.D3D11;

namespace ClockWall.Rendering;

/// <summary>
/// The D3D11 device, the composition swap chain bound to a
/// <see cref="SwapChainPanel"/>, and nothing that is a watch yet.
///
/// WHY THIS IS ITS OWN FILE. Three things go wrong with a swap chain in a XAML
/// tree, and every one of them looks like a rendering bug when it is not:
/// the panel is laid out in DIPs while the swap chain is in pixels, so a 125%
/// wall panel shows a blurry 80% render unless the two are reconciled; the
/// panel resizes after the swap chain was built, so a first frame at 0x0 or
/// a stale size is the ordinary case rather than the exception; and the GPU
/// can be reset out from under the process by a driver update, a TDR or a
/// remote-desktop session, which on a display that runs for days is a
/// certainty rather than a possibility. All three are handled here against a
/// flat clear, where they can be seen, before any geometry exists to hide
/// them behind.
///
/// DEVICE LOST IS A STATE, NOT AN EXCEPTION. Present reports removal; the
/// next frame tears everything down and rebuilds it. The frame loop never
/// stops and never throws - the wall would rather show one wrong frame than
/// no clock. <see cref="Render"/> is therefore safe to call from a per-frame
/// handler whatever the device is doing.
/// </summary>
public sealed class WatchRenderer : IDisposable
{
    /// <summary>The panel this renderer paints into. Held so a device rebuild
    /// can re-attach without the control having to know it happened.</summary>
    private readonly SwapChainPanel _panel;

    private ID3D11Device? _device;
    private ID3D11DeviceContext? _context;
    private IDXGISwapChain2? _swapChain;
    private ID3D11RenderTargetView? _backBuffer;

    /// <summary>The swap chain's current size in PHYSICAL pixels, so a
    /// layout pass that lands on the same size is a no-op rather than a
    /// ResizeBuffers.</summary>
    private int _width, _height;

    /// <summary>The size the panel last asked for, kept separately from what
    /// the swap chain has, because the request can arrive while the device
    /// is down and must survive until it is back.</summary>
    private int _wantWidth, _wantHeight;

    /// <summary>DIP-to-pixel scale of the panel, from the composition tree
    /// rather than the window DPI: the wall's design canvas sits inside a
    /// Viewbox, so the panel's true scale is the window DPI TIMES the
    /// Viewbox factor, and only the composition scale knows both.</summary>
    private float _scaleX = 1f, _scaleY = 1f;

    /// <summary>Set when Present reports the device gone; the next Render
    /// rebuilds before it draws.</summary>
    private bool _deviceLost;

    /// <summary>The watch. Built after the device, torn down with it.</summary>
    private WatchScene? _scene;

    /// <summary>True once the scene has failed to build on this device - a
    /// shader that does not compile, an asset missing from the install.
    /// The panel then shows a plain transparent clear rather than retrying a
    /// multi-second load sixty times a second. A device rebuild clears it,
    /// because a fresh device is the one thing that might change the answer.</summary>
    private bool _sceneFailed;

    public WatchRenderer(SwapChainPanel panel)
    {
        _panel = panel;
    }

    /// <summary>The wall colour behind the panel, sRGB 0..1. The control
    /// reads it off its themed Background so the renderer never names a
    /// colour; see post.hlsl for why the panel composites itself.</summary>
    public System.Numerics.Vector3 Backdrop { get; set; }

    /// <summary>True when there is a device and a swap chain to draw into.
    /// False during a device rebuild, and false before the panel has a size
    /// (a SwapChainPanel measures 0x0 until its first layout, and a 0x0 swap
    /// chain is an error, not an empty picture).</summary>
    public bool IsReady => _swapChain is not null && _backBuffer is not null;

    /// <summary>
    /// Tells the renderer what size the panel is now, in DIPs, and how many
    /// pixels each DIP is. Called from the panel's SizeChanged and
    /// CompositionScaleChanged; cheap to call redundantly. The swap chain is
    /// resized on the NEXT frame, not here, so a burst of layout passes
    /// costs one ResizeBuffers rather than one per pass.
    /// </summary>
    public void SetPanelSize(double dipWidth, double dipHeight, float scaleX, float scaleY)
    {
        _scaleX = scaleX <= 0 ? 1f : scaleX;
        _scaleY = scaleY <= 0 ? 1f : scaleY;

        // Rounded, not truncated: 640 DIPs at 1.25 is exactly 800 pixels, and
        // floating-point layout can hand back 799.9999. A one-pixel-short
        // swap chain gets stretched by the compositor, which is the blur this
        // whole method exists to prevent.
        _wantWidth = Math.Max(1, (int)Math.Round(dipWidth * _scaleX));
        _wantHeight = Math.Max(1, (int)Math.Round(dipHeight * _scaleY));
    }

    /// <summary>
    /// Draws one frame and presents it. Never throws: a failure is logged, the
    /// device is marked lost, and the next call starts again from nothing.
    /// </summary>
    /// <param name="now">The wall clock, which is what the hands and the
    /// escapement are a function of.</param>
    /// <param name="seconds">Monotonic seconds for the things that merely
    /// drift - the light, the camera - and must not jump when the clock is
    /// corrected.</param>
    public void Render(DateTime now, double seconds)
    {
        try
        {
            if (_deviceLost || _device is null)
            {
                ReleaseAll();
                CreateDevice();
                _deviceLost = false;
            }

            if (_wantWidth <= 0 || _wantHeight <= 0)
            {
                return; // not laid out yet; nothing to size a swap chain to
            }

            if (_swapChain is null)
            {
                CreateSwapChain();
            }
            else if (_wantWidth != _width || _wantHeight != _height)
            {
                ResizeSwapChain();
            }

            if (!IsReady)
            {
                return;
            }

            Draw(now, seconds);

            // Interval 1: vsync. The wall is a 60 Hz panel and a watch face
            // has no reason to present faster than it can be shown; tearing
            // on a still image would be the one visible artefact.
            var result = _swapChain!.Present(1, PresentFlags.None);
            if (result.Failure)
            {
                // DeviceRemoved and DeviceReset are the two that mean "start
                // over". Anything else on Present is treated the same way: a
                // swap chain that cannot present is not one worth keeping.
                Debug.WriteLine($"[ClockWall] Present failed {result}; rebuilding device");
                _deviceLost = true;
            }
        }
        catch (Exception ex)
        {
            // Device creation, ResizeBuffers, a SharpGenException from any
            // call - all of them land here, and all of them mean the same
            // thing to a wall display: try again next frame.
            Debug.WriteLine($"[ClockWall] render fault, rebuilding device: {ex.Message}");
            _deviceLost = true;
        }
    }

    // ---------------------------------------------------------------- frame

    private void Draw(DateTime now, double seconds)
    {
        var context = _context!;

        if (_scene is null && !_sceneFailed)
        {
            try
            {
                var assets = Path.Combine(AppContext.BaseDirectory, "Assets");
                // The one place the face is chosen. A second design is a
                // second WatchDesign and this line; see FACE-RECIPE.md.
                _scene = new WatchScene(_device!, context, assets, WatchDesign.BlueSoleil);
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[ClockWall] watch scene failed to build: {ex}");
                _sceneFailed = true;
                LogFault("watch scene failed to build", ex);
            }
        }

        if (_scene is null)
        {
            // Transparent, so the wall's own background shows through the
            // panel and a broken renderer looks like an empty slot rather
            // than a coloured square.
            context.OMSetRenderTargets(_backBuffer!);
            context.RSSetViewport(0, 0, _width, _height);
            context.ClearRenderTargetView(_backBuffer!, new Color4(Backdrop.X, Backdrop.Y, Backdrop.Z, 1f));
            return;
        }

        _scene.Backdrop = Backdrop;
        _scene.Render(_backBuffer!, _width, _height, now, seconds);
    }

    // ---------------------------------------------------------------- device

    private void CreateDevice()
    {
        // BgraSupport is what a swap chain shared with the XAML compositor
        // requires; without it CreateSwapChainForComposition fails with an
        // invalid-arg that says nothing about why.
        var flags = DeviceCreationFlags.BgraSupport;
#if DEBUG
        // The debug layer is only present with the Graphics Tools optional
        // feature installed; asking for it on a machine without it fails
        // device creation outright, so it is tried and then dropped.
        flags |= DeviceCreationFlags.Debug;
#endif

        FeatureLevel[] levels =
        {
            FeatureLevel.Level_11_1,
            FeatureLevel.Level_11_0,
        };

        ID3D11Device device;
        ID3D11DeviceContext context;
        var result = D3D11CreateDevice((IDXGIAdapter?)null, DriverType.Hardware, flags, levels,
            out device, out context);

#if DEBUG
        if (result.Failure)
        {
            flags &= ~DeviceCreationFlags.Debug;
            result = D3D11CreateDevice((IDXGIAdapter?)null, DriverType.Hardware, flags, levels,
                out device, out context);
        }
#endif

        if (result.Failure)
        {
            // WARP is the software rasteriser Windows always ships. Far too
            // slow for the finished watch, but a wall that has lost its GPU
            // driver mid-update should show SOMETHING rather than a black
            // square, and the next rebuild after the driver returns will get
            // hardware back.
            Debug.WriteLine($"[ClockWall] hardware D3D11 device failed ({result}); falling back to WARP");
            D3D11CreateDevice((IDXGIAdapter?)null, DriverType.Warp, flags, levels,
                out device, out context).CheckError();
        }

        _device = device;
        _context = context;
        Debug.WriteLine($"[ClockWall] D3D11 device {device.FeatureLevel}");
    }

    private void CreateSwapChain()
    {
        using var dxgiDevice = _device!.QueryInterface<IDXGIDevice>();
        using var adapter = dxgiDevice.GetAdapter();
        using var factory = adapter.GetParent<IDXGIFactory2>();

        var desc = new SwapChainDescription1
        {
            Width = (uint)_wantWidth,
            Height = (uint)_wantHeight,
            Format = Format.B8G8R8A8_UNorm,
            Stereo = false,
            SampleDescription = new SampleDescription(1, 0),
            BufferUsage = Usage.RenderTargetOutput,
            BufferCount = 2,
            // Composition swap chains must be flip-model, and must scale by
            // stretch. Premultiplied alpha, because the watch is round and
            // the wall background has to show at its corners - Ignore would
            // paint the panel's rectangle solid whatever the shader wrote.
            Scaling = Scaling.Stretch,
            SwapEffect = SwapEffect.FlipSequential,
            AlphaMode = AlphaMode.Premultiplied,
        };

        using var swapChain1 = factory.CreateSwapChainForComposition(_device, desc);
        _swapChain = swapChain1.QueryInterface<IDXGISwapChain2>();
        _width = _wantWidth;
        _height = _wantHeight;

        // The XAML side has to be told the swap chain's pixels are DIPs times
        // the composition scale, or it scales the surface a second time.
        ApplyScaleTransform();
        Attach();
        CreateBackBufferView();
    }

    private void ResizeSwapChain()
    {
        // The back-buffer view has to go before ResizeBuffers will succeed -
        // it holds a reference to a buffer that is about to be recreated.
        _context!.OMSetRenderTargets((ID3D11RenderTargetView?)null);
        _backBuffer?.Dispose();
        _backBuffer = null;

        _swapChain!.ResizeBuffers(2, (uint)_wantWidth, (uint)_wantHeight, Format.B8G8R8A8_UNorm, SwapChainFlags.None);
        _width = _wantWidth;
        _height = _wantHeight;

        ApplyScaleTransform();
        CreateBackBufferView();
    }

    private void ApplyScaleTransform()
    {
        _swapChain!.MatrixTransform = Matrix3x2.CreateScale(1f / _scaleX, 1f / _scaleY);
    }

    private void CreateBackBufferView()
    {
        using var texture = _swapChain!.GetBuffer<ID3D11Texture2D>(0);
        _backBuffer = _device!.CreateRenderTargetView(texture);
    }

    /// <summary>
    /// Hands the swap chain to the XAML panel. The panel is a WinRT object
    /// projected into .NET; ISwapChainPanelNative is a COM interface on the
    /// SAME object, reached by QueryInterface on the projection's own
    /// IUnknown. The pointer from the projection is borrowed, not owned;
    /// the one QueryInterface returns is ours and is released by the using.
    /// </summary>
    private void Attach()
    {
        var unknown = ((IWinRTObject)_panel).NativeObject.ThisPtr;
        var iid = typeof(ISwapChainPanelNative).GUID;
        Marshal.ThrowExceptionForHR(Marshal.QueryInterface(unknown, in iid, out var ptr));
        using var native = new ISwapChainPanelNative(ptr);
        native.SetSwapChain(_swapChain);
    }

    /// <summary>
    /// A line in render-log.txt under the ClockWall local app data folder. Release builds
    /// compile Debug.WriteLine out, and this face runs on a wall nobody is
    /// attached to with a debugger: when it shows an empty square, the
    /// reason has to be somewhere a person can read it the next morning.
    /// Faults only - never per frame - so the file cannot grow unattended.
    /// </summary>
    private static void LogFault(string what, Exception ex)
    {
        try
        {
            var dir = Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "ClockWall");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "render-log.txt"),
                $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {what}: {ex}{System.Environment.NewLine}");
        }
        catch
        {
            // Logging must never be the thing that fails.
        }
    }

    private void ReleaseAll()
    {
        _scene?.Dispose();
        _scene = null;
        _sceneFailed = false;

        _backBuffer?.Dispose();
        _backBuffer = null;

        // Detach before dropping the swap chain, so the panel is not left
        // pointing at a surface whose device is gone. A failure here is not
        // interesting - the panel is being given a new one shortly.
        if (_swapChain is not null)
        {
            try
            {
                var unknown = ((IWinRTObject)_panel).NativeObject.ThisPtr;
                var iid = typeof(ISwapChainPanelNative).GUID;
                if (Marshal.QueryInterface(unknown, in iid, out var ptr) >= 0)
                {
                    using var native = new ISwapChainPanelNative(ptr);
                    native.SetSwapChain(null!);
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[ClockWall] detach swap chain: {ex.Message}");
            }
        }

        _swapChain?.Dispose();
        _swapChain = null;
        _width = _height = 0;

        _context?.ClearState();
        _context?.Flush();
        _context?.Dispose();
        _context = null;
        _device?.Dispose();
        _device = null;
    }

    public void Dispose()
    {
        ReleaseAll();
    }
}
