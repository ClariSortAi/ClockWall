using System.Text;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Windows.Foundation;

namespace ClockWall;

/// <summary>
/// The band between the date and the AGENTS rule: one line, scrolling right to
/// left, naming what every running agent is doing right now - the tool it last
/// called and a short hint at what it called it on.
///
/// It renders <see cref="AgentSession.Activity"/>, which the existing
/// transcript follower already produces; this control adds no reading of its
/// own. Give it the roster's live collection with <see cref="Attach"/>.
///
/// With nothing to say it collapses, which hands its height straight back to
/// the roster (MainWindow.PushRosterBudget). The "no agents" case belongs to
/// the agent list's own empty state, not to a blank strip above it.
/// </summary>
public sealed partial class ActivityTicker : UserControl
{
    /// <summary>Scroll speed in design pixels per second. This is read from
    /// across a room, all day: fast is unreadable and irritating. At this rate a
    /// word takes about 24 seconds to cross the 968px-wide band.</summary>
    private const double PixelsPerSecond = 40d;

    /// <summary>Between agents. Wide enough that two agents never read as one
    /// sentence.</summary>
    private const string Separator = "     ●     ";

    private readonly Storyboard _scroll = new();
    private readonly DoubleAnimation _slide = new();

    private DispatcherQueueTimer? _timer;
    private IReadOnlyList<AgentSession>? _sessions;
    private string _pending = string.Empty;
    private bool _scrolling;

    public ActivityTicker()
    {
        InitializeComponent();

        Storyboard.SetTarget(_slide, Line);
        Storyboard.SetTargetProperty(_slide, "(UIElement.RenderTransform).(TranslateTransform.X)");
        _scroll.Children.Add(_slide);

        // One pass per Begin, relaunched here, rather than RepeatBehavior
        // Forever: the loop seam is then the ONE moment the text is off screen,
        // which is where a change of text has to land if the line is not to
        // snap back to the right edge every time a busy agent calls a tool.
        // The guard is not paranoia: Stop() is documented differently across
        // XAML stacks, and a Stop that raised Completed would re-enter
        // StartPass forever. StartPass clears the flag before it stops.
        _scroll.Completed += (_, _) => { if (_scrolling) StartPass(); };

        // The band's width is only known after layout, and the animation is
        // expressed in it, so a resize has to re-arm. It fires once in practice
        // (the design canvas is a fixed 1080 wide).
        Track.SizeChanged += (_, _) =>
        {
            Track.Clip = new RectangleGeometry
            {
                Rect = new Rect(0, 0, Track.ActualWidth, Track.ActualHeight),
            };
            if (!_scrolling) StartPass();
        };

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
        // Refresh is a string compare over at most a handful of sessions and
        // does nothing at all when the text has not changed, and the underlying
        // data only moves every 5s anyway. If the roster ever grows to hundreds
        // of sessions, swap this for those two subscriptions.
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

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _timer?.Stop();
        _scrolling = false;
        _scroll.Stop();
    }

    /// <summary>Recomposes the line. New text is held until the current pass
    /// runs off the left edge - a mid-flight swap is the one thing that reads
    /// as a glitch on a wall, and a busy agent changes tool every few seconds.
    /// A tick that finds nothing new does nothing at all.</summary>
    private void Refresh()
    {
        var builder = new StringBuilder();

        foreach (var session in _sessions ?? Array.Empty<AgentSession>())
        {
            // No activity yet means nothing to say about it - printing the name
            // alone would leave a dangling separator on the wall.
            if (string.IsNullOrEmpty(session.Activity)) continue;

            if (builder.Length > 0) builder.Append(Separator);
            builder.Append(session.DisplayName).Append("  ·  ").Append(session.Activity);
        }

        var text = builder.ToString();
        if (text == _pending) return;

        _pending = text;
        if (!_scrolling) StartPass();
    }

    /// <summary>Puts the latest text on screen and runs it once, right to left.
    /// Called at every loop seam, so the text shown is never more than one pass
    /// old.</summary>
    private void StartPass()
    {
        _scrolling = false;
        _scroll.Stop();

        Line.Text = _pending;
        Visibility = _pending.Length == 0 ? Visibility.Collapsed : Visibility.Visible;

        if (_pending.Length == 0 || Track.ActualWidth <= 0) return;

        // Canvas children are measured against infinity, so this is the text's
        // natural width - but only after an explicit measure, since the text
        // was assigned after the last layout pass.
        Line.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
        var width = Line.DesiredSize.Width;

        _slide.From = Track.ActualWidth;
        _slide.To = -width;
        _slide.Duration = TimeSpan.FromSeconds((Track.ActualWidth + width) / PixelsPerSecond);

        _scrolling = true;
        _scroll.Begin();
    }
}
