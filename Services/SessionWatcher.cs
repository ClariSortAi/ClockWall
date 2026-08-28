using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using Microsoft.UI.Dispatching;

namespace ClockWall;

/// <summary>
/// Discovers the Claude Code agent sessions currently running on this
/// machine by watching "%USERPROFILE%\.claude\sessions\*.json" and exposes
/// them as an <see cref="ObservableCollection{AgentSession}"/> (sorted
/// busy-first, then most-recently-active) suitable for direct binding from
/// a WinUI ListView.
///
/// Designed to run unattended for days: a missing/locked/mid-write file, a
/// missing directory, or a watcher failure is tolerated and self-heals via
/// a periodic poll - it never lets an exception escape to the caller.
/// </summary>
public sealed class SessionWatcher : IDisposable
{
    /// <summary>How far a process's actual start time may drift from the
    /// startedAt recorded in its session file before we treat the pid as
    /// reused by an unrelated process rather than the original session.</summary>
    private static readonly TimeSpan ProcessStartTolerance = TimeSpan.FromMinutes(2);

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly string _sessionsDirectory;
    private readonly DispatcherQueue _dispatcherQueue;
    private readonly DispatcherQueueTimer _pollTimer;
    private readonly DispatcherQueueTimer _debounceTimer;
    private readonly DispatcherQueueTimer _uptimeTimer;

    /// <summary>Token figures live in the transcripts, not the session files.
    /// The follower keeps a byte offset per session so a refresh only reads
    /// what was appended. Touched only from the single in-flight scan.</summary>
    private readonly TranscriptTokens _transcripts = new();

    private FileSystemWatcher? _fileWatcher;
    private bool _started;
    private bool _disposed;
    private int _scanInFlight;

    /// <summary>Live collection of currently-running sessions. Always
    /// mutated on the UI thread that owns <see cref="DispatcherQueue"/>, so
    /// it is safe to bind directly from XAML.</summary>
    public ObservableCollection<AgentSession> Sessions { get; } = new();

    /// <summary>The directory being watched.</summary>
    public string SessionsDirectory => _sessionsDirectory;

    /// <param name="dispatcherQueue">
    /// The UI-thread dispatcher to marshal collection changes onto. Pass
    /// null to use <see cref="DispatcherQueue.GetForCurrentThread"/>, which
    /// requires this constructor to run on the UI thread.
    /// </param>
    /// <param name="sessionsDirectory">
    /// Overrides the sessions directory (for tests). Defaults to
    /// "%USERPROFILE%\.claude\sessions", resolved at runtime.
    /// </param>
    /// <param name="pollInterval">Safety-net rescan cadence. Default 5s.</param>
    /// <param name="uptimeTickInterval">
    /// Cadence for re-raising PropertyChanged on Uptime/SinceStatusChange
    /// (no disk or process-table access). Default 1s.
    /// </param>
    public SessionWatcher(
        DispatcherQueue? dispatcherQueue = null,
        string? sessionsDirectory = null,
        TimeSpan? pollInterval = null,
        TimeSpan? uptimeTickInterval = null)
    {
        _dispatcherQueue = dispatcherQueue ?? DispatcherQueue.GetForCurrentThread()
            ?? throw new InvalidOperationException(
                "SessionWatcher must be constructed on a thread with a DispatcherQueue, or given one explicitly.");
        _sessionsDirectory = sessionsDirectory ?? DefaultSessionsDirectory();

        _pollTimer = _dispatcherQueue.CreateTimer();
        _pollTimer.Interval = pollInterval ?? TimeSpan.FromSeconds(5);
        _pollTimer.IsRepeating = true;
        _pollTimer.Tick += (_, _) =>
        {
            EnsureFileWatcher();
            RequestRefresh();
        };

        _debounceTimer = _dispatcherQueue.CreateTimer();
        _debounceTimer.Interval = TimeSpan.FromMilliseconds(300);
        _debounceTimer.IsRepeating = false;
        _debounceTimer.Tick += (_, _) => RequestRefresh();

        _uptimeTimer = _dispatcherQueue.CreateTimer();
        _uptimeTimer.Interval = uptimeTickInterval ?? TimeSpan.FromSeconds(1);
        _uptimeTimer.IsRepeating = true;
        _uptimeTimer.Tick += (_, _) =>
        {
            foreach (var session in Sessions)
                session.RaiseTimeChanged();
        };
    }

    /// <summary>Resolves "%USERPROFILE%\.claude\sessions" without hardcoding
    /// a username.</summary>
    public static string DefaultSessionsDirectory() =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude", "sessions");

    /// <summary>Starts watching and does an immediate first scan. Safe to
    /// call once; subsequent calls are a no-op until <see cref="Stop"/>.</summary>
    public void Start()
    {
        if (_started || _disposed) return;
        _started = true;

        EnsureFileWatcher();
        _pollTimer.Start();
        _uptimeTimer.Start();
        RequestRefresh();
    }

    /// <summary>Stops all timers and the file watcher. Leaves the current
    /// <see cref="Sessions"/> contents as-is. Safe to call repeatedly.</summary>
    public void Stop()
    {
        if (!_started) return;
        _started = false;

        _pollTimer.Stop();
        _debounceTimer.Stop();
        _uptimeTimer.Stop();
        DisposeFileWatcher();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        Stop();
    }

    // ---- file watcher (best-effort; polling is the guaranteed path) ----

    private void EnsureFileWatcher()
    {
        if (_fileWatcher != null) return;

        try
        {
            if (!Directory.Exists(_sessionsDirectory)) return; // poll timer retries until it appears

            var watcher = new FileSystemWatcher(_sessionsDirectory, "*.json")
            {
                NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.FileName | NotifyFilters.Size,
            };
            watcher.Created += OnFileChanged;
            watcher.Changed += OnFileChanged;
            watcher.Deleted += OnFileChanged;
            watcher.Renamed += OnFileChanged;
            watcher.Error += OnFileWatcherError;
            watcher.EnableRaisingEvents = true;

            _fileWatcher = watcher;
        }
        catch
        {
            // No FS watcher this cycle (e.g. dir vanished between checks) -
            // the poll timer is the safety net and will retry.
            DisposeFileWatcher();
        }
    }

    private void DisposeFileWatcher()
    {
        var watcher = _fileWatcher;
        _fileWatcher = null;
        if (watcher is null) return;
        try
        {
            watcher.EnableRaisingEvents = false;
            watcher.Created -= OnFileChanged;
            watcher.Changed -= OnFileChanged;
            watcher.Deleted -= OnFileChanged;
            watcher.Renamed -= OnFileChanged;
            watcher.Error -= OnFileWatcherError;
            watcher.Dispose();
        }
        catch
        {
            // best-effort cleanup only
        }
    }

    private void OnFileChanged(object sender, FileSystemEventArgs e) => ScheduleDebouncedRefresh();

    private void OnFileWatcherError(object sender, ErrorEventArgs e)
    {
        // Buffer overflow, watched directory deleted, etc. Drop this
        // watcher; the poll timer keeps the UI current and will recreate
        // the watcher once the directory is stable again.
        _dispatcherQueue.TryEnqueue(DisposeFileWatcher);
    }

    private void ScheduleDebouncedRefresh()
    {
        _dispatcherQueue.TryEnqueue(() =>
        {
            if (!_started) return;
            _debounceTimer.Stop();
            _debounceTimer.Start();
        });
    }

    // ---- scan + merge ----

    private void RequestRefresh()
    {
        // Guard against overlapping scans if a previous one is still
        // running a slow retry against a locked file.
        if (Interlocked.Exchange(ref _scanInFlight, 1) == 1) return;

        var directory = _sessionsDirectory;
        _ = Task.Run(() =>
        {
            List<AgentSession> discovered;
            try
            {
                discovered = ScanDirectory(directory);
            }
            catch
            {
                discovered = new List<AgentSession>();
            }

            _dispatcherQueue.TryEnqueue(() =>
            {
                try
                {
                    Merge(discovered);
                }
                finally
                {
                    Interlocked.Exchange(ref _scanInFlight, 0);
                }
            });
        });
    }

    private List<AgentSession> ScanDirectory(string directory)
    {
        var results = new List<AgentSession>();

        string[] files;
        try
        {
            if (!Directory.Exists(directory)) return results;
            files = Directory.GetFiles(directory, "*.json");
        }
        catch
        {
            return results; // directory briefly unreadable - next poll retries
        }

        foreach (var file in files)
        {
            var session = TryLoadSession(file);
            if (session != null) results.Add(session);
        }

        return results;
    }

    private AgentSession? TryLoadSession(string path)
    {
        SessionFileDto? dto = null;

        for (var attempt = 0; attempt < 3; attempt++)
        {
            try
            {
                using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                dto = JsonSerializer.Deserialize<SessionFileDto>(stream, JsonOptions);
                break;
            }
            catch (IOException)
            {
                // File is being deleted or rewritten concurrently - normal
                // for a live session file. Brief retry, then give up for
                // this cycle; the next poll/FS event will pick it up.
                Thread.Sleep(25);
            }
            catch (UnauthorizedAccessException)
            {
                return null;
            }
            catch (JsonException)
            {
                return null; // malformed / mid-write partial JSON
            }
        }

        if (dto is null || dto.Pid <= 0 || string.IsNullOrWhiteSpace(dto.SessionId))
            return null;

        var startedAtLocal = AgentSession.EpochMsToLocal(dto.StartedAt);
        var updatedAtLocal = AgentSession.EpochMsToLocal(dto.UpdatedAt);
        var statusUpdatedAtLocal = dto.StatusUpdatedAt > 0
            ? AgentSession.EpochMsToLocal(dto.StatusUpdatedAt)
            : updatedAtLocal;

        if (!IsProcessAliveAndMatches(dto.Pid, startedAtLocal))
            return null; // stale file outliving its process, or pid reuse

        var (contextTokens, outputTokens, model, activity) = _transcripts.Read(dto.Cwd ?? string.Empty, dto.SessionId!);

        return new AgentSession(
            dto.Pid,
            dto.SessionId!,
            dto.Name ?? string.Empty,
            dto.Cwd ?? string.Empty,
            dto.Status ?? string.Empty,
            dto.Version ?? string.Empty,
            dto.Kind ?? string.Empty,
            dto.Entrypoint ?? string.Empty,
            startedAtLocal,
            updatedAtLocal,
            statusUpdatedAtLocal,
            contextTokens,
            outputTokens,
            model,
            activity,
            isRunning: true);
    }

    /// <summary>True only if pid is alive right now AND its actual process
    /// start time is within <see cref="ProcessStartTolerance"/> of the
    /// startedAt recorded in the session file (defends against PID reuse
    /// by an unrelated later process). Any exception is treated as "not
    /// running", per contract.</summary>
    private static bool IsProcessAliveAndMatches(int pid, DateTime expectedStartedAtLocal)
    {
        if (pid <= 0) return false;
        try
        {
            using var process = Process.GetProcessById(pid);
            if (process.HasExited) return false;

            if (expectedStartedAtLocal == default)
                return true; // no timestamp to cross-check; trust liveness alone

            var drift = process.StartTime - expectedStartedAtLocal;
            if (drift < TimeSpan.Zero) drift = -drift;
            return drift <= ProcessStartTolerance;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Reconciles <see cref="Sessions"/> with a freshly discovered
    /// set, in place: removes sessions that vanished, updates existing ones
    /// via <see cref="AgentSession.UpdateFrom"/> (preserving object
    /// identity), adds new ones, then reorders busy-first / most-recent
    /// first using Move so unaffected rows don't retemplate.</summary>
    private void Merge(List<AgentSession> discovered)
    {
        var freshBySessionId = new Dictionary<string, AgentSession>(discovered.Count, StringComparer.Ordinal);
        foreach (var fresh in discovered)
            freshBySessionId[fresh.SessionId] = fresh; // last one wins on an (unexpected) duplicate id

        for (var i = Sessions.Count - 1; i >= 0; i--)
        {
            if (!freshBySessionId.ContainsKey(Sessions[i].SessionId))
                Sessions.RemoveAt(i);
        }

        foreach (var fresh in freshBySessionId.Values)
        {
            AgentSession? existing = null;
            foreach (var candidate in Sessions)
            {
                if (candidate.SessionId == fresh.SessionId)
                {
                    existing = candidate;
                    break;
                }
            }

            if (existing != null)
                existing.UpdateFrom(fresh);
            else
                Sessions.Add(fresh);
        }

        Reorder();
    }

    /// <summary>Busy sessions first, then most-recently-active. Reorders via
    /// Move so the ObservableCollection emits minimal, animatable changes.</summary>
    private void Reorder()
    {
        var target = Sessions
            .OrderByDescending(s => s.IsBusy)
            .ThenByDescending(s => s.UpdatedAt)
            .ToList();

        for (var i = 0; i < target.Count; i++)
        {
            var currentIndex = Sessions.IndexOf(target[i]);
            if (currentIndex != i)
                Sessions.Move(currentIndex, i);
        }
    }

    /// <summary>Shape of a "&lt;pid&gt;.json" session file. Unknown fields
    /// are ignored by System.Text.Json; matching is case-insensitive via
    /// <see cref="JsonSerializerDefaults.Web"/>.</summary>
    private sealed class SessionFileDto
    {
        public int Pid { get; set; }
        public string? SessionId { get; set; }
        public string? Cwd { get; set; }
        public long StartedAt { get; set; }
        public string? Name { get; set; }
        public string? Status { get; set; }
        public string? Version { get; set; }
        public string? Kind { get; set; }
        public string? Entrypoint { get; set; }
        public long UpdatedAt { get; set; }
        public long StatusUpdatedAt { get; set; }
    }
}
