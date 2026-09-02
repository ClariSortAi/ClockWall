using System;
using System.Diagnostics;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI.ViewManagement;

namespace ClockWall;

/// <summary>
/// A mechanical watch face: an openworked dial with the escapement beating in
/// an aperture at six.
///
/// WHAT IT IS MADE OF. Rendered assets, not shapes - the whole face, not just
/// the movement. The parts were vectors twice and looked like a patent drawing
/// both times, because metal reads as metal through what it reflects and
/// through the polished chamfer on every machined edge, and a SolidColorBrush
/// has neither. So every part of the watch is modelled as a solid and lit by a
/// measured photographic studio; see the header of the .xaml for the pipeline
/// and the paint order.
///
/// WHAT MAKES IT MECHANICAL. One thing, and it is not the drawing - the seconds
/// hand does not tick once a second. A 4 Hz caliber releases eight times a
/// second, so the hand advances 0.75 degrees at a time, and that stutter is
/// what the eye reads as "movement" before it has consciously identified a
/// single component. Every other detail here is in service of it: the escape
/// wheel jerking round, the fork snapping between banks, the balance sweeping
/// back and forth behind them. All four come off ONE beat counter in
/// <see cref="Caliber"/>, so they cannot fall out of step with each other -
/// which is the failure that would give the whole thing away.
///
/// NOT A REPLICA OF ANY MAKER. There is no logo, no maker name and no borrowed
/// dial furniture, and there will not be: those are the parts that are somebody
/// else's trademark. What is modelled instead is the engineering - vibrations
/// per hour, tooth counts, balance amplitude, the two-beats-per-tooth relation
/// - which is published in every service manual and belongs to nobody. It is
/// also, conveniently, the half that is actually hard.
///
/// ONE CLOCK. Every part is written from a single call to
/// <see cref="Caliber.Read"/> on a single frame, and there is nothing that
/// remembers where it was. That is not tidiness, it is the fix for the one
/// thing this face got visibly wrong: the balance used to be a Storyboard
/// running on the animation system's own clock while the escapement ran on a
/// timer against the wall clock, so the fork fired at no particular point in
/// the swing, and the two clocks slid against each other so it was a DIFFERENT
/// no-particular-point over the course of an evening. A watch has one clock in
/// it. See <see cref="OnFrame"/>.
///
/// COST, STATED PLAINLY. This face is not free the way the rest of the wall is.
/// It runs a per-frame handler for as long as it is on screen; see
/// <see cref="OnFrame"/> for the wattage and the way out of it.
/// <see cref="SetRunning"/> exists so that none of that happens while the user
/// is looking at one of the other faces.
/// </summary>
public sealed partial class OpenworkedFace : UserControl
{
    /// <summary>The movement this dial is built around. Swapping it for an
    /// 18,000 vph caliber changes how the watch MOVES and nothing else has to
    /// be touched - which is the point of keeping the physics in its own
    /// file.</summary>
    private static readonly Caliber Movement = Caliber.Swiss4Hz;

    /// <summary>How far the pallet fork banks either side of centre. This is
    /// the only invented number in the movement: a real lever swings a few
    /// degrees, which at this size is invisible, so the normalised lever
    /// position out of <see cref="Caliber"/> is scaled up to something that
    /// reads. WHEN it moves is physics and lives there; how far is a drawing
    /// decision and lives here.</summary>
    private const double ForkBankDegrees = 7.0;

    /// <summary>
    /// How far each stepping part must travel in one frame before its jump
    /// stops being a movement and becomes a jolt. Half a tooth-space for the
    /// escape wheel, half the bank travel for the lever, and about a coil for
    /// the hairspring.
    ///
    /// THIS IS THE OPPOSITE PROBLEM TO THE BALANCE. The balance was moving too
    /// far to resolve; these are STILL for 94% of the beat and then jump, eight
    /// times a second. An abrupt onset is the strongest involuntary attention
    /// cue in vision - it is the difference between a dripping tap and running
    /// water - and eight times a second sits in the band that reads as jerky
    /// rather than as motion. A real escapement makes exactly the same jump,
    /// but it takes seven milliseconds over it and an eye integrating over
    /// twenty-five sees a blur. So does this, now.
    /// </summary>
    private const double EscapeFeatureDegrees = 6.0;
    private const double ForkFeatureDegrees = 7.0;
    private const double SpringFeatureDegrees = 6.0;

    /// <summary>Taken as one frame for the smear calculation. Nominal on
    /// purpose: the real interval varies, and the eye integrates over more like
    /// two or three frames anyway, so a measured value would make the wheel
    /// flicker between sharp and smeared as frames arrived early or late -
    /// which is the exact artefact this is here to remove.</summary>
    private const double NominalFrameSeconds = 1.0 / 60.0;

    /// <summary>
    /// How much of the balance's swing the hairspring takes, as a rigid turn.
    ///
    /// A crude stand-in either way - the real distribution runs from all of the
    /// swing at the collet to NONE of it at the stud, and one number for the
    /// whole coil cannot express that. But it was 0.16, which swung the outer
    /// end through 91 degrees, and the outer end is precisely the part that is
    /// pinned to a stud and cannot move at all. Now that the stud is modelled
    /// the mismatch would be visible, so this is the largest rigid turn that
    /// still reads as the coil breathing rather than the whole spring sliding
    /// out from under its own anchor.
    /// </summary>
    private const double SpringTravel = 0.05;

    /// <summary>Same <see cref="UISettings"/> bargain the rest of the app
    /// makes: one instance, polled rather than subscribed to.</summary>
    private static readonly UISettings SystemUi = new();

    /// <summary>False when Windows has been asked for reduced motion, and false
    /// too when the setting cannot be read - a watch that keeps time is worth
    /// more than a watch that beats.</summary>
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
                Debug.WriteLine($"[ClockWall] animation setting unreadable: {ex.Message}");
                return false;
            }
        }
    }

    /// <summary>Only ever runs at 1 Hz. It is not what drives the escapement -
    /// it exists to keep the seconds hand honest when the movement is stopped
    /// for reduced motion, and to notice that the setting has changed.</summary>
    private DispatcherQueueTimer? _timer;

    /// <summary>Whether the escapement is currently running, as opposed to the
    /// face merely being on screen. False under reduced motion, where this
    /// becomes an ordinary quartz-looking clock on purpose - a once-a-second
    /// hand and a still movement IS the right answer to that request, not a
    /// degraded version of one.</summary>
    private bool _beating;

    private bool _running;

    public OpenworkedFace()
    {
        InitializeComponent();

        // Debug builds only; see the method. Here rather than in a static
        // constructor because this is the one place that cares.
        Caliber.SelfCheck();

        // Painted once here so the face is correct the instant it is first
        // shown, rather than at whatever the first timer tick happens to be.
        Draw(DateTime.Now);

        Unloaded += (_, _) => SetRunning(false);
    }

    /// <summary>
    /// Starts or stops the escapement. Called by the panel that owns the face
    /// swap, NOT by Loaded/Unloaded: this control stays loaded and merely
    /// Collapsed while another face is on the wall, and a per-frame handler
    /// redrawing a movement nobody can see is the exact cost this face cannot
    /// afford to pay in the background.
    /// </summary>
    public void SetRunning(bool running)
    {
        if (running == _running)
        {
            return;
        }

        _running = running;

        if (!running)
        {
            StopTimer();
            SetBeating(false);
            return;
        }

        _timer ??= CreateTimer();
        Draw(DateTime.Now);
        Arm();
    }

    private DispatcherQueueTimer CreateTimer()
    {
        var timer = DispatcherQueue.CreateTimer();

        // Re-armed by hand every second rather than left repeating, for the
        // same reason ClockPanel does it: the interval is recomputed against
        // the real clock each time, so a tick that arrives late is absorbed
        // instead of accumulating into visible drift over a day on the wall.
        timer.IsRepeating = false;
        timer.Tick += OnSecond;
        return timer;
    }

    private void StopTimer()
    {
        if (_timer is null)
        {
            return;
        }

        _timer.Stop();
        _timer.Tick -= OnSecond;
        _timer = null;
    }

    private void OnSecond(DispatcherQueueTimer sender, object args)
    {
        Draw(DateTime.Now);
        Arm();
    }

    /// <summary>
    /// Sets the 1 Hz timer for the next second boundary, computed against the
    /// wall clock so a stopped movement's seconds hand still lands ON the
    /// second rather than a drifting fraction past it.
    ///
    /// Also the one place <see cref="MotionAllowed"/> is acted on, so a user
    /// flipping the OS setting sees the escapement stop - or start - within a
    /// second, with no handler to unhook when this face goes away.
    /// </summary>
    private void Arm()
    {
        if (_timer is null || !_running)
        {
            return;
        }

        SetBeating(MotionAllowed);

        if (!_beating)
        {
            Draw(DateTime.Now);
        }

        const double period = 1000.0;
        var into = DateTime.Now.TimeOfDay.TotalMilliseconds % period;
        var delay = period - into;
        if (delay < 1.0)
        {
            // Already on the boundary. Waiting out a whole period is right;
            // firing again immediately would spin on the same second.
            delay += period;
        }

        _timer.Interval = TimeSpan.FromMilliseconds(delay);
        _timer.Start();
    }

    /// <summary>Starts or stops the escapement, as opposed to the face merely
    /// being on screen. Stopped is the honest answer to reduced motion: an
    /// ordinary quartz-looking clock with a once-a-second hand and a still
    /// movement, not a degraded version of a beating one. The parts are parked
    /// at rest on the way out, because a lever frozen mid-transit is a picture
    /// of a broken watch.</summary>
    private void SetBeating(bool beating)
    {
        if (beating == _beating)
        {
            return;
        }

        _beating = beating;

        if (beating)
        {
            CompositionTarget.Rendering += OnFrame;
            return;
        }

        CompositionTarget.Rendering -= OnFrame;
        BalanceAngle.Angle = 0;
        SpringAngle.Angle = 0;
        ForkAngle.Angle = 0;

        // A stopped movement is a stopped movement: every part in focus.
        foreach (var blur in new[] { BalanceBlur, EscapeBlur, ForkBlur, SpringBlur })
        {
            blur.Opacity = 0.0;
        }

        foreach (var sharp in new[] { BalanceSharp, EscapeSharp, ForkSharp, SpringSharp })
        {
            sharp.Opacity = 1.0;
        }
    }

    /// <summary>
    /// The whole of the movement's animation: read the wall clock, write the
    /// parts. Every frame is computed from scratch, so a dropped frame, a
    /// resumed face or a machine coming back from sleep needs no
    /// resynchronising - there is no phase being maintained anywhere that could
    /// be wrong.
    ///
    /// Per-frame, and the reason has changed with the caliber. Sixty frames a
    /// second against EIGHT beats was exactly 15:2, so a frame's phase relative
    /// to the beat took only fifteen values a fifteenth of a beat apart, and the
    /// lever's few milliseconds of travel was narrower than that gap: the
    /// transit was reliably stepped over, and whether it was ever caught was
    /// settled once by the offset between two crystals.
    ///
    /// At seven beats a second, 60 and 7 share no factor. The phase now takes
    /// SIXTY values a sixtieth of a beat apart, which is 2.4 ms, and the lever's
    /// travel is wider than that. So the transit IS sampled now, a few frames
    /// per beat, instead of being aliased away. The smears carry it.
    ///
    /// What per-frame actually buys is that the fork and the balance are read
    /// from the SAME instant, so wherever the sampling comb happens to fall the
    /// two agree - which is the entire fix. A per-beat timer cannot give that
    /// at any frame rate, because it writes the fork on its own schedule and
    /// leaves the balance to an animation running on a third clock.
    /// </summary>
    // ponytail: RotateTransform.Angle is not a composition property, so all six
    // writes below invalidate render on the UI thread, every frame, for as long
    // as this face is the one on the wall. It is the most expensive thing in the
    // app by a wide margin, and it is why SetRunning exists rather than
    // Loaded/Unloaded. It is not, however, MORE expensive than what it replaced:
    // two dependent animations were already running at frame rate on this same
    // thread, plus an 8 Hz timer on top of them.
    // Upgrade path, when the wattage is worth it: take each layer's Visual via
    // ElementCompositionPreview.GetElementVisual and drive
    // RotationAngleInDegrees off the compositor. Note that the balance can no
    // longer be a plain looping keyframe animation if it goes - its phase is the
    // whole point - so it wants an ExpressionAnimation on a clock shared with
    // the escapement, which is a good deal more than ten lines. That is the
    // price of the fix, and it is worth paying.
    private void OnFrame(object? sender, object e) => Draw(DateTime.Now);

    /// <summary>How much of a part's smear to show: none while it is slow
    /// enough to follow, all of it once it covers more than the width of the
    /// smallest thing on it within a frame.</summary>
    private static double Smear(double sweptDegrees, double featureDegrees) =>
        Math.Clamp(Math.Abs(sweptDegrees) / featureDegrees, 0.0, 1.0);

    /// <summary>Writes every hand and every wheel for one instant. No state of
    /// its own - hand it a time and it produces the face, which is what makes
    /// a late or a skipped frame a non-event rather than something to recover
    /// from.</summary>
    private void Draw(DateTime now)
    {
        var reading = Movement.Read(now);

        HourAngle.Angle = reading.Hour;
        MinuteAngle.Angle = reading.Minute;

        if (!_beating)
        {
            // Quartz cadence, deliberately: one 6 degree step a second, and the
            // escapement left exactly where it stood.
            SecondAngle.Angle = now.Second * 6.0;
            return;
        }

        // The frame before this one. Every smear below is driven by how far a
        // part actually travelled between the two, which is what a camera
        // shutter integrates - and it needs no state, because Read is a pure
        // function of the clock.
        var prev = Movement.Read(now - TimeSpan.FromSeconds(NominalFrameSeconds));

        SecondAngle.Angle = reading.Second;

        EscapeAngle.Angle = reading.Escape;
        var escapeSmear = Smear(
            (reading.Advanced - prev.Advanced) * Movement.EscapeStepDegrees,
            EscapeFeatureDegrees);
        EscapeBlur.Opacity = escapeSmear;
        EscapeSharp.Opacity = 1.0 - escapeSmear;
        EscapeBlurAngle.Angle =
            (reading.Advanced + prev.Advanced) / 2.0 * Movement.EscapeStepDegrees % 360.0;

        // The wheel that drives the escape pinion, turning the other way and
        // 10.5 times slower, which puts it round once a minute. Two speeds of
        // rotation in one opening is most of
        // what makes it read as a gear train rather than as a spinning disc -
        // and because both come off the same beat count, the mesh they are
        // drawn in stays honest.
        TrainAngle.Angle = reading.Train;

        // The balance, and the two parts it drives. All three come off the same
        // number, which is the point: the lever is not banking on a schedule of
        // its own, it is being pushed by the impulse pin, and it can only move
        // while the balance is close enough to centre to be inside the fork
        // slot. That is where the beat comes from.
        BalanceAngle.Angle = reading.Balance;

        ForkAngle.Angle = reading.Fork * ForkBankDegrees;
        var forkSmear = Smear((reading.Fork - prev.Fork) * ForkBankDegrees,
                              ForkFeatureDegrees);
        ForkBlur.Opacity = forkSmear;
        ForkSharp.Opacity = 1.0 - forkSmear;
        ForkBlurAngle.Angle = (reading.Fork + prev.Fork) / 2.0 * ForkBankDegrees;

        // ...and the wheel trades places with its smear ON ITS SPEED, which is
        // the whole of the fix for what the wall was showing. BalanceSpeed is
        // |cos|: one as the balance whips through centre, zero where it stops
        // to turn round. So the smear is thickest mid-swing and the sharp
        // wheel owns the two reversals - which is where a real balance is
        // momentarily still, and the only place a camera or an eye ever gets
        // it in focus. The opacity is now a smooth function of the phase
        // instead of a switch, and that is what makes this read as a swing.
        //
        // WHAT WAS HERE, AND WHY IT READ AS TWO FROZEN POSITIONS. The same
        // |cos|, first multiplied by how far the bar travels in one frame over
        // the bar's own angular width - 104 degrees over 7 - and then clamped.
        // That gain is fifteen, so the clamp held at 1 for 96% of the
        // oscillation and the sharp wheel existed only in a 6 ms spike at each
        // reversal. A square wave, not a cross-fade. Measured on the deployed
        // app the layer was on screen in 4 frames out of 240 and at the same
        // two angles every time, which is exactly the complaint.
        //
        // THE FEATURE-WIDTH RULE IS RIGHT FOR THE OTHER THREE AND WRONG HERE.
        // Smear() asks whether a part jumped further than the smallest feature
        // on it, because what those parts fade to is ONE BEAT'S travel: a
        // shutter held open across a jump, so it is either that jump or it is
        // nothing, and a hard threshold is the honest control. What the
        // balance fades to is a rotational average over a WHOLE TURN (see
        // tools/smear.py), which is not a shutter - it is the wheel at speed.
        // Cross-fading to that is a fade between stopped and spinning, so the
        // control on it is speed itself.
        //
        // ponytail: the aliasing the old threshold was defending against is
        // real and has not gone away - past about 60 degrees a frame, half the
        // wheel's three-fold symmetry, the spokes appear to run backwards. It
        // is defended differently now: the sharp layer is under 43% opacity
        // everywhere that happens and falls to zero at the worst of it, over a
        // smear that is uniform and therefore carries no direction at all. If
        // the wall ever shows a counter-rotating ghost, this line is the one
        // knob - a gain on BalanceSpeed, fading out where the aliasing starts
        // rather than fifteen times too early. Do not put the clamp back
        // without measuring it: tools/motion_check.py --balance fits the gain
        // straight out of the pixels and its baseline is the failing one.
        BalanceBlur.Opacity = reading.BalanceSpeed;
        BalanceSharp.Opacity = 1.0 - reading.BalanceSpeed;

        // The hairspring travels a fraction of the wheel's arc, because only the
        // inner coil goes with the staff - the outer end is pinned to the cock,
        // so the spring breathes rather than sweeps. Turning it rigidly would
        // whip the stud through 570 degrees, which is the one thing about a
        // hairspring anybody can see is wrong.
        SpringAngle.Angle = reading.Balance * SpringTravel;

        // The hairspring's smear is held still, like the balance's and for the
        // same reason: rotating a many-turned spiral by d gives back very
        // nearly the same spiral starting a hair further in, so it is
        // rotationally invariant to within a coil. Which is also what a real
        // hairspring does - it breathes concentrically rather than sweeping.
        var springSmear = Smear((reading.Balance - prev.Balance) * SpringTravel,
                                SpringFeatureDegrees);
        SpringBlur.Opacity = springSmear;
        SpringSharp.Opacity = 1.0 - springSmear;
    }
}
