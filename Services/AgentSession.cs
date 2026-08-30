using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace ClockWall;

/// <summary>
/// Live view-model for one running Claude Code agent session, sourced from a
/// "&lt;pid&gt;.json" file under "%USERPROFILE%\.claude\sessions".
///
/// Instances are long-lived: <see cref="SessionWatcher"/> keeps the same
/// <see cref="AgentSession"/> object alive across refresh cycles (keyed by
/// <see cref="SessionId"/>) and calls <see cref="UpdateFrom"/> to push new
/// field values onto it, so a WinUI ListView bound to it updates in place
/// instead of flickering / losing selection or animation state.
/// </summary>
public sealed class AgentSession : INotifyPropertyChanged
{
    private static readonly DateTime UnixEpochUtc = new(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    public event PropertyChangedEventHandler? PropertyChanged;

    // Identity - set once at construction, never reassigned. These four are
    // deliberately absent from UpdateFrom: a given SessionId is a child (or is
    // not) for its whole life, so there is nothing to copy forward.
    public int Pid { get; }
    public string SessionId { get; }

    /// <summary>True when this row is a SUBAGENT - an agent running INSIDE a
    /// parent session's process. It has no pid and no session file of its own;
    /// it is discovered from the transcript its parent writes for it. The view
    /// renders these as indented child rows under <see cref="ParentSessionId"/>.</summary>
    public bool IsChild { get; }

    /// <summary>SessionId of the session that spawned this subagent, empty for
    /// a top-level session.</summary>
    public string ParentSessionId { get; }

    private string _name = string.Empty;
    public string Name
    {
        get => _name;
        private set
        {
            if (SetField(ref _name, value ?? string.Empty))
                OnPropertyChanged(nameof(DisplayName));
        }
    }

    private string _cwd = string.Empty;
    public string Cwd
    {
        get => _cwd;
        private set
        {
            if (SetField(ref _cwd, value ?? string.Empty))
                ProjectName = DeriveProjectName(_cwd);
        }
    }

    private string _projectName = string.Empty;
    public string ProjectName
    {
        get => _projectName;
        private set
        {
            if (SetField(ref _projectName, value ?? string.Empty))
                OnPropertyChanged(nameof(DisplayName));
        }
    }

    private string _status = string.Empty;
    public string Status
    {
        get => _status;
        private set
        {
            if (SetField(ref _status, value ?? string.Empty))
            {
                OnPropertyChanged(nameof(IsBusy));
                OnPropertyChanged(nameof(NeedsAttention));
                OnPropertyChanged(nameof(IsIdle));
            }
        }
    }

    /// <summary>True when Status is "busy" (case-insensitive). Anything else
    /// (notably "idle") is treated as not-busy.</summary>
    public bool IsBusy => string.Equals(Status, "busy", StringComparison.OrdinalIgnoreCase);

    /// <summary>True when Status is "waiting" - blocked on the user (a
    /// permission prompt or a question), as opposed to resting at "idle".</summary>
    public bool NeedsAttention => string.Equals(Status, "waiting", StringComparison.OrdinalIgnoreCase);

    /// <summary>True when Status is "idle" - parked between turns, running
    /// nothing. The only status that sinks a session BELOW the fold, so it is
    /// asked for explicitly rather than inferred from "not busy": "shell" is
    /// also not busy, and a session running a shell command is working.</summary>
    public bool IsIdle => string.Equals(Status, "idle", StringComparison.OrdinalIgnoreCase);

    private string _version = string.Empty;
    public string Version { get => _version; private set => SetField(ref _version, value ?? string.Empty); }

    private string _kind = string.Empty;
    public string Kind { get => _kind; private set => SetField(ref _kind, value ?? string.Empty); }

    private string _entrypoint = string.Empty;
    public string Entrypoint { get => _entrypoint; private set => SetField(ref _entrypoint, value ?? string.Empty); }

    /// <summary>The small context window - and the line that PROVES a session
    /// is not on it, since a 200k session cannot hold more than 200k.</summary>
    public const int SmallContextWindow = 200_000;

    /// <summary>The large context window: the only one we can ever establish,
    /// and only by watching a session exceed <see cref="SmallContextWindow"/>.</summary>
    public const int LargeContextWindow = 1_000_000;

    private int _contextTokens;
    /// <summary>Tokens in the prompt the model saw on this session's most
    /// recent turn - fresh input plus cache reads and writes. Read from the
    /// transcript by <see cref="TranscriptTokens"/>; 0 when it has none.</summary>
    public int ContextTokens
    {
        get => _contextTokens;
        private set
        {
            if (SetField(ref _contextTokens, value) && value > SmallContextWindow)
                ContextWindowKnown = true;
        }
    }

    private bool _contextWindowKnown;
    /// <summary>
    /// True once this session has PROVEN which context window it holds, which
    /// it can only do by exceeding <see cref="SmallContextWindow"/>.
    ///
    /// Nothing on disk records the window: the session file has no field for
    /// it, and the transcript writes "claude-opus-5" for the 200k build and
    /// the 1M build alike. So the answer is available in exactly one case - a
    /// session holding more than 200k is on the 1M build - and unavailable in
    /// every other, where the panel shows the raw figure rather than a
    /// percentage it would have to invent a denominator for.
    ///
    /// Latched, never cleared. An auto-compact drops the figure back under the
    /// line but does not move the session to a different build, and un-proving
    /// it would flip the readout between "24%" and "150k" every time the
    /// context breathed across 200k.
    /// </summary>
    public bool ContextWindowKnown { get => _contextWindowKnown; private set => SetField(ref _contextWindowKnown, value); }

    private long _outputTokens;
    /// <summary>Output tokens this session has produced since it started.</summary>
    public long OutputTokens { get => _outputTokens; private set => SetField(ref _outputTokens, value); }

    private long _toolCalls;
    /// <summary>Tool calls this session has made since it started, counted off
    /// the transcript by <see cref="TranscriptTokens"/>.</summary>
    public long ToolCalls { get => _toolCalls; private set => SetField(ref _toolCalls, value); }

    private double _tokensPerSecond;
    /// <summary>Output tokens per second, smoothed - see <see cref="SamplePace"/>.</summary>
    public double TokensPerSecond { get => _tokensPerSecond; private set => SetField(ref _tokensPerSecond, value); }

    private double _toolsPerMinute;
    /// <summary>Tool calls per minute, smoothed - see <see cref="SamplePace"/>.</summary>
    public double ToolsPerMinute { get => _toolsPerMinute; private set => SetField(ref _toolsPerMinute, value); }

    // Pace is measured on the LONG-LIVED instance: UpdateFrom hands us a
    // throwaway object built from this scan, so the previous reading has to
    // live here or there is nothing to subtract.
    private DateTime _paceSampledAt;
    private long _paceOutput;
    private long _paceTools;

    /// <summary>Shortest gap between two pace samples. A refresh can land 300ms
    /// after the last one (the watcher debounces file events), and a transcript
    /// is written in bursts - so a short window routinely divides one whole
    /// turn's tokens by a third of a second and reports a rate no session could
    /// sustain.</summary>
    private static readonly TimeSpan PaceWindow = TimeSpan.FromSeconds(2);

    /// <summary>EMA weight on the newest sample. High enough that a session
    /// waking up shows it within a couple of samples, low enough that the
    /// gap between two turns does not read as a stop.</summary>
    private const double PaceSmoothing = 0.4;

    private string _model = string.Empty;
    /// <summary>Raw model id of this session's most recent assistant turn, e.g.
    /// "claude-opus-5". Read from the transcript by <see cref="TranscriptTokens"/>;
    /// empty when it has none yet.</summary>
    public string Model { get => _model; private set => SetField(ref _model, value ?? string.Empty); }

    private string _activity = string.Empty;
    /// <summary>The last tool call this session made, already shortened for
    /// display ("Edit MainWindow.xaml.cs", "Bash git status", "SendMessage").
    /// Read from the transcript by <see cref="TranscriptTokens"/>; empty when
    /// the session has not called a tool yet.</summary>
    public string Activity { get => _activity; private set => SetField(ref _activity, value ?? string.Empty); }

    private int _subagentCount;
    /// <summary>How many subagents this session has spawned in its lifetime -
    /// one per transcript on disk, finished ones included. Counted by a
    /// directory listing, so it costs a stat rather than a parse.</summary>
    public int SubagentCount { get => _subagentCount; private set => SetField(ref _subagentCount, value); }

    private int _subagentLiveCount;
    /// <summary>How many of those subagents look like they are running right
    /// now. See SessionWatcher.SubagentLiveWindow - this is an mtime heuristic,
    /// not the pid check the session itself gets.</summary>
    public int SubagentLiveCount { get => _subagentLiveCount; private set => SetField(ref _subagentLiveCount, value); }

    public DateTime StartedAt { get; private set; }

    private DateTime _updatedAt;
    public DateTime UpdatedAt { get => _updatedAt; private set => SetField(ref _updatedAt, value); }

    private DateTime _statusUpdatedAt;
    public DateTime StatusUpdatedAt { get => _statusUpdatedAt; private set => SetField(ref _statusUpdatedAt, value); }

    private bool _isRunning;
    /// <summary>True when <see cref="SessionWatcher"/> most recently verified
    /// the pid is alive and its process start time is consistent with
    /// <see cref="StartedAt"/>. Sessions surfaced by SessionWatcher are
    /// always running (non-running ones are dropped from its collection),
    /// but the flag is kept for callers that hold a reference past that.</summary>
    public bool IsRunning { get => _isRunning; private set => SetField(ref _isRunning, value); }

    /// <summary>Wall-clock time since the session started. Recomputed from
    /// <see cref="DateTime.Now"/> on every read - call <see cref="RaiseTimeChanged"/>
    /// periodically from a UI timer to keep bound text current.</summary>
    public TimeSpan Uptime => Since(StartedAt);

    /// <summary>Wall-clock time since Status last changed.</summary>
    public TimeSpan SinceStatusChange => Since(StatusUpdatedAt);

    /// <summary>Best available label for the UI: session Name, else the
    /// project leaf folder, else a short session id, else the pid.</summary>
    public string DisplayName
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(Name)) return Name;
            if (!string.IsNullOrWhiteSpace(ProjectName)) return ProjectName;
            if (!string.IsNullOrWhiteSpace(SessionId))
                return SessionId.Length > 8 ? SessionId[..8] : SessionId;
            return $"pid {Pid}";
        }
    }

    public AgentSession(
        int pid,
        string sessionId,
        string name,
        string cwd,
        string status,
        string version,
        string kind,
        string entrypoint,
        DateTime startedAt,
        DateTime updatedAt,
        DateTime statusUpdatedAt,
        int contextTokens,
        long outputTokens,
        string model,
        string activity,
        bool isRunning,
        long toolCalls = 0,
        int subagentCount = 0,
        int subagentLiveCount = 0,
        bool isChild = false,
        string parentSessionId = "")
    {
        Pid = pid;
        SessionId = sessionId ?? string.Empty;
        IsChild = isChild;
        ParentSessionId = parentSessionId ?? string.Empty;
        _subagentCount = subagentCount;
        _subagentLiveCount = subagentLiveCount;
        StartedAt = startedAt;
        _name = name ?? string.Empty;
        _cwd = cwd ?? string.Empty;
        _projectName = DeriveProjectName(_cwd);
        _status = status ?? string.Empty;
        _version = version ?? string.Empty;
        _kind = kind ?? string.Empty;
        _entrypoint = entrypoint ?? string.Empty;
        _updatedAt = updatedAt;
        _statusUpdatedAt = statusUpdatedAt;
        _contextTokens = contextTokens;
        _contextWindowKnown = contextTokens > SmallContextWindow;
        _outputTokens = outputTokens;
        _model = model ?? string.Empty;
        _activity = activity ?? string.Empty;
        _isRunning = isRunning;
        _toolCalls = toolCalls;
    }

    /// <summary>
    /// Copies the mutable fields from a freshly parsed snapshot of the same
    /// logical session onto this instance, raising PropertyChanged only for
    /// what actually changed. Object identity is preserved so bound UI does
    /// not flicker or lose animation/selection state across refreshes.
    /// </summary>
    public void UpdateFrom(AgentSession fresh)
    {
        if (fresh is null) return;

        Name = fresh.Name;
        Cwd = fresh.Cwd;
        Status = fresh.Status;
        Version = fresh.Version;
        Kind = fresh.Kind;
        Entrypoint = fresh.Entrypoint;
        UpdatedAt = fresh.UpdatedAt;
        StatusUpdatedAt = fresh.StatusUpdatedAt;
        ContextTokens = fresh.ContextTokens;
        OutputTokens = fresh.OutputTokens;
        ToolCalls = fresh.ToolCalls;
        SamplePace(fresh.OutputTokens, fresh.ToolCalls);
        Model = fresh.Model;
        Activity = fresh.Activity;
        IsRunning = fresh.IsRunning;
        SubagentCount = fresh.SubagentCount;
        SubagentLiveCount = fresh.SubagentLiveCount;

        if (fresh.StartedAt != default && StartedAt != fresh.StartedAt)
        {
            StartedAt = fresh.StartedAt;
            OnPropertyChanged(nameof(StartedAt));
        }

        RaiseTimeChanged();
    }

    /// <summary>
    /// Folds one (output, tools) reading into the two pace figures.
    ///
    /// Both are deltas over ELAPSED time, not lifetime averages. A session that
    /// produced 200k tokens an hour ago and has been parked since is not going
    /// fast, and dividing its total by its uptime would put it near the top of
    /// the wall for work it finished before lunch.
    /// </summary>
    private void SamplePace(long output, long tools)
    {
        var now = DateTime.Now;

        if (_paceSampledAt == default)
        {
            // First sight of this session: take the baseline, claim no rate.
            // ClockWall starting up beside a session that has been running for
            // three hours would otherwise divide those three hours of tokens
            // by the two seconds it has been watching.
            _paceSampledAt = now;
            _paceOutput = output;
            _paceTools = tools;
            return;
        }

        var elapsed = now - _paceSampledAt;
        if (elapsed < PaceWindow) return;

        var seconds = elapsed.TotalSeconds;

        // A transcript that was rotated or compacted restarts its counters, and
        // TranscriptTokens zeroes its tally to match. That is a reset, not
        // negative work, so it contributes nothing rather than a negative rate.
        var tokens = Math.Max(0, output - _paceOutput);
        var calls = Math.Max(0, tools - _paceTools);

        TokensPerSecond = Smooth(_tokensPerSecond, tokens / seconds);
        ToolsPerMinute = Smooth(_toolsPerMinute, calls / seconds * 60.0);

        _paceSampledAt = now;
        _paceOutput = output;
        _paceTools = tools;
    }

    /// <summary>Exponential moving average, except that the first non-zero
    /// reading is taken whole: a session that just started working should show
    /// its rate now, not ramp up to it over four scans.</summary>
    private static double Smooth(double previous, double sample) =>
        previous <= 0 ? sample : previous + PaceSmoothing * (sample - previous);

    /// <summary>
    /// Re-raises PropertyChanged for the time-derived properties (Uptime,
    /// SinceStatusChange) without touching disk or the process table. Call
    /// this from a lightweight periodic UI timer so bound "uptime" text
    /// keeps advancing between full rescans.
    /// </summary>
    public void RaiseTimeChanged()
    {
        OnPropertyChanged(nameof(Uptime));
        OnPropertyChanged(nameof(SinceStatusChange));
    }

    private static TimeSpan Since(DateTime value)
    {
        if (value == default) return TimeSpan.Zero;
        var span = DateTime.Now - value;
        return span < TimeSpan.Zero ? TimeSpan.Zero : span;
    }

    /// <summary>"C:\dev\Clock" -&gt; "Clock". Never throws.</summary>
    public static string DeriveProjectName(string? cwd)
    {
        if (string.IsNullOrWhiteSpace(cwd)) return string.Empty;
        try
        {
            var trimmed = cwd.Trim().TrimEnd('\\', '/');
            if (trimmed.Length == 0) return string.Empty;
            var leaf = Path.GetFileName(trimmed);
            return string.IsNullOrEmpty(leaf) ? trimmed : leaf;
        }
        catch
        {
            return cwd;
        }
    }

    /// <summary>Converts an epoch-milliseconds timestamp (as found in the
    /// session JSON) to local time. Never throws; returns default(DateTime)
    /// on any failure.</summary>
    /// <remarks>
    /// A non-positive input means "no timestamp", NOT 1970. The DTO leaves a
    /// missing JSON field at 0, and mapping that onto the Unix epoch would make
    /// every "is this timestamp set?" check downstream compare against a
    /// 56-year-old date instead of default(DateTime) - which is exactly how a
    /// genuinely running session whose file omits startedAt gets thrown away by
    /// the pid cross-check in SessionWatcher.IsProcessAliveAndMatches.
    /// </remarks>
    public static DateTime EpochMsToLocal(long epochMs)
    {
        if (epochMs <= 0) return default;

        try
        {
            return UnixEpochUtc.AddMilliseconds(epochMs).ToLocalTime();
        }
        catch
        {
            return default;
        }
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
