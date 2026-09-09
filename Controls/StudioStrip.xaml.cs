using System;
using ClockWall.Rendering;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;

namespace ClockWall;

/// <summary>
/// The studio controls: seven captioned sliders with the value under each.
/// Built in code because the seven cells are identical and a loop is
/// honest about that. Each slider's range, step and scale come from
/// <see cref="LightRig.Scale"/>, so what a drag means is decided next to
/// the physics and not here. Raises <see cref="Changed"/> with the control
/// and the slider's value; the owner sets the number and hands back the
/// cells to show. Dragging fires continuously and the face follows live.
/// </summary>
public sealed partial class StudioStrip : UserControl
{
    private static readonly (LightControl Control, string Caption)[] Cells =
    {
        (LightControl.Bearing, "BEARING"),
        (LightControl.Elevation, "HEIGHT"),
        (LightControl.KeyLux, "KEY"),
        (LightControl.Kelvin, "COLOUR"),
        (LightControl.AngularSize, "SOFTBOX"),
        (LightControl.AmbientLux, "ROOM"),
        (LightControl.Ev100, "EXPOSURE"),
    };

    private readonly Slider[] _sliders = new Slider[Cells.Length];
    private readonly TextBlock[] _values = new TextBlock[Cells.Length];
    private bool _syncing;

    /// <summary>A slider moved: which number, and the slider's value on
    /// that control's scale (see LightRig.Scale).</summary>
    public event Action<LightControl, double>? Changed;

    /// <summary>The sliders shown or put away; the toggle word shows which.</summary>
    public bool IsOpen
    {
        get => Root.Visibility == Visibility.Visible;
        set
        {
            Root.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
            Toggle.Text = value ? "STUDIO  ▾" : "STUDIO  ▸";
        }
    }

    public StudioStrip()
    {
        InitializeComponent();
        Toggle.Tapped += (_, e) => { e.Handled = true; IsOpen = !IsOpen; };
        for (var i = 0; i < Cells.Length; i++)
        {
            var (control, caption) = Cells[i];
            var scale = LightRig.Scale(control);
            var cell = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center };
            cell.Children.Add(new TextBlock
            {
                Text = caption,
                Style = (Style)Application.Current.Resources["StudioCaptionTextStyle"],
                HorizontalAlignment = HorizontalAlignment.Center,
            });
            var slider = new Slider
            {
                Minimum = scale.Min,
                Maximum = scale.Max,
                StepFrequency = scale.Step,
                SnapsTo = SliderSnapsTo.StepValues,
                IsThumbToolTipEnabled = false,
                Width = (double)Application.Current.Resources["StudioSliderWidth"],
            };
            slider.ValueChanged += (_, e) =>
            {
                if (!_syncing) Changed?.Invoke(control, e.NewValue);
            };
            _sliders[i] = slider;
            cell.Children.Add(slider);
            _values[i] = new TextBlock
            {
                Style = (Style)Application.Current.Resources["StudioValueTextStyle"],
                HorizontalAlignment = HorizontalAlignment.Center,
            };
            cell.Children.Add(_values[i]);
            Root.Children.Add(cell);
        }
    }

    /// <summary>The seven cells, in the order of <see cref="LightControl"/>:
    /// where each slider sits and what to print under it.</summary>
    public void Sync((double Slider, string Text)[] cells)
    {
        _syncing = true;
        try
        {
            for (var i = 0; i < _sliders.Length && i < cells.Length; i++)
            {
                if (Math.Abs(_sliders[i].Value - cells[i].Slider) > 1e-6) _sliders[i].Value = cells[i].Slider;
                _values[i].Text = cells[i].Text;
            }
        }
        finally
        {
            _syncing = false;
        }
    }
}
