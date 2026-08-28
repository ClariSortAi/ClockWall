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

    // Identity - set once at construction, never reassigned.
    public int Pid { get; }
    public string SessionId { get; }

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
                OnPropertyChanged(nameof(IsBusy));
        }
    }

    /// <summary>True when Status is "busy" (case-insensitive). Anything else
    /// (notably "idle") is treated as not-busy.</summary>
    public bool IsBusy => string.Equals(Status, "busy", StringComparison.OrdinalIgnoreCase);

    private string _version = string.Empty;
    public string Version { get => _version; private set => SetField(ref _version, value ?? string.Empty); }

    private string _kind = string.Empty;
    public string Kind { get => _kind; private set => SetField(ref _kind, value ?? string.Empty); }

    private string _entrypoint = string.Empty;
    public string Entrypoint { get => _entrypoint; private set => SetField(ref _entrypoint, value ?? string.Empty); }

    private int _contextTokens;
    /// <summary>Tokens in the prompt the model saw on this session's most
    /// recent turn - fresh input plus cache reads and writes. Read from the
    /// transcript by <see cref="TranscriptTokens"/>; 0 when it has none.</summary>
    public int ContextTokens { get => _contextTokens; private set => SetField(ref _contextTokens, value); }

    private long _outputTokens;
    /// <summary>Output tokens this session has produced since it started.</summary>
    public long OutputTokens { get => _outputTokens; private set => SetField(ref _outputTokens, value); }

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
        bool isRunning)
    {
        Pid = pid;
        SessionId = sessionId ?? string.Empty;
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
        _outputTokens = outputTokens;
        _isRunning = isRunning;
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
        IsRunning = fresh.IsRunning;

        if (fresh.StartedAt != default && StartedAt != fresh.StartedAt)
        {
            StartedAt = fresh.StartedAt;
            OnPropertyChanged(nameof(StartedAt));
        }

        RaiseTimeChanged();
    }

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
