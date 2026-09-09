using System;
using ClockWall.Rendering;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace ClockWall;

/// <summary>
/// The studio controls: seven captioned values with a chevron either side.
/// Built in code because the seven cells are identical and a loop is
/// honest about that. Raises <see cref="Adjusted"/> with the control and
/// the step; the owner does the work and hands back the values to show.
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

    private readonly TextBlock[] _values = new TextBlock[Cells.Length];

    /// <summary>A chevron tapped: which number, and +1 or -1.</summary>
    public event Action<LightControl, int>? Adjusted;

    public StudioStrip()
    {
        InitializeComponent();
        for (var i = 0; i < Cells.Length; i++)
        {
            var (control, caption) = Cells[i];
            var cell = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center };
            cell.Children.Add(new TextBlock
            {
                Text = caption,
                Style = (Style)Application.Current.Resources["StudioCaptionTextStyle"],
                HorizontalAlignment = HorizontalAlignment.Center,
            });
            var row = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center };
            row.Children.Add(Chevron("‹", control, -1));
            _values[i] = new TextBlock
            {
                Style = (Style)Application.Current.Resources["StudioValueTextStyle"],
                VerticalAlignment = VerticalAlignment.Center,
                MinWidth = (double)Application.Current.Resources["StudioValueMinWidth"],
                TextAlignment = Microsoft.UI.Xaml.TextAlignment.Center,
            };
            row.Children.Add(_values[i]);
            row.Children.Add(Chevron("›", control, +1));
            cell.Children.Add(row);
            Root.Children.Add(cell);
        }
    }

    private TextBlock Chevron(string glyph, LightControl control, int step)
    {
        var chevron = new TextBlock
        {
            Text = glyph,
            Style = (Style)Application.Current.Resources["StudioChevronTextStyle"],
            VerticalAlignment = VerticalAlignment.Center,
        };
        chevron.Tapped += (_, e) =>
        {
            e.Handled = true;
            Adjusted?.Invoke(control, step);
        };
        return chevron;
    }

    /// <summary>The seven values, in the order of the cells.</summary>
    public void SetValues(string[] values)
    {
        for (var i = 0; i < _values.Length && i < values.Length; i++)
        {
            _values[i].Text = values[i];
        }
    }
}
