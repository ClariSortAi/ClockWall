using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace ClockWall;

/// <summary>
/// The band between the date and the AGENTS rule: one static line naming what
/// an agent that is WORKING right now is doing - the tool it last called and a
/// short hint at what it called it on. It is rewritten in place on a 1s poll,
/// so what it says is never more than a second behind the roster.
///
/// It renders <see cref="AgentSession.Activity"/>, which the existing
/// transcript follower already produces; this control adds no reading of its
/// own. Give it the roster's live collection with <see cref="Attach"/>.
///
/// Idle sessions are left out on purpose: an idle agent's last tool call can be
/// an hour old and still reads as news. The rest take the band in turn, a few
/// seconds each, and whatever still overruns 1080px is trimmed by the TextBlock
/// rather than scrolled. A line that has to travel to be read is out of date
/// everywhere except the instant it is redrawn.
///
/// With nothing to say it collapses, which hands its height straight back to
/// the roster (MainWindow.PushRosterBudget). The "no agents" case belongs to
/// the agent list's own empty state, not to a blank strip above it.
/// </summary>
public sealed partial class ActivityTicker : UserControl
{
    /// <summary>Ticks of the 1s poll one agent holds the band for.</summary>
    private const int SlotTicks = 4;

    private DispatcherQueueTimer? _timer;
    private IReadOnlyList<AgentSession>? _sessions;
    private int _tick;

    public ActivityTicker()
    {
        InitializeComponent();

        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    /// <summary>Points the ticker at the roster's live session collection. The
    /// roster owns the watcher; this control only reads what it publishes.</summary>
    public void Attach(IReadOnlyList<AgentSession> sessions)
    {
        _sessions = sessions;
        Refresh();
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        // ponytail: a 1s poll rather than subscribing to CollectionChanged plus
        // every session's PropertyChanged (and unsubscribing again on recycle).
        // Refresh is a sort and a list build over at most a handful of sessions
        // plus one TextBlock assignment, and the canvas relays out every second
        // for the clock regardless.
        if (_timer is null)
        {
            _timer = DispatcherQueue.CreateTimer();
            _timer.Interval = TimeSpan.FromSeconds(1);
            _timer.IsRepeating = true;
            _timer.Tick += (_, _) => Refresh();
        }

        Refresh();
        _timer.Start();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e) => _timer?.Stop();

    /// <summary>Rebuilds the line from live state and shows it immediately.
    /// Nothing defers the assignment - no animation, no phase, no completion
    /// callback - because whatever the text has to wait for is time the wall
    /// spends stating something that has stopped being true.</summary>
    private void Refresh()
    {
        var slot = _tick++ / SlotTicks;
        var working = new List<string>();

        // Most recently active first, which for a session waiting on a subagent
        // puts the subagent - the one actually touching files - in the first
        // slot. UpdatedAt is the transcript's mtime for a subagent and the
        // registry file's for a session, so it is exactly "who moved last".
        foreach (var session in (_sessions ?? Array.Empty<AgentSession>()).OrderByDescending(s => s.UpdatedAt))
        {
            // Not working, or working but yet to call anything: either way
            // there is nothing true to say about it this second. Subagents are
            // in here too, and are often the thing actually doing the work -
            // the watcher only surfaces the live ones, and it marks them busy.
            if (!session.IsBusy || string.IsNullOrEmpty(session.Activity)) continue;

            working.Add($"{session.DisplayName}  ·  {session.Activity}");
        }

        // One agent at a time, taking turns. Two busy agents already overrun
        // 1080px at this type size - a session and the subagent inside it is
        // the ordinary case - and each of them in turn, whole, beats both of
        // them at once with the second one cut off mid-word forever. With one
        // agent working the index is 0 every tick, so nothing moves. The list
        // is rebuilt here, on the tick, so the agent on screen is current to
        // the second whether or not the turn just changed.
        Line.Text = working.Count == 0 ? string.Empty : working[slot % working.Count];
        Visibility = Line.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
    }
}
