using System.Globalization;
using System.Text;
using System.Text.Json;

namespace ClockWall;

/// <summary>
/// Today's Claude usage across the whole machine: output tokens produced and an
/// estimated dollar figure, summed from every transcript under
/// "%USERPROFILE%\.claude\projects" that was written today - live sessions,
/// finished ones and subagents alike.
///
/// The same tail-follower idea as <see cref="TranscriptTokens"/>, but keyed per
/// FILE rather than per session, because a session that exited an hour ago
/// still spent money today. Never throws; a file that cannot be read this
/// cycle is picked up by a later one.
/// </summary>
internal sealed class DailyBurn
{
    /// <summary>$ per million tokens, (input, output), matched on the model id.</summary>
    // ponytail: rates hand-copied from the 2026-06 price list. They drift, and
    // this table is the one place to update them. An unknown model bills at the
    // opus rate - mid-table, so the error is bounded either way.
    private static (double In, double Out) Rates(string model) =>
        model.Contains("fable") || model.Contains("mythos") ? (10, 50)
        : model.Contains("sonnet-5") ? (2, 10)
        : model.Contains("sonnet") ? (3, 15)
        : model.Contains("haiku") ? (1, 5)
        : (5, 25); // opus, and anything unrecognised

    private static readonly string ProjectsRoot = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude", "projects");

    /// <summary>Transcripts are re-enumerated at most this often. The session
    /// scan calls <see cref="Read"/> every few seconds; a day total does not
    /// need that cadence.</summary>
    private static readonly TimeSpan ScanInterval = TimeSpan.FromSeconds(60);

    private readonly Dictionary<string, long> _offsets = new(StringComparer.OrdinalIgnoreCase);

    private DateTime _day = DateTime.Today;
    private DateTime _lastScan;
    private long _outputTokens;
    private double _dollars;

    /// <summary>Current totals for today, rescanning at most once per
    /// <see cref="ScanInterval"/>. Call from a background thread: the first
    /// scan of a day reads every transcript written that day in full; the
    /// scans after it read only what was appended.</summary>
    public (long OutputTokens, double Dollars) Read()
    {
        var now = DateTime.Now;
        if (now - _lastScan < ScanInterval) return (_outputTokens, _dollars);
        _lastScan = now;

        if (DateTime.Today != _day)
        {
            // Midnight: the totals reset but the offsets stand - everything
            // already read belongs to yesterday, and only what is appended
            // from here on counts toward the new day.
            _day = DateTime.Today;
            _outputTokens = 0;
            _dollars = 0;
        }

        try
        {
            var root = new DirectoryInfo(ProjectsRoot);
            if (!root.Exists) return (_outputTokens, _dollars);

            foreach (var file in root.EnumerateFiles("*.jsonl", SearchOption.AllDirectories))
            {
                if (file.LastWriteTime < _day) continue; // untouched today

                try
                {
                    FollowFile(file.FullName);
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"[ClockWall] burn skip {file.Name}: {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[ClockWall] burn scan failed: {ex.Message}");
        }

        return (_outputTokens, _dollars);
    }

    private void FollowFile(string path)
    {
        using var stream = new FileStream(
            path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);

        _offsets.TryGetValue(path, out var offset);
        if (stream.Length < offset) offset = 0; // replaced, not appended

        var pending = stream.Length - offset;
        if (pending <= 0) return;

        var buffer = new byte[pending];
        stream.Position = offset;
        stream.ReadExactly(buffer);

        // Whole lines only, same as TranscriptTokens: a half-flushed final line
        // waits for the next scan.
        var end = Array.LastIndexOf(buffer, (byte)'\n');
        if (end < 0) return;
        _offsets[path] = offset + end + 1;

        foreach (var line in Encoding.UTF8.GetString(buffer, 0, end).Split('\n'))
        {
            if (!line.Contains("\"usage\"", StringComparison.Ordinal)) continue;

            try
            {
                TallyLine(line);
            }
            catch (JsonException)
            {
                // Not a shape we know. The offset has already moved past it.
            }
        }
    }

    private void TallyLine(string line)
    {
        using var document = JsonDocument.Parse(line);
        var root = document.RootElement;
        if (!root.TryGetProperty("message", out var message) ||
            !message.TryGetProperty("usage", out var usage))
            return;

        // A cold start mid-day reads files that can straddle midnight, so each
        // line is dated individually rather than trusting the file's mtime.
        if (root.TryGetProperty("timestamp", out var stamp) &&
            stamp.ValueKind == JsonValueKind.String &&
            DateTime.TryParse(stamp.GetString(), CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind, out var when) &&
            when.ToLocalTime().Date != _day)
            return;

        var model = message.TryGetProperty("model", out var m) && m.ValueKind == JsonValueKind.String
            ? m.GetString() ?? string.Empty
            : string.Empty;
        var (rateIn, rateOut) = Rates(model);

        double Count(string name) =>
            usage.TryGetProperty(name, out var value) && value.TryGetInt64(out var n) ? n : 0;

        var output = Count("output_tokens");
        _outputTokens += (long)output;

        // Cache reads bill at a tenth of the input rate, writes at 1.25x (the
        // 5-minute tier; 1-hour writes bill 2x, so those are undercounted a
        // little). It is an estimate on a wall clock, and labelled as one.
        _dollars += (output * rateOut
            + Count("input_tokens") * rateIn
            + Count("cache_read_input_tokens") * rateIn * 0.1
            + Count("cache_creation_input_tokens") * rateIn * 1.25) / 1_000_000d;
    }
}
