using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.ComponentModel;
using System.Globalization;
using System.Linq;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media.Animation;

namespace ClockWall;

/// <summary>
/// The live roster of Claude Code agents running on this machine.
///
/// Self-contained: it owns a <see cref="SessionWatcher"/>, starts it when the
/// control loads and stops it when the control unloads, so a host only has to
/// place <c>&lt;local:AgentListPanel /&gt;</c> in its layout. A host that wants
/// the same data for its own chrome should read <see cref="Sessions"/> rather
/// than spinning up a second watcher.
///
/// The code-behind owns exactly three things that XAML cannot express:
/// fitting a whole number of cards into whatever height the host gives us,
/// the busy pulse (started and stopped per row, including on recycle), and the
/// header count. Everything visual - every brush, size and style - stays in
/// XAML against the locked theme resources.
/// </summary>
public sealed partial class AgentListPanel : UserControl
{
    // Card metrics mirror Themes/Theme.xaml (AgentCardMinHeight / AgentCardGutter).
    // The gutter is the ListViewItem's bottom margin from AgentListViewItemStyle.
    private const double CardGutter = 16d;
    private const double CardMinHeight = 150d;

    // Cards grow into leftover space so the list never trails off into a band of
    // dead pixels, but only so far - one lone agent should not become a poster.
    private const double CardMaxHeight = 190d;

    /// <summary>
    /// The list's vertical BUDGET in design pixels - the most the roster may
    /// ever take out of the 1080x1920 canvas, not the space it is handed.
    ///
    /// The list row is Auto-sized, so the control shrinks to its cards and the
    /// host gives the leftover height to the hero. Fitting therefore has to
    /// solve against a fixed number rather than ActualHeight, or the two would
    /// chase each other. 920 is the worst case that still balances: five cards
    /// at 171px plus four 16px gutters = 919, and with the header, the footer
    /// and their spacing the panel still clears the hero and both insets.
    /// </summary>
    private const double ListBudgetHeight = 920d;

    private readonly SessionWatcher _watcher;
    private double _rowHeight = CardMinHeight;

    public AgentListPanel()
    {
        // Constructed before InitializeComponent so the x:Bind on ItemsSource
        // has a collection to latch onto.
        _watcher = new SessionWatcher(DispatcherQueue);

        InitializeComponent();

        WatchPathText.Text = "Watching  " + _watcher.SessionsDirectory;

        Sessions.CollectionChanged += OnSessionsCollectionChanged;
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    /// <summary>The watcher backing this panel, for a host that needs the same
    /// live data (a count in the hero, say) without starting a second one.</summary>
    public SessionWatcher Watcher => _watcher;

    /// <summary>Live, sorted collection of running agent sessions.</summary>
    public ObservableCollection<AgentSession> Sessions => _watcher.Sessions;

    // ------------------------------------------------------------------
    // Lifetime
    // ------------------------------------------------------------------

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        SubscribeAll();
        _watcher.Start();
        Relayout();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _watcher.Stop();
        foreach (var session in Sessions)
            session.PropertyChanged -= OnSessionPropertyChanged;
    }

    private void SubscribeAll()
    {
        foreach (var session in Sessions)
        {
            session.PropertyChanged -= OnSessionPropertyChanged;
            session.PropertyChanged += OnSessionPropertyChanged;
        }
    }

    private void OnSessionsCollectionChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.OldItems is not null)
        {
            foreach (AgentSession session in e.OldItems)
                session.PropertyChanged -= OnSessionPropertyChanged;
        }

        if (e.NewItems is not null)
        {
            foreach (AgentSession session in e.NewItems)
            {
                // A Move reports the item as both old and new; the paired
                // detach/attach keeps it subscribed exactly once.
                session.PropertyChanged -= OnSessionPropertyChanged;
                session.PropertyChanged += OnSessionPropertyChanged;
            }
        }

        if (e.Action == NotifyCollectionChangedAction.Reset)
            SubscribeAll();

        Relayout();
    }

    /// <summary>
    /// A status flip does not move the collection when it is the only session,
    /// so the header count and the pulse are refreshed from the item itself.
    /// Uptime ticks (Uptime / SinceStatusChange) arrive here every second too
    /// and are deliberately ignored - x:Bind already re-renders those.
    /// </summary>
    private void OnSessionPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(AgentSession.Status)) return;

        UpdateSummary();

        if (sender is AgentSession session &&
            AgentListView.ContainerFromItem(session) is SelectorItem container)
        {
            ApplyPulse(container, session);
        }
    }

    // ------------------------------------------------------------------
    // Fitting: whole cards only, and an honest count of what did not fit
    // ------------------------------------------------------------------

    private void Relayout()
    {
        var count = Sessions.Count;

        EmptyState.Visibility = count == 0 ? Visibility.Visible : Visibility.Collapsed;
        AgentListView.Visibility = count == 0 ? Visibility.Collapsed : Visibility.Visible;

        UpdateSummary();

        if (count == 0)
        {
            OverflowIndicator.Visibility = Visibility.Collapsed;
            return;
        }

        const double available = ListBudgetHeight;

        // Whole cards only - a half-clipped card at the fold looks like a bug,
        // not an affordance.
        var capacity = Math.Max(1, (int)((available + CardGutter) / (CardMinHeight + CardGutter)));
        var shown = Math.Min(capacity, count);
        var rowHeight = Math.Clamp((available + CardGutter) / shown - CardGutter, CardMinHeight, CardMaxHeight);

        if (Math.Abs(rowHeight - _rowHeight) > 0.5)
        {
            _rowHeight = rowHeight;
            foreach (var child in AgentListView.ItemsPanelRoot?.Children ?? Enumerable.Empty<UIElement>())
            {
                if (child is FrameworkElement item) item.Height = _rowHeight;
            }
        }

        var listHeight = shown * (_rowHeight + CardGutter) - CardGutter;
        if (double.IsNaN(AgentListView.Height) || Math.Abs(AgentListView.Height - listHeight) > 0.5)
            AgentListView.Height = listHeight;

        var hidden = count - shown;
        OverflowIndicator.Visibility = hidden > 0 ? Visibility.Visible : Visibility.Collapsed;
        if (hidden > 0)
            OverflowText.Text = hidden == 1 ? "1 MORE AGENT" : $"{hidden} MORE AGENTS";
    }

    private void UpdateSummary()
    {
        var count = Sessions.Count;
        if (count == 0)
        {
            SummaryText.Text = string.Empty;
            return;
        }

        var busy = Sessions.Count(s => s.IsBusy);
        SummaryText.Text = busy > 0 ? $"{count} RUNNING  ·  {busy} BUSY" : $"{count} RUNNING";
    }

    // ------------------------------------------------------------------
    // Busy pulse
    // ------------------------------------------------------------------

    private void OnContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        var container = args.ItemContainer;
        if (container is null) return;

        if (args.InRecycleQueue)
        {
            // Never leave an animation running on a container in the recycle
            // pool - it would keep ticking and then bleed onto the next agent.
            StopPulse(container);
            return;
        }

        container.Height = _rowHeight;

        if (args.Item is AgentSession session)
            ApplyPulse(container, session);
    }

    /// <summary>
    /// A slow opacity breath on the busy dot: ~3.6s round trip, eased, bottoming
    /// out at 0.28 rather than 0. It is legible as motion from across a room and
    /// completely uninteresting up close, which is the point on a panel that is
    /// lit all day. Opacity animates on the composition thread, so this costs
    /// nothing on the UI thread and needs no dependent-animation opt-in.
    /// </summary>
    private static Storyboard CreatePulse(DependencyObject target)
    {
        var fade = new DoubleAnimation
        {
            From = 1.0,
            To = 0.28,
            Duration = new Duration(TimeSpan.FromMilliseconds(1800)),
            AutoReverse = true,
            RepeatBehavior = RepeatBehavior.Forever,
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
        };

        Storyboard.SetTarget(fade, target);
        Storyboard.SetTargetProperty(fade, "Opacity");

        var storyboard = new Storyboard();
        storyboard.Children.Add(fade);
        return storyboard;
    }

    private static void ApplyPulse(SelectorItem container, AgentSession session)
    {
        if (container.ContentTemplateRoot is not FrameworkElement root) return;
        if (root.FindName("BusyDot") is not UIElement dot) return;

        // Cached on the container, which outlives the item it is showing.
        if (container.Tag is not Storyboard pulse)
        {
            pulse = CreatePulse(dot);
            container.Tag = pulse;
        }

        if (session.IsBusy)
        {
            if (pulse.GetCurrentState() == ClockState.Stopped) pulse.Begin();
        }
        else
        {
            pulse.Stop();
            dot.Opacity = 1.0;
        }
    }

    private static void StopPulse(SelectorItem container)
    {
        if (container.Tag is not Storyboard pulse) return;
        pulse.Stop();

        if (container.ContentTemplateRoot is FrameworkElement root &&
            root.FindName("BusyDot") is UIElement dot)
        {
            dot.Opacity = 1.0;
        }
    }

    // ------------------------------------------------------------------
    // x:Bind function bindings (public + static so the generated code can
    // reach them; each re-evaluates when its argument path notifies)
    // ------------------------------------------------------------------

    public static Visibility WhenBusy(string status) => Vis(IsBusy(status));

    public static Visibility WhenIdle(string status) => Vis(IsIdle(status));

    public static Visibility WhenOther(string status) => Vis(!IsBusy(status) && !IsIdle(status));

    /// <summary>Label for a status the session file reports that we have no
    /// dedicated pill for - shown verbatim rather than swallowed.</summary>
    public static string OtherLabel(string status) =>
        string.IsNullOrWhiteSpace(status) ? "UNKNOWN" : status.Trim().ToUpperInvariant();

    /// <summary>Caption over the "how long in this state" figure.</summary>
    public static string StateCaption(string status) =>
        IsBusy(status) ? "BUSY FOR" : IsIdle(status) ? "IDLE FOR" : "IN STATE";

    /// <summary>Coarse, glanceable duration - two units at most, never a
    /// full timestamp. "3d 4h", "2h 07m", "6m 31s", "12s".</summary>
    public static string Duration(TimeSpan value)
    {
        if (value < TimeSpan.Zero) value = TimeSpan.Zero;

        if (value.TotalDays >= 1) return $"{(int)value.TotalDays}d {value.Hours}h";
        if (value.TotalHours >= 1) return $"{(int)value.TotalHours}h {value.Minutes:00}m";
        if (value.TotalMinutes >= 1) return $"{value.Minutes}m {value.Seconds:00}s";
        return $"{value.Seconds}s";
    }

    /// <summary>Secondary identity line: "Clock · interactive". Kind rides here
    /// rather than in the meta line because it is what separates a session you
    /// are driving from one an agent spawned.</summary>
    public static string ProjectLine(string projectName, string kind)
    {
        var project = (projectName ?? string.Empty).Trim();
        var sessionKind = (kind ?? string.Empty).Trim();

        if (project.Length == 0) return sessionKind;
        if (sessionKind.Length == 0) return project;
        return project + "  ·  " + sessionKind;
    }

    /// <summary>The quiet provenance line: "v2.1.247 · pid 1364".</summary>
    public static string MetaLine(string version, int pid)
    {
        var pidText = "pid " + pid.ToString(CultureInfo.InvariantCulture);
        return string.IsNullOrWhiteSpace(version) ? pidText : "v" + version.Trim() + "  ·  " + pidText;
    }

    private static bool IsBusy(string status) => string.Equals(status, "busy", StringComparison.OrdinalIgnoreCase);

    private static bool IsIdle(string status) => string.Equals(status, "idle", StringComparison.OrdinalIgnoreCase);

    private static Visibility Vis(bool value) => value ? Visibility.Visible : Visibility.Collapsed;
}
