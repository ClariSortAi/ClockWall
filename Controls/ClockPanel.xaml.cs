using System;
using System.Diagnostics;
using System.Globalization;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI.ViewManagement;

namespace ClockWall;

/// <summary>
/// The hero clock: an analogue face, a compact HH:MM:SS/AM-PM line, and the
/// date beneath it. Self-contained - starts its own wall-clock-aligned
/// timer on Loaded and tears it down on Unloaded.
///
/// Exactly two things here move: the second hand's step is eased with a small
/// overshoot, and the analogue/digital swap fades through instead of cutting.
/// Both are gated on <see cref="MotionAllowed"/> and both fall back to the
/// instant form this panel had before them - which is the correct
/// reduced-motion behaviour, not a degraded one.
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

    /// <summary>The OS animation-effects switch: Settings &gt; Accessibility &gt;
    /// Visual effects &gt; Animation effects. One instance for the class - the
    /// WinRT activation is not free, and a cached instance still reads the LIVE
    /// setting, so there is nothing a fresh one per query would buy.</summary>
    private static readonly UISettings SystemUi = new();

    /// <summary>False when the user has asked Windows for reduced motion - and
    /// false too if the setting cannot be read at all, because a clock that
    /// keeps ticking is worth more than a clock that eases.</summary>
    // ponytail: polled at each decision point rather than subscribed to the
    // change event. The per-second tick and the per-press toggle both re-read
    // it, so the panel follows the setting within a second on the same "trust
    // the poll" bargain the rest of the app makes, and there is no handler to
    // unhook on Unloaded. Ceiling: an animation already in flight when the user
    // flips the setting runs out its 140ms instead of being cut short.
    private static bool MotionAllowed
    {
        get
        {
            try
            {
                return SystemUi.AnimationsEnabled;
            }
            catch (Exception ex)
            {
                // This is read once a second for the life of the app. It must
                // never be the thing that stops the clock.
                Debug.WriteLine($"[ClockWall] animation setting unreadable: {ex.Message}");
                return false;
            }
        }
    }

    private DispatcherQueueTimer? _timer;
    private bool _analogue = true;

    /// <summary>The second the hand is currently drawn at, or -1 before the
    /// first paint. The step is only ever eased from here to here+1; every
    /// other delta is a jump and gets snapped.</summary>
    private int _lastSecond = -1;

    /// <summary>The one in-flight half of a face swap, or null. Identity is the
    /// whole re-entrancy story: a sequence that is no longer this field is a
    /// sequence the panel has abandoned, and its Completed handler says so.</summary>
    private Storyboard? _faceSwap;

    /// <summary>The current second-hand step, held only so the next tick can
    /// stop it before writing the hand's new resting angle.</summary>
    private Storyboard? _secondSweep;

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
        ApplyModeAnimated();
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
    /// ToggleFace's form of <see cref="ApplyMode"/>: the same two Visibility
    /// writes, with ~250ms of fade wrapped either side of them.
    ///
    /// It is a fade THROUGH, not a crossfade. FaceCanvas and DigitalText are
    /// siblings in a vertical StackPanel, so a single frame with both Visible
    /// stacks one on top of the other and shoves the date - and everything the
    /// wall puts below it - down by the face's 640px. Not moving the layout is
    /// what most of the comments in this control are about, so the flip itself
    /// stays instantaneous and only the opacity either side of it is eased:
    /// out over 120ms, flip, in over 130ms. Opacity composites off the UI
    /// thread, so neither ramp needs the dependent-animation opt-in.
    /// </summary>
    private void ApplyModeAnimated()
    {
        // A second C press inside the 250ms drops the sequence in flight and
        // starts a fresh one from a known state. Nothing is left half-faded
        // because this pins both opacities back to 1.0.
        StopFaceSwap();

        if (!MotionAllowed)
        {
            // The instant flip IS the reduced-motion form - it is exactly what
            // the constructor path does, and it is what this control shipped
            // with. There is no separate degraded path to write.
            ApplyMode();
            return;
        }

        // Whatever is actually on screen is what fades out - asked of the tree
        // rather than derived from _analogue, because a press that lands
        // mid-swap has already flipped the flag while the Visibility it
        // implies has not happened yet. In the ordinary single press the two
        // answers are the same one.
        // ponytail: a double press therefore fades one element out and the
        // same element straight back in, rather than reversing the ramp that
        // was in flight. It is coherent, it never strands the panel, and it
        // costs one branch. Reversing properly means reading the live opacity
        // and shortening the return ramp to match - worth it only if somebody
        // is sitting there drumming on the C key.
        UIElement outgoing = FaceCanvas.Visibility == Visibility.Visible ? FaceCanvas : (UIElement)DigitalText;

        var swap = FadeOpacity(outgoing, 1.0, 0.0, 120);
        _faceSwap = swap;

        // The storyboard is captured rather than read off the Completed
        // sender, so the identity check in the handler cannot be fooled by a
        // null or surprising sender - it compares the object this call made.
        swap.Completed += (_, _) => OnFaceFadedOut(swap);
        swap.Begin();
    }

    /// <summary>
    /// Half two of the swap: flip, then bring the new hero up. Every decision
    /// reads <see cref="_analogue"/> instead of anything captured 120ms ago,
    /// so the sequence is idempotent - it always drives toward the mode that is
    /// current NOW, whatever the user did to the C key in the meantime.
    /// </summary>
    private void OnFaceFadedOut(Storyboard swap)
    {
        // A sequence StopFaceSwap has already abandoned must not flip anything
        // on its way out; the panel is no longer listening to it.
        if (!ReferenceEquals(swap, _faceSwap))
        {
            return;
        }

        ApplyMode();

        // Stop releases the outgoing element's opacity back to its local 1.0,
        // so it has to come AFTER ApplyMode collapsed it - the other order pops
        // it to full for the frame in between. Collapsed, nobody sees it, and
        // it is left at 1.0 ready for the next swap.
        swap.Stop();

        // From=0 rather than writing Opacity=0 first: if the storyboard never
        // runs, the incoming hero is still at 1.0 and visible instead of
        // stranded invisible, which on this panel is the failure that matters.
        // ponytail: that leaves a theoretical frame where it could render at
        // full opacity before the ramp's first frame lands. Begin applies From
        // before the next composition pass, so it has not been seen - and the
        // alternative trades an invisible glitch for a permanent visible one.
        UIElement incoming = _analogue ? FaceCanvas : (UIElement)DigitalText;

        // No Completed of its own: it ends on 1.0, which is already the local
        // value StopFaceSwap wrote, so there is nothing to restore. The next
        // swap - or Unloaded - stops it.
        _faceSwap = FadeOpacity(incoming, 0.0, 1.0, 130);
        _faceSwap.Begin();
    }

    /// <summary>Drops any swap in flight and leaves both heroes at full
    /// opacity. The order is load-bearing twice: the field is cleared before
    /// Stop so a Completed raised on the way out fails its identity check, and
    /// the opacities are written after Stop because a storyboard still holding
    /// a property outranks a direct assignment to it.</summary>
    private void StopFaceSwap()
    {
        var swap = _faceSwap;
        _faceSwap = null;
        swap?.Stop();

        FaceCanvas.Opacity = 1.0;
        DigitalText.Opacity = 1.0;
    }

    /// <summary>One eased opacity ramp on one element, built but not started.
    /// Opacity composites off the UI thread, so this costs no UI-thread frames
    /// and needs no EnableDependentAnimation - the same bargain the roster's
    /// busy pulse makes.</summary>
    private static Storyboard FadeOpacity(UIElement target, double from, double to, int milliseconds)
    {
        var fade = new DoubleAnimation
        {
            From = from,
            To = to,
            Duration = new Duration(TimeSpan.FromMilliseconds(milliseconds)),
            // EaseOut on both halves: the outgoing hero leaves briskly and the
            // incoming one arrives soft, which is what a replacement looks like
            // when it is not asking to be watched.
            EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut },
        };

        Storyboard.SetTarget(fade, target);
        Storyboard.SetTargetProperty(fade, "Opacity");

        var storyboard = new Storyboard();
        storyboard.Children.Add(fade);
        return storyboard;
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

        // Motion goes with the timer. ApplyMode is the part that matters:
        // unloading BETWEEN the two halves of a swap leaves the outgoing hero
        // on screen while _analogue already names the other one, and a control
        // that is re-loaded rather than torn down would come back wrong. The
        // second reset makes the first paint after such a reload snap, not
        // ease, on the same "one step only" rule as everything else here.
        _secondSweep?.Stop();
        _secondSweep = null;
        _lastSecond = -1;
        StopFaceSwap();
        ApplyMode();
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

        // Hour and minute hands creep continuously and stay instant: their
        // delta between two ticks is a fraction of a degree, and easing a move
        // nobody can see move is frames spent on nothing. The second hand steps
        // a whole 6 degrees, so it is the only one that gets eased.
        // ponytail: still a STEP, not a sweep. A smooth-sweep second hand needs
        // a 60fps loop running forever on an always-on panel - not worth the
        // wattage - where this is 140ms of frames once a second and idle in
        // between. Composition animation remains the upgrade path if a true
        // sweep is ever wanted.
        var t = now.TimeOfDay;
        HourAngle.Angle = t.TotalHours % 12 * 30;
        MinuteAngle.Angle = t.TotalMinutes % 60 * 6;
        StepSecondHand(now.Second);

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

    /// <summary>
    /// Moves the second hand to <paramref name="second"/>, easing the 6 degree
    /// step with a small overshoot when that is both wanted and visible.
    ///
    /// The cost, stated plainly: RotateTransform.Angle is not a composition
    /// property, so this is a DEPENDENT animation - it needs the opt-in below
    /// and its frames run on the UI thread. 140ms of them once a second, on a
    /// panel whose other work per tick is a handful of string assignments, is
    /// noise. The same easing on all three hands, or a continuous sweep, would
    /// not be, which is why neither is here.
    /// </summary>
    private void StepSecondHand(int second)
    {
        // Exactly one second later than what is on screen, and nothing else.
        // The first paint after Loaded (-1), ToggleFace repainting a second the
        // timer already drew, a tick that slipped and skipped one, a resume
        // from suspend, a clock correction - every one of those is a jump, and
        // a jump is snapped: easing a forty minute correction would crawl the
        // hand round the face for 140ms of nonsense, and easing from angle 0 on
        // first paint would swing it up from twelve o'clock every launch.
        var stepped = _lastSecond >= 0 && second == (_lastSecond + 1) % 60;
        _lastSecond = second;

        // Stop first, then write the resting angle. A storyboard still holding
        // the property outranks a direct assignment, so this order is what
        // makes the line below the hand's real position rather than a value
        // the last animation is sitting on top of.
        _secondSweep?.Stop();
        _secondSweep = null;
        SecondAngle.Angle = second * 6;

        // Three ways out, all of them landing on that assignment: the user
        // asked Windows for reduced motion, the face is not on screen at all
        // (digital mode, or the first 120ms of a swap back INTO analogue where
        // the canvas is still collapsed - animating either is invisible work),
        // or this was not a single step. The snap is not a fallback for the
        // first of those; it is the right answer to it.
        if (!stepped || !MotionAllowed || FaceCanvas.Visibility != Visibility.Visible)
        {
            return;
        }

        // The wrap trap: at :00 the hand is at 354 and the target is 0, and
        // 354 -> 0 spins it backwards through almost the whole face. Animate to
        // 360 instead - a RotateTransform is perfectly happy past a full turn -
        // and let the 0 already written above be where the NEXT step starts
        // from. 0 and 360 render identically, so the reset is never seen.
        var to = second == 0 ? 360.0 : second * 6.0;

        // Stepped, so the hand is standing exactly one 6 degree notch back.
        var from = to - 6.0;

        var sweep = new DoubleAnimation
        {
            From = from,
            To = to,
            Duration = new Duration(TimeSpan.FromMilliseconds(140)),
            // Quartz, not cartoon: EaseOut carries the hand about a degree past
            // the mark and settles it back on. Amplitude much past this starts
            // to read as a bounce, which is a toy clock.
            EasingFunction = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.4 },
            EnableDependentAnimation = true,
        };

        // Target the RotateTransform object itself. Naming it in a property
        // path from the Rectangle works too, but this is the form that cannot
        // be broken by someone renaming or restyling the hand above it.
        Storyboard.SetTarget(sweep, SecondAngle);
        Storyboard.SetTargetProperty(sweep, "Angle");

        _secondSweep = new Storyboard();
        _secondSweep.Children.Add(sweep);
        _secondSweep.Begin();
    }
}
