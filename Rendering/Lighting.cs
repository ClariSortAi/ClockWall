using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Numerics;

namespace ClockWall.Rendering;

/// <summary>Which of the rig's seven numbers a control moves.</summary>
public enum LightControl { Bearing, Elevation, KeyLux, Kelvin, AngularSize, AmbientLux, Ev100 }

/// <summary>
/// The studio, in physical units. Seven numbers, every one of them a
/// quantity a light meter, a thermometer or a camera would read:
///
///   key bearing and elevation   degrees; where the softbox stands
///   key illuminance             lux at the dial, normal to the light
///   key colour temperature      kelvin; the light's colour is Planck's law
///                               at that temperature, integrated against the
///                               eye's CIE 1931 matching functions
///   key angular diameter        degrees; a 60 cm softbox at a metre is 33.
///                               It sets the penumbra (PCSS) and the width
///                               of the highlight (Karis' widening)
///   ambient illuminance         lux at the dial from the whole room (the
///                               HDRI), calibrated off the HDRI's own
///                               irradiance read back after the bake
///   EV100                       the camera: exposure = 1 / (1.2 * 2^EV)
///
/// The shader does L = f(v,l) * E * cos(theta) with E in lux and the
/// environment in the same units, then the exposure, then the tone map -
/// the Frostbite / Filament formulation (Lagarde &amp; de Rousiers 2014;
/// google.github.io/filament). Lights are pre-exposed on the CPU so half
/// floats never overflow: the shaders' Exposure constant is 1.
///
/// DEFAULTS are chosen so the first frame is the face as it was before any
/// of this existed - the design's key at 2.0 in the HDRI's own units over an
/// unscaled HDRI - read back in real units: ambient 1000 lux, and the key
/// and the EV that follow from that. Every number persists in
/// %LOCALAPPDATA%\ClockWall\light.txt; delete the file for the defaults.
/// </summary>
internal sealed class LightRig
{
    public float BearingDeg, ElevationDeg, KeyLux, Kelvin, AngularDeg, AmbientLux, Ev100;

    /// <summary>The rig that reproduces the design's look: ambient 1000 lux
    /// over the HDRI's measured irradiance, the key at the design's 2.0 in
    /// those units, and the exposure that made those read as they did.</summary>
    public static LightRig Default(WatchDesign d, float envIrradianceUnits)
    {
        const float ambient = 1000f;
        var exposure = envIrradianceUnits / ambient;             // what 1.0 was worth, in 1/lux
        var rig = new LightRig
        {
            BearingDeg = d.KeyBearingDeg,
            ElevationDeg = d.KeyElevationDeg,
            KeyLux = MathF.Round(2.0f / exposure / 50f) * 50f,
            Kelvin = 5600f,                                      // daylight-balanced, what a studio strobe is
            AngularDeg = 30f,
            AmbientLux = ambient,
            Ev100 = MathF.Round(MathF.Log2(1f / (1.2f * exposure)) * 10f) / 10f,
        };
        return rig;
    }

    public float Exposure => 1f / (1.2f * MathF.Pow(2f, Ev100));
    public float HalfAngleTan => MathF.Tan(AngularDeg * 0.5f * MathF.PI / 180f);

    /// <summary>One press of a control: a third of a stop for anything that
    /// is an amount, a few degrees for anything that is an angle, 250 K for
    /// the temperature. Steps may be negative.</summary>
    public void Adjust(LightControl control, int steps)
    {
        var third = MathF.Pow(2f, steps / 3f);
        switch (control)
        {
            case LightControl.Bearing: BearingDeg = ((BearingDeg + 10f * steps) % 360f + 360f) % 360f; break;
            case LightControl.Elevation: ElevationDeg = Math.Clamp(ElevationDeg + 5f * steps, 5f, 85f); break;
            case LightControl.KeyLux: KeyLux = Math.Clamp(KeyLux * third, 10f, 200000f); break;
            case LightControl.Kelvin: Kelvin = Math.Clamp(Kelvin + 250f * steps, 1800f, 12000f); break;
            case LightControl.AngularSize: AngularDeg = Math.Clamp(AngularDeg + 5f * steps, 1f, 90f); break;
            case LightControl.AmbientLux: AmbientLux = Math.Clamp(AmbientLux * third, 1f, 100000f); break;
            case LightControl.Ev100: Ev100 = Math.Clamp(Ev100 + steps / 3f, -2f, 20f); break;
        }
    }

    public string Describe() => string.Format(CultureInfo.InvariantCulture,
        "key {0:0}° / {1:0}°  ·  {2:#,0} lx  ·  {3:0} K  ·  {4:0}° wide     ambient {5:#,0} lx     EV {6:0.0}",
        BearingDeg, ElevationDeg, KeyLux, Kelvin, AngularDeg, AmbientLux, Ev100);

    /// <summary>A control's slider: its range, its step, and whether the
    /// slider runs in stops (log2) rather than in the unit itself. Amounts
    /// of light are in stops because that is how they feel - a third of a
    /// stop is a third of a stop at 100 lux and at 10,000 - and angles and
    /// temperature are what they are.</summary>
    public readonly record struct SliderScale(double Min, double Max, double Step, bool Stops);

    public static SliderScale Scale(LightControl control) => control switch
    {
        LightControl.Bearing => new(0, 360, 5, false),
        LightControl.Elevation => new(5, 85, 5, false),
        LightControl.KeyLux => new(Math.Log2(10), Math.Log2(200000), 1.0 / 3, true),
        LightControl.Kelvin => new(1800, 12000, 100, false),
        LightControl.AngularSize => new(1, 90, 1, false),
        LightControl.AmbientLux => new(0, Math.Log2(100000), 1.0 / 3, true),
        _ => new(-2, 20, 1.0 / 3, false),
    };

    /// <summary>The value a slider should show for a control now.</summary>
    public double SliderValue(LightControl control) => control switch
    {
        LightControl.Bearing => BearingDeg,
        LightControl.Elevation => ElevationDeg,
        LightControl.KeyLux => Math.Log2(KeyLux),
        LightControl.Kelvin => Kelvin,
        LightControl.AngularSize => AngularDeg,
        LightControl.AmbientLux => Math.Log2(AmbientLux),
        _ => Ev100,
    };

    /// <summary>A slider moved: set the number it stands for.</summary>
    public void SetFromSlider(LightControl control, double value)
    {
        var s = Scale(control);
        value = Math.Clamp(value, s.Min, s.Max);
        var amount = (float)(s.Stops ? Math.Pow(2, value) : value);
        switch (control)
        {
            case LightControl.Bearing: BearingDeg = amount % 360f; break;
            case LightControl.Elevation: ElevationDeg = amount; break;
            case LightControl.KeyLux: KeyLux = amount; break;
            case LightControl.Kelvin: Kelvin = amount; break;
            case LightControl.AngularSize: AngularDeg = amount; break;
            case LightControl.AmbientLux: AmbientLux = amount; break;
            default: Ev100 = amount; break;
        }
    }

    /// <summary>The seven cells for the strip: where each slider sits and
    /// what to print under it, in the order of <see cref="LightControl"/>.</summary>
    public (double Slider, string Text)[] Cells()
    {
        var text = Values();
        var cells = new (double, string)[text.Length];
        for (var i = 0; i < text.Length; i++) cells[i] = (SliderValue((LightControl)i), text[i]);
        return cells;
    }

    /// <summary>The seven values as the strip shows them, in the order of
    /// <see cref="LightControl"/>.</summary>
    public string[] Values() => new[]
    {
        string.Format(CultureInfo.InvariantCulture, "{0:0}°", BearingDeg),
        string.Format(CultureInfo.InvariantCulture, "{0:0}°", ElevationDeg),
        string.Format(CultureInfo.InvariantCulture, "{0:#,0} lx", KeyLux),
        string.Format(CultureInfo.InvariantCulture, "{0:#,0} K", Kelvin),
        string.Format(CultureInfo.InvariantCulture, "{0:0}°", AngularDeg),
        string.Format(CultureInfo.InvariantCulture, "{0:#,0} lx", AmbientLux),
        string.Format(CultureInfo.InvariantCulture, "EV {0:0.0}", Ev100),
    };

    /// <summary>The key's colour, linear sRGB, normalised to Y = 1, from
    /// Planck's law. B(l, T) = 2hc^2 / l^5 / (exp(hc / (l k T)) - 1), integrated
    /// over 380-780 nm against the CIE 1931 2-degree matching functions in
    /// Wyman, Sloan and Shirley's multi-lobe fit (JCGT 2013, within about a
    /// percent of the tables), to XYZ, then the D65 sRGB matrix. There is no
    /// colour chosen anywhere in this: the temperature is the whole input.</summary>
    public static Vector3 Blackbody(float kelvin)
    {
        const double h = 6.62607015e-34, c = 2.99792458e8, k = 1.380649e-23;
        double X = 0, Y = 0, Z = 0;
        for (var nm = 380.0; nm <= 780.0; nm += 5.0)
        {
            var l = nm * 1e-9;
            var B = 2 * h * c * c / Math.Pow(l, 5) / (Math.Exp(h * c / (l * k * kelvin)) - 1);
            X += B * Xbar(nm); Y += B * Ybar(nm); Z += B * Zbar(nm);
        }
        X /= Y; Z /= Y; Y = 1;
        var r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z;
        var g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z;
        var b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z;
        return new Vector3((float)Math.Max(r, 0), (float)Math.Max(g, 0), (float)Math.Max(b, 0));
    }

    private static double G(double l, double mu, double s1, double s2)
    {
        var t = (l - mu) / (l < mu ? s1 : s2);
        return Math.Exp(-0.5 * t * t);
    }
    private static double Xbar(double l) => 1.056 * G(l, 599.8, 37.9, 31.0) + 0.362 * G(l, 442.0, 16.0, 26.7) - 0.065 * G(l, 501.1, 20.4, 26.2);
    private static double Ybar(double l) => 0.821 * G(l, 568.8, 46.9, 40.5) + 0.286 * G(l, 530.9, 16.3, 31.1);
    private static double Zbar(double l) => 1.217 * G(l, 437.0, 11.8, 36.0) + 0.681 * G(l, 459.0, 26.0, 13.4);

    // ---- persistence: one line, seven numbers, invariant culture
    public static string DefaultPath =>
        Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData), "ClockWall", "light.txt");

    public bool TryLoad(string path)
    {
        try
        {
            if (!File.Exists(path)) return false;
            var parts = File.ReadAllText(path).Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length != 7) return false;
            var v = new float[7];
            for (var i = 0; i < 7; i++) v[i] = float.Parse(parts[i], CultureInfo.InvariantCulture);
            BearingDeg = v[0]; ElevationDeg = v[1]; KeyLux = v[2]; Kelvin = v[3]; AngularDeg = v[4]; AmbientLux = v[5]; Ev100 = v[6];
            return true;
        }
        catch (Exception ex) when (ex is IOException or FormatException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    public void Save(string path)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, string.Join(' ', new[] { BearingDeg, ElevationDeg, KeyLux, Kelvin, AngularDeg, AmbientLux, Ev100 }
                .Select(x => x.ToString("0.###", CultureInfo.InvariantCulture))));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Unattended for days: a locked file is not worth a fault.
        }
    }
}
