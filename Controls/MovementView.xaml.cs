using System;
using System.Diagnostics;
using ClockWall.Rendering;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace ClockWall;

/// <summary>
/// The real-time watch face: a <see cref="SwapChainPanel"/> and the
/// <see cref="WatchRenderer"/> that paints into it. This control is the XAML
/// half - size, scale, the frame loop and the running flag - and it knows
/// nothing about what the renderer draws.
///
/// SAME BARGAIN AS THE OPENWORKED FACE. It is expensive while running and it
/// must not run while another face is on the wall, so it is started and
/// stopped by the panel that owns the face swap through <see cref="SetRunning"/>,
/// not by Loaded/Unloaded. Collapsed alone would leave the GPU drawing a
/// watch nobody can see.
/// </summary>
public sealed partial class MovementView : UserControl
{
    private readonly WatchRenderer _renderer;
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private bool _running;

    public MovementView()
    {
        InitializeComponent();
        _renderer = new WatchRenderer(Panel);

        // Both of these fire on the UI thread, and both are the same event
        // to the renderer: "the pixel size you should be is now this".
        Panel.SizeChanged += (_, _) => PushSize();
        Panel.CompositionScaleChanged += (_, _) => PushSize();

        Unloaded += (_, _) => SetRunning(false);
    }

    /// <summary>The crown: winds the mechanism. From the W accelerator.</summary>
    public void Wind() => _renderer.Wind();

    /// <summary>The crown pulled or pushed (S) and turned (arrows).</summary>
    public void ToggleCrown() => _renderer.ToggleCrown();
    public void TurnCrown(TimeSpan byHands) => _renderer.TurnCrown(byHands);

    /// <summary>The studio's lights (LightRig): a control moved, or L to
    /// read them, or Ctrl+L to reset. The readout shows for four seconds.</summary>
    public void AdjustLight(LightControl control, int steps)
    {
        _renderer.AdjustLight(control, steps);
        ShowReadout();
    }

    public void ResetLight()
    {
        _renderer.ResetLight();
        ShowReadout();
    }

    public string[] LightValues => _renderer.LightValues;
    public (double Slider, string Text)[]? LightCells => _renderer.LightCells;
    public void SetLight(LightControl control, double sliderValue) => _renderer.SetLight(control, sliderValue);
    public void CommitLight() => _renderer.CommitLight();

    /// <summary>Fires on the UI thread once the renderer's scene is built,
    /// so the strip can read real values rather than blanks.</summary>
    public event Action? SceneReady;
    private bool _sceneReported;

    public void ShowReadout()
    {
        LightReadout.Text = _renderer.LightReadout;
        LightReadout.Visibility = Visibility.Visible;
        _readoutTimer ??= new DispatcherTimer { Interval = TimeSpan.FromSeconds(4) };
        _readoutTimer.Stop();
        _readoutTimer.Tick -= HideReadout;
        _readoutTimer.Tick += HideReadout;
        _readoutTimer.Start();
    }

    private DispatcherTimer? _readoutTimer;

    private void HideReadout(object? sender, object e)
    {
        _readoutTimer?.Stop();
        LightReadout.Visibility = Visibility.Collapsed;
    }

    /// <summary>Starts or stops the frame loop. See the class remarks for
    /// who calls it and why it is not Loaded.</summary>
    public void SetRunning(bool running)
    {
        if (running == _running)
        {
            return;
        }

        _running = running;

        if (running)
        {
            PushSize();
            PushBackdrop();
            CompositionTarget.Rendering += OnFrame;
        }
        else
        {
            CompositionTarget.Rendering -= OnFrame;
        }
    }

    /// <summary>
    /// Hands the renderer the wall colour, so it can paint the corners of
    /// the panel to match: the compositor shows the swap chain opaque
    /// whatever alpha it is given (see post.hlsl), so the face composites
    /// itself over the wall.
    ///
    /// Looked up from the application resources rather than bound in XAML.
    /// The brush lives in Theme.xaml's ThemeDictionaries and the dictionary
    /// resolves it for the active theme; a ThemeResource on the panel
    /// itself was tried first and took the app down with a stowed exception
    /// at load. Read when the face starts, so a theme change is picked up the
    /// next time it does.
    /// </summary>
    private void PushBackdrop()
    {
        try
        {
            if (Application.Current.Resources.TryGetValue("WallBackgroundBrush", out var value)
                && value is SolidColorBrush brush)
            {
                var c = brush.Color;
                _renderer.Backdrop = new System.Numerics.Vector3(c.R / 255f, c.G / 255f, c.B / 255f);
            }
        }
        catch (Exception ex)
        {
            // The renderer keeps its default near-black; a wrong corner
            // colour is not worth a face that will not start.
            Debug.WriteLine($"[ClockWall] wall colour unreadable: {ex.Message}");
        }
    }

    private void PushSize()
    {
        _renderer.SetPanelSize(Panel.ActualWidth, Panel.ActualHeight,
            Panel.CompositionScaleX, Panel.CompositionScaleY);
    }

    private void OnFrame(object? sender, object e)
    {
        _renderer.Render(DateTime.Now, _clock.Elapsed.TotalSeconds);
        if (!_sceneReported && _renderer.LightValues[0] != "")
        {
            _sceneReported = true;
            SceneReady?.Invoke();
        }
    }
}
