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
    int TrainTeeth = 64,
    int EscapePinionLeaves = 7,
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
    /// the difference between a mechanical watch and a quartz one: 0.75 degrees
    /// at 4 Hz, against a quartz movement's 6.</summary>
    public double SecondStepDegrees => 6.0 / BeatsPerSecond;

    /// <summary>
    /// How far the escape wheel advances per beat.
    ///
    /// TWO beats per tooth, not one. That is the factor of two in every
    /// train-count formula in the literature, and the geometry behind it is
    /// this: the entry and exit pallets straddle the wheel about two and a half
    /// tooth-spaces apart, so a single release carries it half a space and it
    /// takes a full oscillation to hand one whole tooth through. A 15-tooth
    /// wheel therefore turns once every 30 beats - 3.75 seconds at 4 Hz, which
    /// makes it comfortably the fastest thing anyone can see.
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
    /// 64 teeth driven by a 7-leaf pinion means the escape wheel turns 9.14
    /// times for each turn of this one: about 34 seconds a revolution, slow
    /// enough to read as a different motion from the escapement's jerking.
    /// </summary>
    public double TrainStepDegrees => -EscapeStepDegrees * EscapePinionLeaves / TrainTeeth;

    /// <summary>
    /// How much of a beat the lever spends MOVING, as a fraction.
    ///
    /// The whole character of an escapement is in this number being small. The
    /// balance is only inside the fork slot while it is within half a lift
    /// angle of centre, and since it moves as sin, that is
    /// 2·asin(lift/2A)/pi of the beat - about 6% at 52 degrees of lift on a
    /// 285 degree amplitude, so seven milliseconds of a hundred and twenty
    /// five. For the other ninety-four percent the lever is dead still against
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

    /// <summary>The line printed on the dial: "4 Hz · 28,800 vph".</summary>
    public string Signature => string.Create(CultureInfo.InvariantCulture, $"{Hertz:0.#} Hz  ·  {Vph:N0} vph");

    /// <summary>
    /// A stock 4 Hz Swiss automatic - the beat rate under most of what is in a
    /// boutique window. Nothing on this line identifies a maker: vibration
    /// counts and tooth counts are engineering, published in every service
    /// manual, and shared by dozens of calibers.
    /// </summary>
    public static readonly Caliber Swiss4Hz = new("CW‑01 OPENWORKED", 28_800, 15, 285);

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
        var balance = BalanceAmplitudeDegrees * Math.Sin(Math.PI * (beats % 2.0));

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
            Second: Wrap(advanced * SecondStepDegrees),
            Escape: Wrap(advanced * EscapeStepDegrees),
            Train: Wrap(advanced * TrainStepDegrees),

            Balance: balance,
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

        var extreme = c.Read(new DateTime(2026, 1, 1, 12, 0, 30, 500).AddMilliseconds(c.BeatMilliseconds / 2));
        Debug.Assert(Math.Abs(Math.Abs(extreme.Balance) - c.BalanceAmplitudeDegrees) < 1e-6,
            "Half a beat from the crossing is the top of the swing.");
        Debug.Assert(Math.Abs(Math.Abs(extreme.Fork) - 1.0) < 1e-12,
            "...and there the lever must be locked against a banking pin.");

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
public readonly record struct Reading(
    double Hour, double Minute, double Second, double Escape, double Train,
    double Balance, double Fork, long Beat);
