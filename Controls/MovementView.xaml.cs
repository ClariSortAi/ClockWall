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
            CompositionTarget.Rendering += OnFrame;
        }
        else
        {
            CompositionTarget.Rendering -= OnFrame;
        }
    }

    private void PushSize()
    {
        _renderer.SetPanelSize(Panel.ActualWidth, Panel.ActualHeight,
            Panel.CompositionScaleX, Panel.CompositionScaleY);
    }

    private void OnFrame(object? sender, object e)
    {
        _renderer.Render(_clock.Elapsed.TotalSeconds);
    }
}
