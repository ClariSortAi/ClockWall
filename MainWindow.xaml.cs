using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;
using Windows.Graphics.Imaging;
using Windows.Storage;
using Windows.Storage.Streams;
using WinRT.Interop;

namespace ClockWall;

/// <summary>
/// The wall window: chrome-less, always-awake, and sized to the 1080x1920
/// portrait panel. It owns three things and nothing else - the window shell
/// (size, backdrop, presenter, keyboard), the <see cref="SessionWatcher"/>
/// lifecycle, and the command-line entry points. All visual content lives in
/// ClockPanel and AgentListPanel.
/// </summary>
public sealed partial class MainWindow : Window
{
    /// <summary>Design canvas width in physical pixels. See MainWindow.xaml.</summary>
    private const int DesignWidth = 1080;

    /// <summary>Design canvas height in physical pixels.</summary>
    private const int DesignHeight = 1920;

    /// <summary>How long the screenshot path lets the UI settle and the session scan land.</summary>
    private static readonly TimeSpan ScreenshotSettleDelay = TimeSpan.FromSeconds(3);

    /// <summary>Hard ceiling on the screenshot path. It must always terminate.</summary>
    private static readonly TimeSpan ScreenshotWatchdog = TimeSpan.FromSeconds(30);

    private readonly IntPtr _hwnd;
    private readonly string? _screenshotPath;
    private readonly bool _startFullScreen;

    private bool _isFullScreen;
    private bool _closed;

    public MainWindow()
    {
        InitializeComponent();

        (_screenshotPath, _startFullScreen) = ParseCommandLine(Environment.GetCommandLineArgs());

        _hwnd = WindowNative.GetWindowHandle(this);
        Title = "ClockWall";

        // A wall display must survive a transient fault rather than vanish.
        InstallGlobalFaultHandlers();

        // The screen stays on for as long as this process lives.
        Native.SetThreadExecutionState(
            Native.ES_CONTINUOUS | Native.ES_DISPLAY_REQUIRED | Native.ES_SYSTEM_REQUIRED);

        ApplyWindowShell();

        // ---- INTEGRATION POINT -------------------------------------------
        // The whole of the coupling between the shell and the agent panel.
        //
        // AgentListPanel constructs its own SessionWatcher and starts/stops it
        // with its own Loaded/Unloaded, because its row-height maths needs the
        // collection before the first bind. The shell therefore ADOPTS that
        // watcher rather than constructing a second one - two watchers would
        // mean two FileSystemWatchers and two timer sets over the same
        // directory, which the panel explicitly warns against.
        //
        // What the panel does NOT do is dispose: Unloaded only stops it. So the
        // final release stays the shell's job, on window close, below.
        Closed += OnClosed;

        if (_screenshotPath is not null)
        {
            Activated += OnActivatedForScreenshot;
        }
        else if (_startFullScreen)
        {
            EnterFullScreen();
        }
    }

    // ---------------------------------------------------------------- command line

    /// <summary>
    /// Recognises <c>--screenshot PATH</c> and <c>--fullscreen</c>. Anything else
    /// is ignored, so the app always starts rather than failing on a stray argument.
    /// </summary>
    private static (string? ScreenshotPath, bool FullScreen) ParseCommandLine(string[] args)
    {
        string? screenshot = null;
        var fullScreen = false;

        for (var i = 1; i < args.Length; i++)
        {
            switch (args[i].ToLowerInvariant())
            {
                case "--fullscreen" or "-fullscreen" or "/fullscreen":
                    fullScreen = true;
                    break;

                case "--screenshot" or "-screenshot" or "/screenshot":
                    if (i + 1 < args.Length)
                    {
                        screenshot = Path.GetFullPath(args[++i]);
                    }

                    break;
            }
        }

        return (screenshot, fullScreen);
    }

    // ---------------------------------------------------------------- window shell

    /// <summary>
    /// Chrome-less, content extended into the title bar, client area sized to
    /// exactly 1080x1920.
    /// </summary>
    /// <remarks>
    /// Deliberately NO system backdrop. A Mica/Acrylic backdrop only paints its
    /// tinted material while the window is active; the moment it loses focus -
    /// the permanent state of a kiosk - MicaController falls back to a solid
    /// #202020, which is LIGHTER than the #1B1B22 agent cards and so inverts the
    /// card elevation the dark palette is built on. A full-bleed wall panel has
    /// no desktop showing through it, so the material buys nothing and costs the
    /// whole palette. WallRoot therefore keeps the opaque, activation-independent
    /// WallBackgroundBrush from XAML, which is also what lets the HighContrast
    /// theme dictionary reach the window at all.
    /// </remarks>
    private void ApplyWindowShell()
    {
        ExtendsContentIntoTitleBar = true;

        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            // No border, no title bar, no caption buttons: it reads as a panel,
            // not as a window that happens to be showing a clock.
            presenter.SetBorderAndTitleBar(false, false);
            presenter.IsResizable = false;
            presenter.IsMaximizable = false;
            presenter.IsMinimizable = false;
        }

        SizeClientToDesign();
    }

    /// <summary>
    /// Sizes the CLIENT area to 1080x1920 physical pixels.
    /// </summary>
    /// <remarks>
    /// The documented trap here is treating these numbers as DIPs.
    /// <see cref="AppWindow"/> geometry is always raw physical pixels, and
    /// <c>ResizeClient</c> excludes the frame, so this is exactly 1080x1920 real
    /// pixels of content with no arithmetic needed - deliberately NOT multiplied
    /// by the DPI scale, which would overshoot by the scale factor.
    /// <para>
    /// The scale still matters, just one layer up: at the 125% of this machine's
    /// panel those 1080x1920 physical pixels are 864x1536 DIPs, which is why the
    /// XAML wraps a fixed 1080x1920 design canvas in a Viewbox. The DPI is read
    /// here so that relationship is visible in the log rather than implicit.
    /// </para>
    /// </remarks>
    private void SizeClientToDesign()
    {
        try
        {
            var dpi = Native.GetDpiForWindow(_hwnd);
            var scale = dpi <= 0 ? 1.0 : dpi / 96.0;
            Debug.WriteLine(
                $"[ClockWall] dpi={dpi} scale={scale:0.##}x  " +
                $"client={DesignWidth}x{DesignHeight}px = " +
                $"{DesignWidth / scale:0}x{DesignHeight / scale:0} DIPs; " +
                $"Viewbox factor {1 / scale:0.###}");

            AppWindow.ResizeClient(new SizeInt32(DesignWidth, DesignHeight));
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[ClockWall] could not size client area: {ex}");
        }
    }

    // ---------------------------------------------------------------- keyboard

    private void OnExitAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        Close();
    }

    private void OnFullScreenAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;

        if (_isFullScreen)
        {
            ExitFullScreen();
        }
        else
        {
            EnterFullScreen();
        }
    }

    private void EnterFullScreen()
    {
        try
        {
            AppWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
            _isFullScreen = true;
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[ClockWall] could not enter full screen: {ex}");
        }
    }

    private void ExitFullScreen()
    {
        try
        {
            AppWindow.SetPresenter(AppWindowPresenterKind.Overlapped);
            _isFullScreen = false;

            // The presenter is rebuilt on the way back out, so the chrome-less
            // shell has to be reapplied.
            ApplyWindowShell();
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[ClockWall] could not leave full screen: {ex}");
        }
    }

    // ---------------------------------------------------------------- screenshot

    private void OnActivatedForScreenshot(object sender, WindowActivatedEventArgs args)
    {
        Activated -= OnActivatedForScreenshot;
        _ = RunScreenshotAsync(_screenshotPath!);
    }

    /// <summary>
    /// Parks the window at 0,0 at exactly 1080x1920, lets the clock tick and the
    /// session scan land, grabs the screen region and writes a PNG - then exits.
    /// A watchdog guarantees the process terminates even if any of that wedges.
    /// </summary>
    private async Task RunScreenshotAsync(string path)
    {
        StartScreenshotWatchdog();

        var exitCode = 1;
        try
        {
            // 0,0 on the primary display. The panel is 1440x2560 portrait, so a
            // 1080x1920 window fits entirely on-screen and the captured region
            // is guaranteed to be real content rather than clipped desktop.
            if (AppWindow.Presenter is OverlappedPresenter presenter)
            {
                presenter.IsAlwaysOnTop = true;
            }

            AppWindow.Move(new PointInt32(0, 0));
            SizeClientToDesign();
            Native.SetForegroundWindow(_hwnd);

            // Let layout, the first clock tick and the watcher's initial scan land.
            await Task.Delay(ScreenshotSettleDelay);

            // ...and give the compositor a couple of frames to present them.
            await WaitForRenderAsync();
            await WaitForRenderAsync();

            var bounds = GetClientBoundsOnScreen();
            var pixels = Native.CaptureScreenRegion(bounds.X, bounds.Y, bounds.Width, bounds.Height);
            await SavePngAsync(path, pixels, bounds.Width, bounds.Height);

            Console.Out.WriteLine($"{bounds.Width}x{bounds.Height} -> {path}");
            exitCode = 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[ClockWall] screenshot failed: {ex}");
        }

        ReleaseDisplayRequest();
        Environment.Exit(exitCode);
    }

    /// <summary>
    /// Force-terminates if the screenshot path stalls. The flag exists to be
    /// reviewed by a person waiting on a file, so hanging is the worst outcome.
    /// </summary>
    private void StartScreenshotWatchdog()
    {
        var watchdog = DispatcherQueue.CreateTimer();
        watchdog.Interval = ScreenshotWatchdog;
        watchdog.IsRepeating = false;
        watchdog.Tick += (_, _) =>
        {
            Console.Error.WriteLine("[ClockWall] screenshot watchdog fired; exiting.");
            ReleaseDisplayRequest();
            Environment.Exit(2);
        };
        watchdog.Start();
    }

    /// <summary>Completes after the next composition frame is presented.</summary>
    private static Task WaitForRenderAsync()
    {
        var completion = new TaskCompletionSource();

        void OnRendering(object? sender, object e)
        {
            CompositionTarget.Rendering -= OnRendering;
            completion.TrySetResult();
        }

        CompositionTarget.Rendering += OnRendering;
        return completion.Task;
    }

    /// <summary>
    /// The client rectangle in screen coordinates, all in physical pixels. Read
    /// from the window rather than assumed, so the capture stays correct even if
    /// the presenter nudged the geometry.
    /// </summary>
    private RectInt32 GetClientBoundsOnScreen()
    {
        if (Native.GetClientRect(_hwnd, out var client))
        {
            var origin = new Native.POINT { X = client.Left, Y = client.Top };
            if (Native.ClientToScreen(_hwnd, ref origin))
            {
                var width = client.Right - client.Left;
                var height = client.Bottom - client.Top;
                if (width > 0 && height > 0)
                {
                    return new RectInt32(origin.X, origin.Y, width, height);
                }
            }
        }

        return new RectInt32(0, 0, DesignWidth, DesignHeight);
    }

    private static async Task SavePngAsync(string path, byte[] bgra, int width, int height)
    {
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        // Create/truncate first: FileRandomAccessStream opens an existing file.
        File.Create(path).Dispose();

        using var stream = await FileRandomAccessStream.OpenAsync(path, FileAccessMode.ReadWrite);
        var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream);
        encoder.SetPixelData(
            BitmapPixelFormat.Bgra8,
            BitmapAlphaMode.Ignore,
            (uint)width,
            (uint)height,
            96,
            96,
            bgra);
        await encoder.FlushAsync();
    }

    // ---------------------------------------------------------------- lifetime

    private void OnClosed(object sender, WindowEventArgs args)
    {
        if (_closed)
        {
            return;
        }

        _closed = true;

        try
        {
            // See the integration note in the constructor: the panel owns the
            // watcher's construction and start/stop, the shell owns its final
            // disposal so the FileSystemWatcher and timers are released.
            AgentList.Watcher.Dispose();
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[ClockWall] could not dispose the session watcher: {ex}");
        }

        ReleaseDisplayRequest();
    }

    private static void ReleaseDisplayRequest()
    {
        try
        {
            Native.SetThreadExecutionState(Native.ES_CONTINUOUS);
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[ClockWall] could not restore execution state: {ex}");
        }
    }

    /// <summary>
    /// Swallows faults that would otherwise take the display down. Nothing is
    /// silently lost - everything goes to the debug log and stderr - but an
    /// unattended wall panel going blank is worse than a wrong pixel.
    /// </summary>
    private void InstallGlobalFaultHandlers()
    {
        if (Application.Current is { } app)
        {
            app.UnhandledException += (_, e) =>
            {
                Log("XAML", e.Exception);

                // In screenshot mode a fault must not be papered over - the
                // watchdog would then produce a bad PNG instead of a failure.
                e.Handled = _screenshotPath is null;
            };
        }

        AppDomain.CurrentDomain.UnhandledException += (_, e) => Log("AppDomain", e.ExceptionObject as Exception);
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            Log("Task", e.Exception);
            e.SetObserved();
        };

        static void Log(string source, Exception? ex)
        {
            var message = $"[ClockWall] unhandled ({source}): {ex}";
            Debug.WriteLine(message);
            Console.Error.WriteLine(message);
        }
    }
}

/// <summary>
/// Win32 surface used by the shell. Classic <c>DllImport</c> rather than
/// <c>LibraryImport</c> because the GDI capture marshals a managed pixel buffer,
/// which the source generator would require an <c>unsafe</c> block for.
/// </summary>
internal static class Native
{
    internal const uint ES_CONTINUOUS = 0x80000000;
    internal const uint ES_DISPLAY_REQUIRED = 0x00000002;
    internal const uint ES_SYSTEM_REQUIRED = 0x00000001;

    private const int SRCCOPY = 0x00CC0020;
    private const int CAPTUREBLT = 0x40000000;
    private const int BI_RGB = 0;
    private const uint DIB_RGB_COLORS = 0;

    [StructLayout(LayoutKind.Sequential)]
    internal struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BITMAPINFOHEADER
    {
        public uint biSize;
        public int biWidth;
        public int biHeight;
        public ushort biPlanes;
        public ushort biBitCount;
        public uint biCompression;
        public uint biSizeImage;
        public int biXPelsPerMeter;
        public int biYPelsPerMeter;
        public uint biClrUsed;
        public uint biClrImportant;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BITMAPINFO
    {
        public BITMAPINFOHEADER bmiHeader;
        public uint Mask0;
        public uint Mask1;
        public uint Mask2;
    }

    [DllImport("kernel32.dll")]
    internal static extern uint SetThreadExecutionState(uint esFlags);

    [DllImport("user32.dll")]
    internal static extern int GetDpiForWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetForegroundWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetClientRect(IntPtr hwnd, out RECT rect);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool ClientToScreen(IntPtr hwnd, ref POINT point);

    [DllImport("user32.dll")]
    private static extern IntPtr GetDC(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateCompatibleDC(IntPtr hdc);

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int width, int height);

    [DllImport("gdi32.dll")]
    private static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);

    [DllImport("gdi32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeleteObject(IntPtr hgdiobj);

    [DllImport("gdi32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeleteDC(IntPtr hdc);

    [DllImport("gdi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool BitBlt(
        IntPtr hdcDest, int xDest, int yDest, int width, int height,
        IntPtr hdcSrc, int xSrc, int ySrc, int rop);

    [DllImport("gdi32.dll")]
    private static extern int GetDIBits(
        IntPtr hdc, IntPtr hbitmap, uint startScan, uint scanLines,
        [Out] byte[]? bits, ref BITMAPINFO bitmapInfo, uint usage);

    /// <summary>
    /// Copies a screen region into a top-down BGRA8 buffer. Capturing the screen
    /// rather than rendering the XAML tree is what puts the real composed
    /// result - exactly what the wall shows - in the PNG.
    /// </summary>
    internal static byte[] CaptureScreenRegion(int x, int y, int width, int height)
    {
        var screenDc = GetDC(IntPtr.Zero);
        if (screenDc == IntPtr.Zero)
        {
            throw new InvalidOperationException("GetDC failed for the screen.");
        }

        var memoryDc = IntPtr.Zero;
        var bitmap = IntPtr.Zero;

        try
        {
            memoryDc = CreateCompatibleDC(screenDc);
            bitmap = CreateCompatibleBitmap(screenDc, width, height);
            if (memoryDc == IntPtr.Zero || bitmap == IntPtr.Zero)
            {
                throw new InvalidOperationException("Could not create the capture bitmap.");
            }

            var previous = SelectObject(memoryDc, bitmap);
            var copied = BitBlt(memoryDc, 0, 0, width, height, screenDc, x, y, SRCCOPY | CAPTUREBLT);

            // GetDIBits requires the bitmap to be out of the DC again.
            SelectObject(memoryDc, previous);

            if (!copied)
            {
                throw new InvalidOperationException(
                    $"BitBlt failed (win32 {Marshal.GetLastWin32Error()}).");
            }

            var info = new BITMAPINFO();
            info.bmiHeader.biSize = (uint)Marshal.SizeOf<BITMAPINFOHEADER>();
            info.bmiHeader.biWidth = width;
            info.bmiHeader.biHeight = -height; // negative: top-down rows
            info.bmiHeader.biPlanes = 1;
            info.bmiHeader.biBitCount = 32;
            info.bmiHeader.biCompression = BI_RGB;

            var pixels = new byte[checked(width * height * 4)];
            var scanned = GetDIBits(memoryDc, bitmap, 0, (uint)height, pixels, ref info, DIB_RGB_COLORS);
            if (scanned == 0)
            {
                throw new InvalidOperationException("GetDIBits returned no scan lines.");
            }

            // BitBlt leaves the alpha channel at zero; force it opaque so the
            // PNG is not written as a fully transparent image.
            for (var i = 3; i < pixels.Length; i += 4)
            {
                pixels[i] = 0xFF;
            }

            return pixels;
        }
        finally
        {
            if (bitmap != IntPtr.Zero)
            {
                DeleteObject(bitmap);
            }

            if (memoryDc != IntPtr.Zero)
            {
                DeleteDC(memoryDc);
            }

            ReleaseDC(IntPtr.Zero, screenDc);
        }
    }
}
