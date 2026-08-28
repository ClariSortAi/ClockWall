using System;
using System.Globalization;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace ClockWall;

/// <summary>
/// The hero clock: a very large HH:MM, a de-emphasized seconds/AM-PM row, and
/// the date beneath it. Self-contained - starts its own wall-clock-aligned
/// timer on Loaded and tears it down on Unloaded.
/// </summary>
public sealed partial class ClockPanel : UserControl
{
    private DispatcherQueueTimer? _timer;

    public ClockPanel()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
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
        HeroText.Text = string.Create(CultureInfo.InvariantCulture, $"{hour:D2}:{now.Minute:D2}");
        SecondsRun.Text = string.Create(CultureInfo.InvariantCulture, $":{now.Second:D2}");

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
