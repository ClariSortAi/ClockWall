using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.ComponentModel;
using System.Globalization;
using System.Linq;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media.Animation;
using Windows.UI.ViewManagement;

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
public sealed partial class AgentListPanel : UserControl, IDisposable
{
    // Card metrics mirror Themes/Theme.xaml (AgentCardMinHeight / AgentCardGutter).
    // The gutter is the ListViewItem's bottom margin from AgentListViewItemStyle.
    private const double CardGutter = 16d;
    private const double CardMinHeight = 150d;

    // Cards grow into leftover space so the list never trails off into a band of
    // dead pixels, but only so far - one lone agent should not become a poster.
    private const double CardMaxHeight = 190d;

    // A subagent row is one line of text, not a card - it has to cost a small
    // fraction of a card or a session with a dozen of them owns the whole panel.
    private const double ChildRowHeight = 48d;

    private readonly SessionWatcher _watcher;
    private double _rowHeight = CardMinHeight;
    private double _listBudget = 920d;

    /// <summary>How many subagent rows the measured budget currently affords.
    /// The watcher is told the same number and stops producing more, but it
    /// learns it one scan late, so the view enforces it too - see
    /// <see cref="IsOverBudget"/>.</summary>
    private int _childBudget = int.MaxValue;

    /// <summary>
    /// The panel's vertical budget in design pixels - what the host has left
    /// over once every other band on its canvas has taken what it wants.
    ///
    /// The panel is CONTENT-sized (the host hands the slack to the hero, see
    /// MainWindow.xaml), so it cannot measure this for itself: its own height
    /// is the answer, and reading ActualHeight back would just return whatever
    /// the last <see cref="Relayout"/> set. The host can measure it without
    /// that circularity - every other band's desired height is independent of
    /// the roster - so the host pushes it in here. 920 is only what the very
    /// first layout pass fits against, before any measurement exists.
    /// </summary>
    public double ListBudget
    {
        get => _listBudget;
        set
        {
            if (double.IsNaN(value) || value <= CardMinHeight || Math.Abs(value - _listBudget) < 0.5) return;
            _listBudget = value;
            Relayout();
        }
    }

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

        // Our own height moving means the chrome around the list moved (the
        // overflow footer appearing, say), so the fit is stale. Relayout only
        // assigns when a number actually changes, so this settles in one pass.
        SizeChanged += (_, _) => Relayout();
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
        _watcher.Refreshed += OnWatcherRefreshed;
        _watcher.Start();
        Relayout();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        _watcher.Stop();
        _watcher.Refreshed -= OnWatcherRefreshed;
        foreach (var session in Sessions)
            session.PropertyChanged -= OnSessionPropertyChanged;
    }

    /// <summary>The day totals in the header move without any card moving, so
    /// the summary is refreshed on every scan, not just collection changes.</summary>
    private void OnWatcherRefreshed() => UpdateSummary();

    /// <summary>Releases the watcher we own. Unloaded only stops it - the host
    /// disposes on the way down, by sweeping its children for IDisposable.</summary>
    public void Dispose() => _watcher.Dispose();

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

        // Measured, not assumed: everything of ours that is NOT the list host
        // is the header, the overflow footer and their row spacing, so what is
        // left of the budget is what the cards may have.
        var chrome = Math.Max(0d, ActualHeight - ListHost.ActualHeight);
        var available = Math.Max(CardMinHeight, _listBudget - chrome);

        var parents = 0;
        var liveChildren = 0;
        foreach (var session in Sessions)
        {
            if (session.IsChild) continue;
            parents++;
            liveChildren += session.SubagentLiveCount;
        }

        // SESSIONS ARE THE BACKBONE, so they are budgeted first, at minimum
        // height: sessions are few and each one matters, subagents are many and
        // individually disposable, and a session that cannot show its children
        // still says how many it has. So childRoom is what is left when every
        // session that physically fits has its card - space no CARD could use -
        // and a burst of subagents can never cost a session its row.
        var parentCapacity = Math.Max(1, (int)((available + CardGutter) / (CardMinHeight + CardGutter)));
        var parentsFit = Math.Min(parents, parentCapacity);
        var childRoom = available - (parentsFit * (CardMinHeight + CardGutter) - CardGutter);
        var childCapacity = Math.Max(0, (int)(childRoom / (ChildRowHeight + CardGutter)));
        _childBudget = childCapacity;

        // What the NEXT scan is allowed to open and parse. Liveness is a stat
        // and is done for every subagent; the transcript is only read for the
        // handful of rows that will be rendered.
        _watcher.MaxChildren = childCapacity;

        // Whole rows only - a half-clipped card at the fold looks like a bug,
        // not an affordance - and a prefix, because a ListView cannot skip a row
        // in the middle. Walking the collection rather than dividing by a row
        // height is what lets the two row sizes coexist.
        var shown = 0;
        var childrenShown = 0;
        var used = 0d;
        foreach (var session in Sessions)
        {
            // A child the budget cannot afford is COLLAPSED, not skipped: the
            // watcher only learns the number one scan late, and a child left in
            // the layout in the meantime would cost a SESSION its row - the one
            // thing a burst of subagents must never do.
            if (session.IsChild && childrenShown >= childCapacity) continue;

            var next = used
                + (shown == 0 ? 0d : CardGutter)
                + (session.IsChild ? ChildRowHeight : CardMinHeight);

            if (shown > 0 && next > available) break;

            used = next;
            shown++;
            if (session.IsChild) childrenShown++;
        }

        // Cards grow into whatever is still spare so the list does not trail off
        // into a band of dead pixels; child rows stay one line tall.
        var cardsShown = shown - childrenShown;
        var slack = cardsShown > 0 ? Math.Max(0d, available - used) / cardsShown : 0d;
        var rowHeight = Math.Clamp(CardMinHeight + slack, CardMinHeight, CardMaxHeight);

        _rowHeight = rowHeight;
        foreach (var child in AgentListView.ItemsPanelRoot?.Children ?? Enumerable.Empty<UIElement>())
        {
            if (child is SelectorItem item && item.Content is AgentSession session)
                ApplyRowMetrics(item, session);
        }

        var listHeight = used + cardsShown * (_rowHeight - CardMinHeight);
        if (double.IsNaN(AgentListView.Height) || Math.Abs(AgentListView.Height - listHeight) > 0.5)
            AgentListView.Height = listHeight;

        // Both kinds of remainder are announced. Silent truncation is the actual
        // failure mode on a wall: what is not on screen has to be said.
        var hiddenParents = parents - cardsShown;
        var hiddenChildren = Math.Max(0, liveChildren - childrenShown);

        OverflowIndicator.Visibility = hiddenParents > 0 || hiddenChildren > 0
            ? Visibility.Visible
            : Visibility.Collapsed;

        if (hiddenParents > 0 || hiddenChildren > 0)
            OverflowText.Text = OverflowLine(hiddenParents, hiddenChildren);
    }

    /// <summary>Sizes one row for what it is - card, subagent line, or a
    /// subagent the budget cannot afford, which takes no space at all
    /// (Collapsed, so its gutter goes with it).</summary>
    private void ApplyRowMetrics(SelectorItem container, AgentSession session)
    {
        var affordable = !IsOverBudget(session);
        container.Visibility = affordable ? Visibility.Visible : Visibility.Collapsed;
        if (affordable) container.Height = session.IsChild ? ChildRowHeight : _rowHeight;
    }

    /// <summary>True for a subagent past the row budget. Collection order is
    /// the priority order - the watcher hands over the most recently active
    /// children first, under the sessions they belong to.</summary>
    private bool IsOverBudget(AgentSession session)
    {
        if (!session.IsChild) return false;

        var seen = 0;
        foreach (var candidate in Sessions)
        {
            if (ReferenceEquals(candidate, session)) return seen >= _childBudget;
            if (candidate.IsChild) seen++;
        }

        return false;
    }

    private static string OverflowLine(int sessions, int subagents)
    {
        if (sessions > 0 && subagents > 0)
            return $"{sessions} MORE {(sessions == 1 ? "SESSION" : "SESSIONS")}  ·  {subagents} MORE {(subagents == 1 ? "SUBAGENT" : "SUBAGENTS")}";

        if (sessions > 0)
            return sessions == 1 ? "1 MORE AGENT" : $"{sessions} MORE AGENTS";

        return subagents == 1 ? "1 MORE SUBAGENT" : $"{subagents} MORE SUBAGENTS";
    }

    /// <summary>
    /// Sessions and subagents are counted separately and named separately: one
    /// number covering both would be a count of nothing in particular, and the
    /// subagent figure is the LIVE one, including the children that did not fit.
    /// A session blocked on the user leads the line, and the machine's day
    /// totals close it - the one part that survives an empty roster, because
    /// money spent this morning is still spent after the last session exits.
    /// </summary>
    private void UpdateSummary()
    {
        var parents = 0;
        var busy = 0;
        var waiting = 0;
        var live = 0;

        foreach (var session in Sessions)
        {
            if (session.IsChild) continue;
            parents++;
            if (session.IsBusy) busy++;
            if (session.NeedsAttention) waiting++;
            live += session.SubagentLiveCount;
        }

        var parts = new List<string>(4);
        if (waiting > 0) parts.Add($"{waiting} NEEDS YOU");
        if (parents > 0)
        {
            parts.Add($"{parents} RUNNING");
            if (busy > 0) parts.Add($"{busy} BUSY");
            if (live > 0) parts.Add($"{live} {(live == 1 ? "SUBAGENT" : "SUBAGENTS")}");
        }

        SummaryText.Text = string.Join("  ·  ", parts);

        BurnText.Text = _watcher.TodayOutputTokens > 0
            ? $"TODAY  {TokenCount(_watcher.TodayOutputTokens)}  ·  {Dollars(_watcher.TodayDollars)}"
            : string.Empty;
    }

    /// <summary>"~$3.40" under ten dollars, "~$27" over - and always "~",
    /// because the figure is priced from a hand-copied rate table.</summary>
    public static string Dollars(double value) =>
        "~$" + value.ToString(value < 10 ? "0.00" : "0", CultureInfo.InvariantCulture);

    // ------------------------------------------------------------------
    // Busy pulse
    // ------------------------------------------------------------------

    /// <summary>
    /// The user's "Animation effects" switch (Settings &gt; Accessibility &gt;
    /// Visual effects), which the two looping storyboards below are gated on.
    ///
    /// One instance for the life of the process: ACTIVATING a UISettings is
    /// WinRT work and this is read on every roster scan, but the property read
    /// off an existing instance goes to the live system setting, so a cached
    /// instance is cheaper and no staler than a fresh one.
    /// </summary>
    private static readonly UISettings SystemUISettings = new UISettings();

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

        if (args.Item is not AgentSession session) return;

        ApplyRowMetrics(container, session);
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

    /// <summary>
    /// The needs-you flash: the same composition-thread opacity trick as the
    /// busy breath, but faster and deeper - 700ms down to 0.15 - because this
    /// one is an alarm and the breath is furniture. Cached on the glow element
    /// itself, so the container's Tag stays the busy pulse's.
    /// </summary>
    private static Storyboard CreateFlash(DependencyObject target)
    {
        var fade = new DoubleAnimation
        {
            From = 1.0,
            To = 0.15,
            Duration = new Duration(TimeSpan.FromMilliseconds(700)),
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
        // A subagent row has no status pill - the dot in the collapsed half of
        // the template is not its own, and animating it would be invisible work.
        if (session.IsChild) return;

        if (container.ContentTemplateRoot is not FrameworkElement root) return;
        if (root.FindName("BusyDot") is not UIElement dot) return;

        // These two are the only FOREVER animations on the wall, and a forever
        // animation in someone's field of vision all day is precisely what the
        // OS animation-effects switch is for, so it is a hard gate: with it off
        // both take the same path as "not busy" / "not waiting" - stopped, at
        // full opacity. Nothing is lost, because the motion was only ever the
        // emphasis: the dot still sits beside the word BUSY and the glow is
        // still drawn around the card. Read per call rather than through
        // AnimationsEnabledChanged - ApplyPulse re-runs on every roster scan,
        // so a flipped setting heals itself within a poll, the same mechanism
        // the rest of the app already leans on for staying honest for days.
        var animate = SystemUISettings.AnimationsEnabled;

        // Cached on the container, which outlives the item it is showing.
        if (container.Tag is not Storyboard pulse)
        {
            pulse = CreatePulse(dot);
            container.Tag = pulse;
        }

        if (session.IsBusy && animate)
        {
            if (pulse.GetCurrentState() == ClockState.Stopped) pulse.Begin();
        }
        else
        {
            pulse.Stop();
            dot.Opacity = 1.0;
        }

        // The waiting flash rides the same recycle-safe path. When the session
        // is fresh-idle instead, the glow is visible but STILL - the visibility
        // is x:Bind's job, only the motion is decided here.
        if (root.FindName("AttentionGlow") is FrameworkElement glow)
        {
            if (glow.Tag is not Storyboard flash)
            {
                flash = CreateFlash(glow);
                glow.Tag = flash;
            }

            if (session.NeedsAttention && animate)
            {
                if (flash.GetCurrentState() == ClockState.Stopped) flash.Begin();
            }
            else
            {
                flash.Stop();
                glow.Opacity = 1.0;
            }
        }
    }

    private static void StopPulse(SelectorItem container)
    {
        if (container.Tag is not Storyboard pulse) return;
        pulse.Stop();

        if (container.ContentTemplateRoot is not FrameworkElement root) return;

        if (root.FindName("BusyDot") is UIElement dot)
        {
            dot.Opacity = 1.0;
        }

        if (root.FindName("AttentionGlow") is FrameworkElement glow)
        {
            if (glow.Tag is Storyboard flash) flash.Stop();
            glow.Opacity = 1.0;
        }
    }

    // ------------------------------------------------------------------
    // x:Bind function bindings (public + static so the generated code can
    // reach them; each re-evaluates when its argument path notifies)
    // ------------------------------------------------------------------

    public static Visibility WhenBusy(string status) => Vis(IsBusy(status));

    public static Visibility WhenIdle(string status) => Vis(IsIdle(status));

    public static Visibility WhenOther(string status) => Vis(!IsBusy(status) && !IsIdle(status));

    /// <summary>The two halves of the row template: a session gets the card, a
    /// subagent gets the indented line.</summary>
    public static Visibility WhenParent(bool isChild) => Vis(!isChild);

    public static Visibility WhenChild(bool isChild) => Vis(isChild);

    /// <summary>The subagent row's own figures: "18%  ·  12k  ·  opus-5". Read
    /// from its transcript by the same follower the sessions use.</summary>
    public static string ChildStats(int contextTokens, long outputTokens, string model)
    {
        var line = ContextShare(contextTokens) + "  ·  " + TokenCount(outputTokens);
        var shortModel = ShortModel(model);
        return shortModel.Length == 0 ? line : line + "  ·  " + shortModel;
    }

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

    /// <summary>How full the context window is, as a percentage: "23%".</summary>
    public static string ContextShare(int contextTokens)
    {
        if (contextTokens <= 0) return "--";
        return Math.Round(ContextFraction(contextTokens) * 100).ToString("0", CultureInfo.InvariantCulture) + "%";
    }

    /// <summary>Context held as a fraction of the window, 0 when unknown.</summary>
    private static double ContextFraction(int contextTokens)
    {
        if (contextTokens <= 0) return 0;

        // ponytail: the transcript never records the context WINDOW, and
        // message.model reads "claude-opus-5" for the 200k and the 1M build
        // alike, so the window is inferred from the traffic: a session holding
        // more than 200k can only be on the 1M one. A session on the 1M build
        // that has not passed 200k yet therefore reads against 200k and shows
        // a percentage that is too high. Upgrade path: take the window from
        // the session file, the day it starts recording one.
        var window = contextTokens > 200_000 ? 1_000_000d : 200_000d;
        return contextTokens / window;
    }

    // The CONTEXT figure's three registers - calm, caution from 75%, critical
    // from 90%, where auto-compact lives. Exactly one is visible at a time.
    public static Visibility WhenContextCalm(int contextTokens) => Vis(ContextFraction(contextTokens) < 0.75);

    public static Visibility WhenContextCaution(int contextTokens)
    {
        var fraction = ContextFraction(contextTokens);
        return Vis(fraction >= 0.75 && fraction < 0.9);
    }

    public static Visibility WhenContextCritical(int contextTokens) => Vis(ContextFraction(contextTokens) >= 0.9);

    /// <summary>How long a finished session keeps its steady glow: long enough
    /// to survive a walk back to the room, short enough that "recently" is
    /// still true.</summary>
    private static readonly TimeSpan FreshFinishWindow = TimeSpan.FromMinutes(3);

    /// <summary>The attention overlay: a waiting session (blocked on the user)
    /// or one that went quiet in the last few minutes. Never a subagent row.
    /// Re-evaluated every second by the SinceStatusChange tick, which is what
    /// ages the finished-glow out with no timer of its own.</summary>
    public static Visibility WhenAttention(bool isChild, string status, TimeSpan sinceStatusChange) =>
        Vis(!isChild && (IsWaiting(status)
            || (IsIdle(status) && sinceStatusChange < FreshFinishWindow)));

    private static bool IsWaiting(string status) => string.Equals(status, "waiting", StringComparison.OrdinalIgnoreCase);

    /// <summary>Tokens produced, abbreviated for a glance: "318k", "1.2M".</summary>
    public static string TokenCount(long tokens)
    {
        if (tokens <= 0) return "--";
        if (tokens >= 1_000_000) return (tokens / 1_000_000d).ToString("0.0", CultureInfo.InvariantCulture) + "M";
        if (tokens >= 1_000) return (tokens / 1_000).ToString(CultureInfo.InvariantCulture) + "k";
        return tokens.ToString(CultureInfo.InvariantCulture);
    }

    /// <summary>Output pace: "12 tok/s", "1.2k tok/s". EMPTY under half a
    /// token a second - the smoothing leaves a decaying tail behind a session
    /// that stopped, and the caller drops the whole segment rather than
    /// publish "0 tok/s" for the hours a parked session sits there.</summary>
    public static string TokenRate(double perSecond)
    {
        if (perSecond < 0.5) return string.Empty;
        var figure = perSecond >= 1_000
            ? (perSecond / 1_000d).ToString("0.0", CultureInfo.InvariantCulture) + "k"
            : perSecond.ToString("0", CultureInfo.InvariantCulture);
        return figure + " tok/s";
    }

    /// <summary>Tool-call pace: "0.4 tools/m", "6 tools/m". Keeps a decimal
    /// below 10 because the interesting range is small - the gap between one
    /// call a minute and four is most of what this figure has to say, and
    /// rounding both to "0" and "4" throws half of it away. Empty rule as
    /// <see cref="TokenRate"/>.</summary>
    public static string ToolRate(double perMinute)
    {
        if (perMinute < 0.1) return string.Empty;
        var figure = perMinute < 10
            ? perMinute.ToString("0.0", CultureInfo.InvariantCulture)
            : perMinute.ToString("0", CultureInfo.InvariantCulture);
        return figure + " tools/m";
    }

    /// <summary>The two pace figures joined, either half dropping out on its
    /// own, empty when the session is doing neither.</summary>
    private static string Pace(double tokensPerSecond, double toolsPerMinute)
    {
        var tokens = TokenRate(tokensPerSecond);
        var tools = ToolRate(toolsPerMinute);

        if (tokens.Length == 0) return tools;
        return tools.Length == 0 ? tokens : tokens + "  ·  " + tools;
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

    /// <summary>The line under the status pill: "3 of 12 subagents". The
    /// denominator counts every subagent this session has ever started, so "1 of
    /// 23" is one running now out of twenty-three it has been through.</summary>
    public static string SubagentTally(int live, int total) =>
        string.Create(CultureInfo.InvariantCulture, $"{live} of {total} subagents");

    public static Visibility WhenPositive(int value) => Vis(value > 0);

    /// <summary>The quiet provenance line, with pace on the end while there is
    /// any: "opus-5 · v2.1.247 · pid 1364 · 175 tok/s · 6 tools/m". Each piece
    /// drops out cleanly when it is missing.
    ///
    /// Pace rides HERE rather than in the stat row above because the row is
    /// full: a fifth and sixth column there cost the agent name its width, and
    /// "graniteai-website-98" trimmed to "granite..." is not a name - two
    /// different sessions render identically. The name is the one thing on this
    /// card that has to survive being read from across the room.</summary>
    public static string MetaLine(string model, string version, int pid, double tokensPerSecond, double toolsPerMinute)
    {
        var line = "pid " + pid.ToString(CultureInfo.InvariantCulture);
        if (!string.IsNullOrWhiteSpace(version)) line = "v" + version.Trim() + "  ·  " + line;

        var shortModel = ShortModel(model);
        if (shortModel.Length > 0) line = shortModel + "  ·  " + line;

        var pace = Pace(tokensPerSecond, toolsPerMinute);
        return pace.Length == 0 ? line : line + "  ·  " + pace;
    }

    /// <summary>"claude-opus-5" -&gt; "opus-5", "claude-haiku-4-5-20251001" -&gt;
    /// "haiku-4.5". Empty in, empty out - the meta line then omits it entirely
    /// rather than showing a stray separator.</summary>
    // ponytail: assumes today's family-first ids, "claude-<family>-<major>[-<minor>][-<datestamp>]".
    // A legacy id like "claude-3-5-sonnet-20241022" comes out as "3.5-sonnet". If those ever come
    // back, pick the family by matching known names instead of taking the first part.
    public static string ShortModel(string model)
    {
        var name = (model ?? string.Empty).Trim();
        if (name.StartsWith("claude-", StringComparison.OrdinalIgnoreCase)) name = name["claude-".Length..];

        // Drop a trailing "-20251001" release stamp.
        var stamp = name.LastIndexOf('-');
        if (stamp > 0 && name.Length - stamp == 9 && name[(stamp + 1)..].All(char.IsAsciiDigit))
            name = name[..stamp];

        // Family stays dash-joined, the version parts after it join with dots.
        var split = name.IndexOf('-');
        return split < 0 ? name : name[..(split + 1)] + name[(split + 1)..].Replace('-', '.');
    }

    private static bool IsBusy(string status) => string.Equals(status, "busy", StringComparison.OrdinalIgnoreCase);

    private static bool IsIdle(string status) => string.Equals(status, "idle", StringComparison.OrdinalIgnoreCase);

    private static Visibility Vis(bool value) => value ? Visibility.Visible : Visibility.Collapsed;
}
