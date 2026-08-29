using System;
using System.Diagnostics;
using System.Globalization;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace ClockWall;

/// <summary>
/// The hero clock: an analogue face, a compact HH:MM:SS/AM-PM line, and the
/// date beneath it. Self-contained - starts its own wall-clock-aligned
/// timer on Loaded and tears it down on Unloaded.
/// </summary>
public sealed partial class ClockPanel : UserControl
{
    /// <summary>Where the analogue/digital choice is remembered: one word, one
    /// line - the same shape as the shell's window-position file, and the same
    /// warning applies: the day a THIRD setting appears, reach for a store.</summary>
    private static string ModeFile => System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ClockWall",
        "clock-mode.txt");

    private DispatcherQueueTimer? _timer;
    private bool _analogue = true;

    public ClockPanel()
    {
        InitializeComponent();
        BuildFaceTicks();

        try
        {
            _analogue = !string.Equals(File.ReadAllText(ModeFile).Trim(), "digital", StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception ex)
        {
            // Missing on first run - analogue stands as the default.
            Debug.WriteLine($"[ClockWall] no clock mode restored: {ex.Message}");
        }

        ApplyMode();
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    /// <summary>Flips between the analogue face and the digital hero, and
    /// remembers the choice. Wired to the C accelerator in the shell.</summary>
    public void ToggleFace()
    {
        _analogue = !_analogue;
        ApplyMode();
        UpdateClock();

        try
        {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(ModeFile)!);
            File.WriteAllText(ModeFile, _analogue ? "analogue" : "digital");
        }
        catch (Exception ex)
        {
            Debug.WriteLine($"[ClockWall] could not save clock mode: {ex}");
        }
    }

    private void ApplyMode()
    {
        FaceCanvas.Visibility = _analogue ? Visibility.Visible : Visibility.Collapsed;
        DigitalText.Visibility = _analogue ? Visibility.Collapsed : Visibility.Visible;
    }

    /// <summary>
    /// The 60 tick marks around the face, majors on the hours. Constructed
    /// once here rather than written out as 60 XAML elements. Brushes are
    /// borrowed from face elements XAML already themed, so the ticks match
    /// the palette without naming a resource in code.
    /// </summary>
    private void BuildFaceTicks()
    {
        for (var i = 0; i < 60; i++)
        {
            var major = i % 5 == 0;
            var width = major ? 6d : 2d;
            var tick = new Rectangle
            {
                Width = width,
                Height = major ? 34 : 16,
                RadiusX = width / 2,
                RadiusY = width / 2,
                Fill = major ? DateText.Foreground : FaceRing.Stroke,
                // Pivot: the face centre (320,320) relative to a tick whose
                // top edge sits at the 10px ring inset.
                RenderTransform = new RotateTransform { Angle = i * 6, CenterX = width / 2, CenterY = 310 },
            };

            Canvas.SetLeft(tick, 320 - width / 2);
            Canvas.SetTop(tick, 10);
            FaceCanvas.Children.Add(tick);
        }
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (_timer is null)
        {
            _timer = DispatcherQueue.CreateTimer();
            _timer.IsRepeating = false; // we re-arm it ourselves each tick, realigned to the wall clock
            _timer.Tick += OnTick;
        }

        UpdateClock();
        ScheduleNextTick();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        if (_timer is not null)
        {
            _timer.Stop();
            _timer.Tick -= OnTick;
            _timer = null;
        }
    }

    private void OnTick(DispatcherQueueTimer sender, object args)
    {
        UpdateClock();
        ScheduleNextTick();
    }

    /// <summary>
    /// Arms the timer for the moment the real-world clock next crosses a
    /// second boundary, computed fresh from DateTime.Now every time - never
    /// assumed to be a drift-free 1000ms - so display never visibly lags or
    /// skips even if a tick is delayed by the UI thread.
    /// </summary>
    private void ScheduleNextTick()
    {
        if (_timer is null)
        {
            return;
        }

        var msIntoSecond = DateTime.Now.Millisecond;
        var delay = 1000 - msIntoSecond;
        if (delay <= 0 || delay > 1000)
        {
            delay = 1000;
        }

        _timer.Interval = TimeSpan.FromMilliseconds(delay);
        _timer.Start();
    }

    private void UpdateClock()
    {
        var now = DateTime.Now;
        var format = DateTimeFormatInfo.CurrentInfo;

        // "H" in the culture's short time pattern marks a 24-hour clock; "h"
        // marks 12-hour. Re-read every tick so a live region/culture change
        // is picked up without restarting the app.
        var is24Hour = format.ShortTimePattern.IndexOf('H') >= 0;

        int hour;
        if (is24Hour)
        {
            hour = now.Hour;
        }
        else
        {
            hour = now.Hour % 12;
            if (hour == 0)
            {
                hour = 12;
            }
        }

        // Always 2-digit, zero-padded - including the hour in 12-hour mode -
        // so the string's character count (and, combined with tabular figures,
        // its measured width) never changes as digits change. That is what
        // keeps the centered hero line from jittering.
        // The HH:MM lives in exactly one place per mode: beside the seconds
        // under the analogue face, or up in the 400px hero when digital - the
        // compact line then reverts to the ":SS AM" it originally was.
        var time = string.Create(CultureInfo.InvariantCulture, $"{hour:D2}:{now.Minute:D2}");
        HeroRun.Text = _analogue ? time : string.Empty;
        DigitalText.Text = time;
        SecondsRun.Text = string.Create(CultureInfo.InvariantCulture, $":{now.Second:D2}");

        // Hour and minute hands creep continuously; the second hand steps,
        // because the timer already ticks on the wall clock's second boundary.
        // ponytail: a smooth-sweep second hand needs a 60fps animation loop on
        // an always-on panel - not worth the wattage. Composition animation is
        // the upgrade path if it ever is.
        var t = now.TimeOfDay;
        HourAngle.Angle = t.TotalHours % 12 * 30;
        MinuteAngle.Angle = t.TotalMinutes % 60 * 6;
        SecondAngle.Angle = now.Second * 6;

        // A Run has no Visibility - emptying it is how it disappears. The
        // leading space is the gap to the seconds, set at the meridiem's size.
        if (is24Hour)
        {
            MeridiemRun.Text = string.Empty;
        }
        else
        {
            var designator = now.Hour < 12 ? format.AMDesignator : format.PMDesignator;
            MeridiemRun.Text = string.IsNullOrEmpty(designator) ? string.Empty : " " + designator;
        }

        DateText.Text = now.ToString("D", CultureInfo.CurrentCulture);
    }
}
