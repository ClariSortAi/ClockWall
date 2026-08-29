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
/// The collection is FLAT but reads as a tree: each session is followed by the
/// SUBAGENTS running inside it (<see cref="AgentSession.IsChild"/>), which have
/// no session file of their own because they have no process of their own - they
/// are found through the transcripts their parent writes for them, under
/// "...\projects\&lt;cwd-slug&gt;\&lt;sessionId&gt;\subagents". The view indents
/// them; nothing here needs a nested collection type.
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

    /// <summary>How recently a subagent's transcript must have been written to
    /// for it to count as running.</summary>
    // ponytail: this is an MTIME HEURISTIC and it is weaker than the pid check a
    // session gets. A subagent has no pid and no session file - it runs inside
    // its parent's process - so there is nothing to ask the OS about. A killed
    // or crashed agent therefore reads as live until its transcript goes stale,
    // and an agent that spends longer than this window on one slow tool call
    // reads as finished until it writes again. The parent's own "busy" status is
    // required as corroboration, which is what makes it trustworthy enough to
    // put on a wall. Upgrade path: the day a subagent gets a status file, check
    // that instead and delete this window.
    private static readonly TimeSpan SubagentLiveWindow = TimeSpan.FromSeconds(45);

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

    /// <summary>Machine-wide totals for today, dead sessions included. Also
    /// touched only from the single in-flight scan; internally throttled.</summary>
    private readonly DailyBurn _burn = new();

    private FileSystemWatcher? _fileWatcher;
    private bool _started;
    private bool _disposed;
    private int _scanInFlight;

    /// <summary>Live collection of currently-running sessions. Always
    /// mutated on the UI thread that owns <see cref="DispatcherQueue"/>, so
    /// it is safe to bind directly from XAML.</summary>
    public ObservableCollection<AgentSession> Sessions { get; } = new();

    /// <summary>Output tokens produced today by every session on this machine,
    /// running or not. Written on the UI thread after each scan.</summary>
    public long TodayOutputTokens { get; private set; }

    /// <summary>Estimated dollars spent today, same coverage. An estimate -
    /// see <see cref="DailyBurn"/> for what it rounds over.</summary>
    public double TodayDollars { get; private set; }

    /// <summary>Raised on the UI thread after every scan has merged, whether
    /// or not the collection changed - the hook for chrome (header totals)
    /// that must track values a CollectionChanged cannot see.</summary>
    public event Action? Refreshed;

    /// <summary>The directory being watched.</summary>
    public string SessionsDirectory => _sessionsDirectory;

    /// <summary>
    /// How many subagent rows are worth materialising - set by the view from
    /// the height it measured for them.
    ///
    /// Liveness is a stat and is done for every subagent there is; context,
    /// tokens and activity need the transcript OPENED and PARSED, so that is
    /// done only for the few that will actually be rendered. Five sessions each
    /// running a dozen subagents is 60 transcripts every poll otherwise, and the
    /// display polls forever. An int assignment is atomic, so the scan thread
    /// reading this while the UI thread writes it is safe as-is.
    /// </summary>
    public int MaxChildren { get; set; } = 4;

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

            var burn = _burn.Read(); // throttles itself; usually a no-op

            _dispatcherQueue.TryEnqueue(() =>
            {
                try
                {
                    TodayOutputTokens = burn.OutputTokens;
                    TodayDollars = burn.Dollars;
                    Merge(discovered);
                    Refreshed?.Invoke();
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

        // Subagents of every session, competing for the same few rows: most
        // recently active first, since that is the closest thing to "busiest".
        var candidates = new List<(FileInfo File, AgentSession Parent)>();

        foreach (var file in files)
        {
            var session = TryLoadSession(file, candidates);
            if (session != null) results.Add(session);
        }

        foreach (var (transcript, parent) in candidates
                     .OrderByDescending(c => c.File.LastWriteTime)
                     .Take(Math.Max(0, MaxChildren)))
        {
            results.Add(LoadSubagent(transcript, parent));
        }

        return results;
    }

    /// <summary>
    /// Stats every subagent transcript this session has, returning how many
    /// there are in total and which of them look live. Reads nothing: the
    /// enumeration already carries each file's timestamp, so this stays cheap
    /// at a session with dozens of finished agents behind it.
    /// </summary>
    private static (int Total, List<FileInfo> Live) SubagentFiles(string cwd, string sessionId, bool parentIsBusy)
    {
        var live = new List<FileInfo>();
        var total = 0;

        try
        {
            var directory = new DirectoryInfo(TranscriptTokens.SubagentsDirectory(cwd, sessionId));
            if (!directory.Exists) return (0, live);

            var cutoff = DateTime.Now - SubagentLiveWindow;

            // "agent-*.jsonl" recursively: it takes in the workflow agents one
            // level down and leaves out the journal.jsonl sitting beside them,
            // which is not an agent.
            foreach (var file in directory.EnumerateFiles("agent-*.jsonl", SearchOption.AllDirectories))
            {
                total++;

                // A subagent cannot be working while the session hosting it is
                // not. That corroboration is most of what makes the mtime
                // window above worth trusting.
                if (parentIsBusy && file.LastWriteTime >= cutoff) live.Add(file);
            }
        }
        catch
        {
            // Missing or unreadable this cycle - the next poll retries.
        }

        return (total, live);
    }

    /// <summary>Builds the row for one subagent: its name and model come from
    /// the "agent-&lt;id&gt;.meta.json" beside the transcript, everything else
    /// from the transcript itself, through the same follower the sessions
    /// use.</summary>
    private AgentSession LoadSubagent(FileInfo transcript, AgentSession parent)
    {
        var id = Path.GetFileNameWithoutExtension(transcript.Name);
        var metaPath = Path.Combine(transcript.DirectoryName ?? string.Empty, id + ".meta.json");

        SubagentMetaDto? meta = null;
        var startedAt = transcript.CreationTime;
        try
        {
            var metaFile = new FileInfo(metaPath);
            if (metaFile.Exists)
            {
                // The meta file is written once, when the agent is spawned, so
                // its timestamp is the agent's start time.
                startedAt = metaFile.LastWriteTime;
                using var stream = metaFile.OpenRead();
                meta = JsonSerializer.Deserialize<SubagentMetaDto>(stream, JsonOptions);
            }
        }
        catch
        {
            // No metadata: fall back to the id below rather than dropping a
            // subagent we can see is running.
        }

        var (contextTokens, outputTokens, model, activity) = _transcripts.ReadFile(id, transcript.FullName);

        // The transcript's model id is the precise one ("claude-opus-5"); the
        // meta file's is the alias that was asked for ("opus"). Prefer the
        // former, keep the latter for an agent that has not answered yet.
        if (string.IsNullOrWhiteSpace(model)) model = meta?.Model ?? string.Empty;

        var name = meta?.Description;
        if (string.IsNullOrWhiteSpace(name)) name = meta?.AgentType;      // workflow agents carry no description
        if (string.IsNullOrWhiteSpace(name)) name = id;

        return new AgentSession(
            parent.Pid,                 // it runs inside the parent's process
            id,
            name!,
            parent.Cwd,
            "busy",                     // only live subagents are surfaced at all
            string.Empty,
            meta?.AgentType ?? string.Empty,
            string.Empty,
            startedAt,
            transcript.LastWriteTime,
            startedAt,
            contextTokens,
            outputTokens,
            model,
            activity,
            isRunning: true,
            isChild: true,
            parentSessionId: parent.SessionId);
    }

    private AgentSession? TryLoadSession(string path, List<(FileInfo File, AgentSession Parent)> candidates)
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

        var isBusy = string.Equals(dto.Status, "busy", StringComparison.OrdinalIgnoreCase);
        var (subagentTotal, subagentLive) = SubagentFiles(dto.Cwd ?? string.Empty, dto.SessionId!, isBusy);

        var session = new AgentSession(
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
            isRunning: true,
            subagentCount: subagentTotal,
            subagentLiveCount: subagentLive.Count);

        foreach (var live in subagentLive)
            candidates.Add((live, session));

        return session;
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

    /// <summary>Busy sessions first, then most-recently-active - with each
    /// session's subagents immediately after it, so a child row is never
    /// separated from the parent it is indented under. Reorders via Move so the
    /// ObservableCollection emits minimal, animatable changes.</summary>
    private void Reorder()
    {
        var target = Sessions
            .Where(s => !s.IsChild)
            // A session blocked on the user outranks even a busy one: its
            // flash is the panel's one alarm, and an alarm below the fold
            // is silence.
            .OrderByDescending(s => s.NeedsAttention ? 2 : s.IsBusy ? 1 : 0)
            .ThenByDescending(s => s.UpdatedAt)
            .SelectMany(parent => Sessions
                .Where(c => c.IsChild && c.ParentSessionId == parent.SessionId)
                .OrderByDescending(c => c.UpdatedAt)
                .Prepend(parent))
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

    /// <summary>Shape of an "agent-&lt;id&gt;.meta.json" sitting beside a
    /// subagent transcript: {"agentType":"general-purpose","description":"Add
    /// agent activity ticker","spawnDepth":1,"model":"opus"}. Workflow agents
    /// carry no description.</summary>
    private sealed class SubagentMetaDto
    {
        public string? AgentType { get; set; }
        public string? Description { get; set; }
        public string? Model { get; set; }
    }
}
