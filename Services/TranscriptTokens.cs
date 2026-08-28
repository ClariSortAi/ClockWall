using System.Text;
using System.Text.Json;

namespace ClockWall;

/// <summary>
/// Reads the two figures the session registry does not carry - how much of the
/// context window a session is holding, and how many tokens it has produced -
/// out of that session's transcript at
/// "%USERPROFILE%\.claude\projects\&lt;cwd-slug&gt;\&lt;sessionId&gt;.jsonl".
///
/// Transcripts are append-only and grow without bound (megabytes within a day),
/// so this is a TAIL FOLLOWER rather than a parser: each session's byte offset
/// is remembered, and a refresh reads only what was appended since. The first
/// sight of a session pays for its whole file once; the 5-second polls after it
/// read a few kilobytes.
///
/// Never throws. A locked, half-written, rotated or absent transcript leaves
/// the last good figures for that session standing (zero if there were none).
/// </summary>
internal sealed class TranscriptTokens
{
    private static readonly string ProjectsRoot = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude", "projects");

    private readonly Dictionary<string, Tally> _bySession = new(StringComparer.Ordinal);

    /// <summary>Context held by the most recent assistant turn, and output
    /// tokens summed over the session so far.</summary>
    public (int Context, long Output) Read(string cwd, string sessionId)
    {
        if (string.IsNullOrWhiteSpace(sessionId)) return default;

        if (!_bySession.TryGetValue(sessionId, out var tally))
            _bySession[sessionId] = tally = new Tally();

        try
        {
            Follow(Path.Combine(ProjectsRoot, Slug(cwd), sessionId + ".jsonl"), tally);
        }
        catch
        {
            // Absent, locked, mid-write, unreadable: keep what we already have.
        }

        return (tally.Context, tally.Output);
    }

    /// <summary>"C:\dev\Clock" -&gt; "C--dev-Clock", the on-disk project folder.</summary>
    private static string Slug(string? cwd) =>
        (cwd ?? string.Empty).Replace(':', '-').Replace('\\', '-').Replace('/', '-');

    private static void Follow(string path, Tally tally)
    {
        using var stream = new FileStream(
            path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);

        // Shorter than where we stopped means the file was replaced, not
        // appended to - start over rather than read from a meaningless offset.
        if (stream.Length < tally.Offset)
        {
            tally.Offset = 0;
            tally.Output = 0;
        }

        var pending = stream.Length - tally.Offset;
        if (pending <= 0) return;

        // ponytail: the first pass buffers the whole transcript (a couple of MB
        // today) in one go on the scan thread. If transcripts ever reach the
        // hundreds of MB, read it in fixed chunks instead - the offset/tally
        // state this already keeps is all a chunked loop would need.
        var buffer = new byte[pending];
        stream.Position = tally.Offset;
        stream.ReadExactly(buffer);

        // Whole lines only. A half-flushed final line is left behind by parking
        // the offset on the last newline; the next pass picks it up complete.
        var end = Array.LastIndexOf(buffer, (byte)'\n');
        if (end < 0) return;
        tally.Offset += end + 1;

        foreach (var line in Encoding.UTF8.GetString(buffer, 0, end).Split('\n'))
        {
            // Cheap reject: only assistant turns carry a usage block, and they
            // are a small minority of the lines in a transcript.
            if (line.IndexOf("\"usage\"", StringComparison.Ordinal) < 0) continue;

            try
            {
                using var document = JsonDocument.Parse(line);
                if (!document.RootElement.TryGetProperty("message", out var message) ||
                    !message.TryGetProperty("usage", out var usage))
                    continue;

                // Output only. Summing the input side across turns would count
                // the same cached prompt once per turn - tens of millions of
                // tokens for a session that has actually produced 300k.
                tally.Output += Count(usage, "output_tokens");

                // Context is the whole prompt the model just saw: what was sent
                // fresh, plus everything served from or written to the cache.
                tally.Context = Count(usage, "input_tokens")
                    + Count(usage, "cache_read_input_tokens")
                    + Count(usage, "cache_creation_input_tokens");
            }
            catch (JsonException)
            {
                // Not a shape we know. The offset has already moved past it.
            }
        }
    }

    private static int Count(JsonElement usage, string name) =>
        usage.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) ? number : 0;

    private sealed class Tally
    {
        public long Offset;
        public long Output;
        public int Context;
    }
}
