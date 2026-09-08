using System;
using System.Diagnostics;

namespace ClockWall;

/// <summary>
/// The movement as a MECHANISM: a balance with inertia and a hairspring with
/// a stiffness, integrated in time; an escapement that unlocks, impulses and
/// locks at the real angles; a mainspring whose torque falls as it unwinds.
/// The beat count - the one number every part's position hangs off - is the
/// count of unlock events this simulation has produced, and the time on the
/// hands is that count divided by the beat rate. The system clock is used
/// for exactly two things a person does to a watch: setting it when it is
/// first picked up, and setting it again if it has been left stopped.
///
/// <see cref="Caliber"/> is the specification and still the kinematic form:
/// hand it a wall-clock instant and it draws the movement where a running
/// watch would have it. This class is the running watch. Both produce a
/// <see cref="Reading"/>, so a face cannot tell them apart - which is the
/// seam Caliber's header promised.
///
/// WHAT IS MEASURED AND WHAT IS NOT. The balance's moment of inertia is
/// integrated off the OM10 solids (balance, staff, roller, collet, and the
/// hairspring's share) at brass and steel densities. Every tooth count is
/// counted off the solids. The lift angle is the OM10's. The hairspring's
/// stiffness is NOT measured: the strip in the STEP is 0.020 mm thick, 0.16
/// wide and 133 mm long, which with a 200 GPa alloy gives 1.5 Hz against a
/// train that only keeps time at 3.5 Hz, so the STEP's spring is a
/// placeholder and the stiffness here is the one the train demands - what a
/// 0.036 mm strip of the same width and length would give. The STEP has no
/// mainspring at all (the disc first taken for one is the ratchet wheel),
/// so its torque is a typical figure for a barrel this size. Damping is set so the full-wind amplitude comes
/// out at the caliber's 285 degrees; it is the one constant with no
/// physical source.
///
/// THE PERIOD IS NOT TYPED IN. It comes out of I and k, and it is pulled
/// off that by the escapement: an impulse delivered off-centre advances or
/// retards the balance a little every beat, more at low amplitude, which is
/// why a real watch's rate changes as its spring runs down and why this one
/// drifts against the wall clock by seconds a day. That drift is the
/// point: it is the proof that the time comes from the mechanism.
/// <see cref="Measure"/> runs the mechanism on its own and reports the rate
/// it actually keeps; the scene logs that at start-up.
/// </summary>
public sealed class Mechanism
{
    public Caliber Spec { get; }

    // ------------------------------------------------------------ the numbers

    /// <summary>Moment of inertia of everything on the balance staff, kg m^2.
    /// Off the OM10 solids: balance 1.848e-9 (brass, 8.5 g/cm^3), hairspring
    /// 0.014e-9, roller, collet and staff 0.002e-9.</summary>
    public const double Inertia = 1.864e-9;

    /// <summary>Hairspring stiffness, N m / rad. See the class remarks: the
    /// train's rate and the measured inertia, not the STEP's strip.</summary>
    public double Stiffness { get; }

    /// <summary>Viscous damping, N m s / rad. Set from the full-wind
    /// amplitude, the one constant here with no physical source.</summary>
    public double Damping { get; }

    /// <summary>Mainspring torque at full wind, N m. A typical 6 N mm for a
    /// 14 mm barrel; the STEP carries no mainspring to measure.</summary>
    public const double BarrelTorqueFull = 6.0e-3;

    /// <summary>Torque left at the end of the run, as a fraction of full.</summary>
    public const double BarrelTorqueEmpty = 0.55;

    /// <summary>Turns of the barrel from full wind to stop. With 107 teeth
    /// on the barrel and 16 on the centre pinion the barrel turns once in
    /// 6.69 hours, so six turns is a forty-hour reserve.</summary>
    public const double BarrelTurns = 6.0;
    public const double BarrelTeeth = 107.0;
    public const double CentrePinionLeaves = 16.0;

    /// <summary>The train, counted off the solids. Barrel 107 to centre
    /// pinion 16; centre wheel 75 to third pinion 10; third wheel 72 to
    /// seconds pinion 9; seconds wheel 84 to escape pinion 8.</summary>
    public const double TrainReduction = (CentrePinionLeaves / BarrelTeeth) * (10.0 / 75.0) * (9.0 / 72.0) * (8.0 / 84.0);

    /// <summary>How much of the escape wheel's work reaches the balance as
    /// kinetic energy. Sliding friction on the pallet faces takes the rest;
    /// 0.35 is a Swiss lever's ordinary figure.</summary>
    public const double EscapementEfficiency = 0.35;

    /// <summary>Energy taken from the balance to unlock the wheel, as a
    /// fraction of the impulse it then receives: the draw pulls the pallet
    /// in and the balance has to push it back out.</summary>
    public const double UnlockingLoss = 0.12;

    /// <summary>Fixed integration step. The impulse window is about eight
    /// milliseconds long at 285 degrees; sixteen steps across it keep the
    /// unlock instant honest to a twentieth of a beat.</summary>
    public const double Step = 0.0005;

    /// <summary>A gap longer than this is a watch that stopped - the
    /// process was suspended, the machine slept - and a person sets it
    /// again rather than the mechanism catching up a night's beats.</summary>
    private const double StoppedAfterSeconds = 5.0;

    // ------------------------------------------------------------ the state

    private double _theta;            // balance displacement, rad; + is clockwise on the dial
    private double _omega;            // rad/s
    private long _beats;              // unlock events since the watch was set
    private double _unwound;          // barrel turns spent since full wind
    private bool _inImpulse;
    private double _impulseSign;
    private double _lastPeak;         // |theta| at the last reversal: the amplitude
    private double _lastUnlockAt;     // mechanism time of the last unlock, for Measure

    private DateTime _setAt;          // the instant the beat count was zero
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private double _simulated;        // seconds of mechanism time integrated

    private readonly double _halfLift;

    /// <summary>
    /// Where in the pin's travel the impulse is delivered. The pin enters
    /// the slot half a lift angle before centre; unlocking costs energy
    /// there; the wheel then runs and the impulse face pushes the pallet
    /// while the pin is still in the slot. In a Swiss lever the push does
    /// not begin until the wheel has run through its drop, which puts most
    /// of the impulse AFTER the centre crossing, and an impulse after centre
    /// lengthens the swing's period. That is the escapement error: the
    /// mechanism runs a little slow of its free period, and more so as the
    /// amplitude falls with the spring - which is the drift a real watch
    /// shows and the reason the wall clock and this watch will disagree by
    /// evening. The window starts this fraction of the half-lift before
    /// centre and ends at the slot's edge after it.
    /// </summary>
    public const double ImpulseStartsBeforeCentre = 0.25;

    public Mechanism(Caliber spec, DateTime now)
    {
        Spec = spec;
        _halfLift = spec.LiftAngleDegrees * Math.PI / 180.0 / 2.0;
        var omega0 = 2.0 * Math.PI * spec.Hertz;
        Stiffness = Inertia * omega0 * omega0;

        // Damping from the full-wind amplitude: over one half-period at
        // amplitude A the viscous loss is c A^2 omega0 pi / 2, and it has to
        // equal what one impulse delivers less what unlocking took.
        var amplitude = spec.BalanceAmplitudeDegrees * Math.PI / 180.0;
        var net = ImpulseEnergy(0.0) * (1.0 - UnlockingLoss);
        Damping = 2.0 * net / (Math.PI * amplitude * amplitude * omega0);

        Set(now);
    }

    /// <summary>What a person does with the crown: the hands to now, the
    /// balance given a swing, the spring left as it was.</summary>
    public void Set(DateTime now)
    {
        _setAt = now;
        _beats = 0;
        _simulated = 0;
        _clock.Restart();
        // Start at the top of a swing at the caliber's amplitude, so the
        // first beat is a real one and not a spring settling from rest.
        _theta = Spec.BalanceAmplitudeDegrees * Math.PI / 180.0;
        _omega = 0;
        _lastPeak = _theta;
        _inImpulse = false;
        _impulseSign = -1.0;
    }

    /// <summary>Winds the spring fully, and if the watch had stopped, gives
    /// the balance the shake a person gives a watch to start it. The W key
    /// on the wall stands in for the crown.</summary>
    public void Wind()
    {
        _unwound = 0;
        if (Stopped)
        {
            _theta = Spec.BalanceAmplitudeDegrees * Math.PI / 180.0 * 0.6;
            _omega = 0;
            _lastPeak = _theta;
            _inImpulse = false;
        }
    }

    /// <summary>True once the spring is spent and the balance has died
    /// down below the lift angle, where the pin no longer reaches the fork:
    /// no more unlocks, no more beats, the hands stand. A real watch does
    /// exactly this, and so does this one, forty hours after its last wind.</summary>
    public bool Stopped => _unwound >= BarrelTurns && _lastPeak < _halfLift;

    /// <summary>Energy one impulse hands the balance, joules: the escape
    /// wheel's torque through its half-tooth step, less the escapement's
    /// friction. Falls with the spring.</summary>
    private double ImpulseEnergy(double unwound)
    {
        // Past the last turn there is no torque at all: the spring is slack,
        // the train stands, and the balance runs down on its damping.
        if (unwound >= BarrelTurns) return 0.0;
        var fraction = Math.Clamp(unwound / BarrelTurns, 0.0, 1.0);
        var torque = BarrelTorqueFull * (1.0 - fraction * (1.0 - BarrelTorqueEmpty)) * TrainReduction;
        var stepRad = Spec.EscapeStepDegrees * Math.PI / 180.0;
        return torque * stepRad * EscapementEfficiency;
    }

    /// <summary>One integration step: the escapement's events, then the
    /// balance's equation of motion.</summary>
    private void StepOnce()
    {
        // The pin enters the fork slot when the balance comes within half a
        // lift angle of centre travelling toward it. That is the unlock:
        // the escape wheel is freed, a half-tooth of its motion is spent
        // pushing the pallet, and the push reaches the balance through the
        // pin for as long as the pin is in the slot. Leaving the slot is the
        // drop, and the wheel locks on the other pallet.
        var towardCentre = _theta * _omega < 0;
        var inSlot = Math.Abs(_theta) < _halfLift;
        // A balance swinging less than the lift angle never carries the pin
        // clear of the slot: it cannot unlock the wheel. That is how a
        // watch stops, and it is why one that has stopped needs a shake.
        var canUnlock = _lastPeak >= _halfLift;
        if (!_inImpulse && inSlot && towardCentre && canUnlock)
        {
            _inImpulse = true;
            _impulseSign = Math.Sign(_omega);
            _beats++;
            _lastUnlockAt = _simulated;
            // One half-tooth of the escape wheel is one beat's worth of the
            // barrel: Vph beats per barrel-hour, 107/16 barrel-hours per turn.
            _unwound += 1.0 / (Spec.Vph * (BarrelTeeth / CentrePinionLeaves));
            // Unlocking takes energy out of the balance first.
            var energy = Math.Max(0.0, 0.5 * Inertia * _omega * _omega - ImpulseEnergy(_unwound) * UnlockingLoss);
            _omega = _impulseSign * Math.Sqrt(2.0 * energy / Inertia);
        }
        else if (_inImpulse && !inSlot)
        {
            _inImpulse = false;
        }

        var torque = -Stiffness * _theta - Damping * _omega;
        if (_inImpulse)
        {
            // The impulse energy spread evenly over the part of the pin's
            // travel that the impulse face is actually pushing: from a
            // little before centre to the slot's far edge.
            var along = _theta * _impulseSign;            // the pin's progress through the slot, - before centre
            var start = -ImpulseStartsBeforeCentre * _halfLift;
            if (along >= start)
            {
                torque += _impulseSign * ImpulseEnergy(_unwound) / (_halfLift - start);
            }
        }

        // Semi-implicit Euler: stable for an oscillator at this step.
        var omegaNext = _omega + torque / Inertia * Step;
        if (Math.Sign(omegaNext) != Math.Sign(_omega) && _omega != 0)
        {
            _lastPeak = Math.Abs(_theta);   // a reversal: this is the amplitude
        }
        _omega = omegaNext;
        _theta += _omega * Step;
        _simulated += Step;
    }

    /// <summary>Runs the mechanism up to the present. Called once per frame;
    /// integrates whatever real time has passed since the last call.</summary>
    public void Advance()
    {
        var target = _clock.Elapsed.TotalSeconds;
        if (target - _simulated > StoppedAfterSeconds)
        {
            Set(DateTime.Now);   // left stopped; the owner sets it again
            return;
        }

        while (_simulated + Step <= target)
        {
            StepOnce();
        }
    }

    /// <summary>The escapement's state, in the shape every face consumes.
    /// The lever is where the pin puts it while the pin is in the slot, and
    /// hard against a banking pin otherwise - the rule Caliber draws.</summary>
    public Reading Read()
    {
        var thetaDeg = _theta * 180.0 / Math.PI;
        var halfLiftDeg = Spec.LiftAngleDegrees / 2.0;
        var omega0 = 2.0 * Math.PI * Spec.Hertz;
        var peak = Spec.BalanceAmplitudeDegrees * Math.PI / 180.0 * omega0;

        var fork = _inImpulse ? Math.Clamp(thetaDeg / halfLiftDeg, -1.0, 1.0) : (_theta >= 0 ? 1.0 : -1.0);

        // The train advances with the fork during the impulse and is locked
        // otherwise: half before the crossing and half after, as the
        // kinematic form does, so the two agree on where a wheel stands.
        var heading = _impulseSign >= 0 ? 1.0 : -1.0;
        var advanced = _inImpulse ? _beats - 1.0 + (fork * heading + 1.0) / 2.0 : _beats;

        // The hands read the beat count: the cannon pinion turns once an
        // hour because the train has turned 25,200 times.
        var shown = _setAt.AddSeconds(_beats / Spec.BeatsPerSecond).TimeOfDay;

        return new Reading(
            Hour: shown.TotalHours % 12 * 30,
            Minute: shown.TotalMinutes % 60 * 6,
            Advanced: advanced,
            Second: advanced * Spec.SecondStepDegrees % 360.0,
            Escape: advanced * Spec.EscapeStepDegrees % 360.0,
            Train: advanced * Spec.TrainStepDegrees % 360.0,
            Balance: thetaDeg,
            BalanceSpeed: Math.Min(1.0, Math.Abs(_omega) / peak),
            Fork: fork,
            Beat: _beats);
    }

    /// <summary>Where the watch stands against the wall clock, in seconds
    /// gained (positive) or lost since it was set. The bet's number.</summary>
    public double DriftSeconds => _beats / Spec.BeatsPerSecond - _clock.Elapsed.TotalSeconds;

    /// <summary>The balance's amplitude now, degrees, off its last reversal.</summary>
    public double AmplitudeDegrees => _lastPeak * 180.0 / Math.PI;

    /// <summary>Barrel turns still to run.</summary>
    public double ReserveTurns => Math.Max(0.0, BarrelTurns - _unwound);

    public long Beats => _beats;

    /// <summary>
    /// The rate this mechanism actually keeps, found by running it: beats
    /// over an interval of its own time, after two seconds to settle. This
    /// is a measurement, and it is the number that says whether the bet is
    /// being won - a rate that is the caliber's to the last digit would mean
    /// the period had been typed in after all.
    /// </summary>
    public static (double Hertz, double AmplitudeDegrees, double SecondsPerDay) Measure(Caliber spec, double seconds = 60.0)
    {
        var m = new Mechanism(spec, DateTime.Now);
        var settle = (long)(2.0 / Step);
        var run = (long)(seconds / Step);
        for (var k = 0; k < settle; k++) m.StepOnce();
        // Time from one unlock to another, not a count over an interval: a
        // count is only good to one beat, which over thirty seconds is four
        // hundred seconds a day and hides everything worth knowing.
        var firstBeats = m._beats;
        var firstAt = m._lastUnlockAt;
        var peak = 0.0;
        for (var k = 0; k < run; k++)
        {
            m.StepOnce();
            peak = Math.Max(peak, m._lastPeak);
        }
        var hertz = (m._beats - firstBeats) / 2.0 / (m._lastUnlockAt - firstAt);
        var secondsPerDay = (hertz / spec.Hertz - 1.0) * 86400.0;
        return (hertz, peak * 180.0 / Math.PI, secondsPerDay);
    }
}
