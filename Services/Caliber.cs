using System;
using System.Diagnostics;
using System.Globalization;

namespace ClockWall;

/// <summary>
/// The mechanical specification of one movement, and the whole of the physics
/// behind a mechanical watch face. No UI, no XAML: given a wall-clock instant
/// it returns where every moving part is, so a SECOND dial is a new set of
/// shapes over the same maths rather than a second copy of it.
///
/// Everything derives from one number - the count of beats since midnight.
/// That is not a shortcut, it is how the watch works. The escapement is what
/// gates the gear train: the train is not free-running and separately
/// observed, it advances only when the pallet fork lets a tooth past. So
/// counting releases and multiplying out gives the same answer the wheels do,
/// and it cannot drift out of step with itself the way three independent
/// clocks could.
///
/// WHERE THE BEAT COUNT COMES FROM, AND WHERE IT IS GOING. Today
/// <see cref="Read"/> takes the wall clock and turns it into beats: the
/// balance is a sine of that count, the lever a clamp on it, and nothing
/// here pushes anything. That is KINEMATICS - a description of where the
/// parts are - standing in for an oscillator that does not exist yet. The
/// direction of travel for this project is a watch whose time is driven by
/// its own mechanism: a balance with inertia and a hairspring with a
/// stiffness, integrated; an escapement that delivers impulse at the real
/// unlock, impulse and drop angles; a mainspring whose falling torque lets
/// the amplitude sag. The period then EMERGES and the watch gains or loses
/// like a real one, and the system clock is demoted to what a person does:
/// set the hands once, wind it.
///
/// The seam for that change is this record's contract, not its body. One
/// beat count in, every angle out, is what the sprite face and the live face
/// both consume; the count's source is what changes. <see cref="Mechanism"/>
/// is that change: the same <see cref="Reading"/> out, but the beat count is
/// a count of unlock events from an integrated balance, and the live face
/// reads it. This record stays as the specification and as the kinematic
/// form the sprite face still draws. The argument in the paragraph above -
/// that reading the hands off the clock is "correct" - is correct for a
/// description and wrong for a mechanism.
/// </summary>
/// <param name="Name">Shown under the dial. A caliber's own name, never a
/// brand's - see the header of <see cref="OpenworkedFace"/>.</param>
/// <param name="Vph">Vibrations per hour, the number every spec sheet leads
/// with. 28,800 is the modern Swiss standard; 18,000 is vintage and visibly
/// steppier; 36,000 is high-beat. Changing it changes how the watch MOVES,
/// which is the only knob on this record that anyone will notice.</param>
/// <param name="EscapeTeeth">Teeth on the escape wheel. Sets how far the wheel
/// jumps per beat and nothing else.</param>
/// <param name="BalanceAmplitudeDegrees">How far the balance swings from rest,
/// one way. 270-315 is a healthy fully wound movement; below about 220 a
/// watchmaker starts asking questions.</param>
/// <param name="TrainTeeth">Teeth on the going-train wheel visible in the
/// aperture, and <paramref name="EscapePinionLeaves"/> the leaves of the pinion
/// it drives. Together they are the last gear ratio in the watch, and they are
/// the numbers the drawing is built from too - tools/escapement_geometry.py
/// places that wheel IN MESH from the same pair, so the picture and the motion
/// cannot disagree about what is driving what.</param>
/// <param name="LiftAngleDegrees">How far the balance turns while the impulse
/// pin is inside the fork slot - through unlocking, impulse and drop. This is
/// the number a timing machine asks for before it will read a watch, and 52 is
/// the ordinary Swiss figure. It is the only thing that sets how LONG the lever
/// takes to cross, and therefore how long the escape wheel is running rather
/// than locked: see <see cref="TransitFraction"/>.</param>
public sealed record Caliber(
    string Name,
    int Vph,
    int EscapeTeeth,
    double BalanceAmplitudeDegrees,
    int TrainTeeth = 84,
    int EscapePinionLeaves = 8,
    double LiftAngleDegrees = 52.0)
{
    /// <summary>Releases per second: vibrations per hour over the 3600 seconds
    /// in one. 28,800 vph is 8.</summary>
    public double BeatsPerSecond => Vph / 3600.0;

    /// <summary>Hertz the way a spec sheet quotes it, which is HALF the beat
    /// rate: one full oscillation of the balance is two beats, one in each
    /// direction. 28,800 vph is "4 Hz" and eight ticks a second, both at
    /// once - the pair of numbers that confuses everyone exactly once.</summary>
    public double Hertz => BeatsPerSecond / 2.0;

    /// <summary>Milliseconds between releases. The face's whole frame budget.</summary>
    public double BeatMilliseconds => 1000.0 / BeatsPerSecond;

    /// <summary>Extreme to extreme: how long the balance takes to cross from
    /// one end of its swing to the other. That is exactly ONE beat, because a
    /// beat IS a half-oscillation - so the balance and the seconds hand share a
    /// period outright and only the shape of the motion differs, one gliding
    /// and one stepping.</summary>
    public double BalanceSwingMilliseconds => BeatMilliseconds;

    /// <summary>How far the seconds hand advances per beat. This one number is
    /// the difference between a mechanical watch and a quartz one: 6/7 of a
    /// degree at seven beats a second, against a quartz movement's 6.</summary>
    public double SecondStepDegrees => 6.0 / BeatsPerSecond;

    /// <summary>
    /// How far the escape wheel advances per beat.
    ///
    /// TWO beats per tooth, not one. That is the factor of two in every
    /// train-count formula in the literature, and the geometry behind it is
    /// this: the entry and exit pallets straddle the wheel three and a half
    /// tooth-spaces apart (measured off the OM10: 62.08 degrees, seven half
    /// spaces of nine), so a single release carries it half a space and it
    /// takes a full oscillation to hand one whole tooth through. A 20-tooth
    /// wheel therefore turns once every 40 beats, which at seven beats a second
    /// is 5.7 seconds a revolution, comfortably the fastest thing anyone can
    /// see in the aperture.
    /// </summary>
    public double EscapeStepDegrees => 360.0 / (2.0 * EscapeTeeth);

    /// <summary>
    /// How far the going-train wheel turns per beat.
    ///
    /// NEGATIVE, and that is the point of it being here rather than inlined.
    /// The train wheel drives the escape wheel's pinion through an external
    /// mesh, and two wheels in external mesh turn OPPOSITE ways - a detail that
    /// costs nothing to get right and is glaring when it is wrong, because two
    /// visibly meshed wheels rotating the same way is something the eye rejects
    /// before it can say why.
    ///
    /// 84 teeth driving an 8-leaf pinion means the escape wheel turns 10.5
    /// times for each turn of this one, and this one turns once a MINUTE. That
    /// is not a coincidence and not a choice: it is the wheel that carries the
    /// seconds, and requiring it to keep time is what fixes the beat rate. See
    /// the note on Swiss4Hz. It also makes the aperture readable, because the
    /// wheel in the window sweeps in step with the seconds hand on the dial.
    /// </summary>
    public double TrainStepDegrees => -EscapeStepDegrees * EscapePinionLeaves / TrainTeeth;

    /// <summary>
    /// How much of a beat the lever spends MOVING, as a fraction.
    ///
    /// The whole character of an escapement is in this number being small. The
    /// balance is only inside the fork slot while it is within half a lift
    /// angle of centre, and since it moves as sin, that is
    /// 2·asin(lift/2A)/pi of the beat - about 6% at 52 degrees of lift on a
    /// 285 degree amplitude, so about eight milliseconds of a hundred and
    /// forty three. For the other ninety-four percent the lever is still against
    /// a banking pin and the wheel is locked. A lever that is in motion for any
    /// appreciable part of the beat is not an escapement, it is a windscreen
    /// wiper.
    ///
    /// It falls out of amplitude, which is why a tired movement's lever
    /// visibly dwells longer: the balance is slower through centre, so the same
    /// lift angle takes more of the beat.
    /// </summary>
    public double TransitFraction =>
        2.0 * Math.Asin(Math.Min(1.0, LiftAngleDegrees / 2.0 / BalanceAmplitudeDegrees)) / Math.PI;

    /// <summary>
    /// How fast the balance is moving at its fastest, in degrees per second.
    ///
    /// The number that explains why a running watch is restful to look at and
    /// a badly drawn one is not. Simple harmonic motion peaks at amplitude
    /// times omega, which here is about 6,270 deg/s - so on a 60Hz panel the
    /// wheel covers 104 degrees BETWEEN FRAMES. Nothing on the rim can be
    /// resolved at that rate by a display or by an eye, and a face that draws
    /// it sharply anyway is showing detail the viewer cannot track, which reads
    /// as chaos rather than as speed.
    /// </summary>
    public double PeakBalanceDegreesPerSecond =>
        BalanceAmplitudeDegrees * 2.0 * Math.PI * Hertz;

    /// <summary>The line printed on the dial: "4 Hz · 28,800 vph".</summary>
    public string Signature => string.Create(CultureInfo.InvariantCulture, $"{Hertz:0.#} Hz  ·  {Vph:N0} vph");

    /// <summary>
    /// The caliber in the aperture, and every number on this line is now
    /// measured rather than chosen.
    ///
    /// The wheels rendered through the opening are openmovement.org's OM10 - a
    /// real, open-source Swiss movement - so the tooth counts are counted off
    /// the solids: a 20-tooth escape wheel driven by an 8-leaf pinion on the
    /// same arbor, itself driven by an 84-tooth fourth wheel.
    ///
    /// THE BEAT RATE FOLLOWS FROM THEM; it is not a separate preference. The
    /// fourth wheel carries the seconds, so it must turn exactly once a minute:
    ///
    ///     escape turns per hour = 60 x 84/8          = 630
    ///     vph = 2 x 20 teeth x 630                   = 25,200
    ///
    /// which is 3.5 Hz, an ordinary historical Swiss rate. The previous 28,800
    /// was inherited from the invented 15-tooth wheel, and against these real
    /// counts it puts the fourth wheel round in 52.5 seconds - so the wheel
    /// visible in the opening would slowly drift against the seconds hand on
    /// the dial above it. Nothing crashes; the watch is just wrong, in the one
    /// way a watch is not allowed to be.
    ///
    /// Nothing here identifies a maker: vibration counts and tooth counts are
    /// engineering, published in every service manual.
    /// </summary>
    public static readonly Caliber Swiss4Hz =
        new("CW‑01 OPENWORKED", 25_200, 20, 285);

    /// <summary>
    /// Every moving part's position for one instant: degrees clockwise from
    /// twelve, and a lever position.
    ///
    /// ONE CLOCK, AND IT IS THE BALANCE. Everything below is a function of a
    /// single fractional beat count, including the balance itself - which is
    /// the correction that matters most here. The balance used to be animated
    /// separately and left free to run at whatever phase it happened to start
    /// at, on the argument that at eight beats a second nobody could see which
    /// end of the swing the fork was firing at. That was wrong twice over:
    /// WHEN the lever fires relative to the balance is the only mechanical
    /// content the lever has, and two clocks in a watch slide against each
    /// other, so the relationship was not merely arbitrary but changing.
    /// </summary>
    public Reading Read(DateTime now)
    {
        var day = now.TimeOfDay;

        // Beats since midnight, FRACTIONAL. It used to be floored here, which
        // is why every part below could only teleport. double rather than long:
        // a day is 691,200 beats at 28,800 vph, so this is nowhere near the
        // 2^53 where a double stops resolving the fraction.
        var beats = day.TotalSeconds * BeatsPerSecond;

        // THE BALANCE, and every other line in this method hangs off it.
        //
        // sin rather than cos: it makes the balance cross CENTRE at every whole
        // beat and reach its extremes halfway between, which is the whole
        // point. A beat is a half-oscillation, so the period is two of them -
        // 4 Hz at 28,800 vph, as advertised - and taking beats modulo that
        // period first is not tidiness. A day is 691,200 beats; pi times that
        // has an ulp around 2e-10, so sin() of it is a few times 1e-8 rather
        // than zero AT THE EXACT INSTANT THE LEVER UNLOCKS, and the whole
        // phase relationship this method exists to establish would be
        // approximate at precisely the moment it has to be exact.
        var phase = beats % 2.0;
        var balance = BalanceAmplitudeDegrees * Math.Sin(Math.PI * phase);

        // HOW FAST it is going, normalised, which the face needs for a reason
        // that is about the display rather than the movement: at peak speed the
        // balance covers 119 degrees between two frames at 60fps, so a wheel
        // with two arms aliases into a spinning blur going whichever way it
        // likes. A real one smears and the face imitates that, cross-faded on
        // this number. Derivative of sin is cos; that is the whole of it.
        var speed = Math.Abs(Math.Cos(Math.PI * phase));

        // THE LEVER, which is not a state that alternates - it is a part being
        // pushed by another part. The impulse pin is only inside the fork slot
        // while the balance is within half a lift angle of centre; there the
        // fork goes where the pin puts it, and everywhere else it is jammed
        // against a banking pin. That is this one clamp, and it gives for free
        // everything the parity flip had to be told: it alternates, it snaps,
        // it is motionless in between, it is exactly in phase with the balance
        // because it is DRIVEN by the balance, and it dwells longer when
        // amplitude drops.
        //
        // Normalised to -1..+1 rather than degrees, because a real lever swings
        // a few degrees and the face has to exaggerate that to be visible at
        // all. How far is a drawing decision and lives with the drawing.
        var fork = Math.Clamp(balance / (LiftAngleDegrees / 2.0), -1.0, 1.0);

        // ...and the train is unlocked exactly as long as the lever is moving,
        // so the wheels advance on the SAME ramp rather than jumping. n is the
        // crossing being served; the transit straddles it, half before and half
        // after, so a wheel is mid-step at the instant of the beat itself.
        var n = Math.Round(beats, MidpointRounding.AwayFromZero);
        var heading = (long)n % 2 == 0 ? 1.0 : -1.0;
        var advanced = n - 1.0 + (fork * heading + 1.0) / 2.0;

        return new Reading(
            // Hour and minute come off the motion works, geared straight to the
            // train, so they CREEP. They are the two hands that do not step -
            // on a real watch and therefore on this one. Reading them from the
            // clock rather than from the beat count is not a shortcut: a
            // continuous gear ratio is a continuous function of time.
            Hour: day.TotalHours % 12 * 30,
            Minute: day.TotalMinutes % 60 * 6,

            // ...and these three are the gated train, all on one ramp. The
            // seconds hand runs its 0.75 degrees in the seven milliseconds the
            // lever is crossing and is then held for the other hundred and
            // eighteen, which is what a mechanical seconds hand actually does
            // and why it does not look like a teleport.
            Advanced: advanced,
            Second: Wrap(advanced * SecondStepDegrees),
            Escape: Wrap(advanced * EscapeStepDegrees),
            Train: Wrap(advanced * TrainStepDegrees),

            Balance: balance,
            BalanceSpeed: speed,
            Fork: fork,
            Beat: (long)Math.Floor(beats));
    }

    private static double Wrap(double degrees) => degrees % 360.0;

    /// <summary>
    /// The relations that, if they broke, would leave a watch which still DREW
    /// perfectly and merely moved wrong - a seconds hand that never quite lands
    /// on the marker, an escape wheel drifting against its own fork. That is
    /// the one failure on this dial a screenshot cannot catch and nobody would
    /// report precisely; they would just say it looked off.
    ///
    /// Called from the face's constructor and compiled out of Release
    /// entirely, so a Debug run is the check and a shipped build pays nothing.
    /// </summary>
    [Conditional("DEBUG")]
    internal static void SelfCheck()
    {
        var c = Swiss4Hz;

        Debug.Assert(Math.Abs(c.BeatsPerSecond - 8) < 1e-9,
            "28,800 vph is eight beats a second.");
        Debug.Assert(Math.Abs(c.SecondStepDegrees - 0.75) < 1e-9,
            "Eight steps a second around 360 degrees is 0.75 degrees each.");

        // The stepping only works if the steps DIVIDE the dial. A step that is
        // merely close leaves the hand a fraction off the marker, and the error
        // is invisible on any one beat and glaring after a minute of them.
        Debug.Assert(Math.Abs(60 * c.BeatsPerSecond * c.SecondStepDegrees - 360) < 1e-9,
            "A minute of beats has to be exactly one revolution.");
        Debug.Assert(Math.Abs(2 * c.EscapeTeeth * c.EscapeStepDegrees - 360) < 1e-9,
            "Two beats per tooth, all the way round, has to close on itself.");

        // The two wheels are drawn visibly in mesh, so they must not turn the
        // same way. This is the cheap guard on a sign that is easy to lose in
        // an edit and impossible to miss on the wall.
        Debug.Assert(c.TrainStepDegrees * c.EscapeStepDegrees < 0,
            "Wheels in external mesh turn opposite ways.");

        // THE ONE THE FACE ACTUALLY GOT WRONG. A lever escapement unlocks when
        // the balance crosses CENTRE, so on a whole beat the balance must be at
        // zero and the fork must be mid-flight - and halfway between two beats,
        // at the far end of the swing, the fork must be hard against a banking
        // pin. The old face had these the other way round and then let the
        // balance run on a clock of its own, which is a fork firing at no
        // particular moment. Neither failure changes a single pixel of the
        // drawing, so a screenshot cannot catch it; this can.
        var crossing = c.Read(new DateTime(2026, 1, 1, 12, 0, 30, 500));
        Debug.Assert(Math.Abs(crossing.Balance) < 1e-9,
            "The balance has to be at centre on the beat, not at the end of its swing.");
        Debug.Assert(Math.Abs(crossing.Fork) < 1e-9,
            "The lever has to be crossing on the beat.");

        Debug.Assert(Math.Abs(crossing.BalanceSpeed - 1.0) < 1e-9,
            "The balance is at its fastest as it crosses centre.");

        var extreme = c.Read(new DateTime(2026, 1, 1, 12, 0, 30, 500).AddMilliseconds(c.BeatMilliseconds / 2));
        Debug.Assert(Math.Abs(Math.Abs(extreme.Balance) - c.BalanceAmplitudeDegrees) < 1e-6,
            "Half a beat from the crossing is the top of the swing.");
        Debug.Assert(Math.Abs(Math.Abs(extreme.Fork) - 1.0) < 1e-12,
            "...and there the lever must be locked against a banking pin.");
        Debug.Assert(extreme.BalanceSpeed < 1e-6,
            "...and momentarily stopped, which is the only moment it is in focus.");

        // Locked for the overwhelming majority of the beat. If this ever fails
        // the lever is drifting rather than snapping, which reads as an
        // escapement that fires at random.
        Debug.Assert(c.TransitFraction < 0.12,
            "The lever must be still for most of the beat.");

        // ...and the reading still has to agree with the beat arithmetic at an
        // instant worked out by hand: 30.56s past the minute is 244 beats in
        // and clear of the transit, and 244 steps of 0.75 degrees is 183.
        var settled = c.Read(new DateTime(2026, 1, 1, 12, 0, 30, 560));
        Debug.Assert(Math.Abs(settled.Second - 183.0) < 1e-9,
            "Read disagrees with the beat arithmetic it is supposed to be.");
    }
}

/// <summary>Where every moving part is at one instant: degrees clockwise from
/// twelve, except <see cref="Fork"/>, which is a normalised lever position, and
/// <see cref="Beat"/>, which is a count.</summary>
/// <param name="Balance">Displacement of the balance from rest, positive one
/// way and negative the other. Zero at every whole beat.</param>
/// <param name="Fork">Where the lever is between its two banking pins: -1 at
/// one, +1 at the other, and strictly in between only during the few
/// milliseconds the balance is inside the fork slot. Normalised because the
/// real angle is a few degrees and any face showing it has to exaggerate.</param>
/// <param name="BalanceSpeed">The balance's angular speed as a fraction of its
/// peak: 1 as it crosses centre, 0 at the ends of the swing. Not a mechanical
/// quantity anyone quotes - it is here because the face has to fade the wheel
/// into a smear at the speeds a 60Hz display cannot resolve.</param>
/// <param name="Advanced">How far the gated train has got, in beats, and
/// UNWRAPPED. Escape, Train and Second are all this number times a constant, so
/// they wrap and it does not - which is what lets a caller difference two
/// readings to find how far a wheel moved between two frames without a 360
/// degree step landing in the middle of the subtraction.</param>
public readonly record struct Reading(
    double Hour, double Minute, double Second, double Escape, double Train,
    double Advanced, double Balance, double BalanceSpeed, double Fork, long Beat);
