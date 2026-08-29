using System.Diagnostics;
using System.Globalization;
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace ClockWall;

/// <summary>
/// CPU, RAM and network throughput for the machine the wall is running on,
/// plus the three processes holding the most memory, resampled once a second.
/// Self-contained: it starts its own timer on Loaded and stops it on Unloaded,
/// like <see cref="ClockPanel"/>.
///
/// Every figure comes from an in-box OS call - GetSystemTimes,
/// GlobalMemoryStatusEx, and NetworkInterface statistics. No performance
/// counters: PerformanceCounter is a separate package on modern .NET, needs a
/// discarded warm-up read, and is a heavier way to reach the same numbers.
///
/// Two of the three are DELTAS, which is where meters like this normally go
/// wrong, so the counter hygiene is deliberate and spelled out at each site:
///   - a first sample has no predecessor, so it renders a placeholder rather
///     than a number that would be wrong or a spike;
///   - counters reset (an adapter reconnecting zeroes its byte counts), so a
///     negative delta clamps to zero;
///   - elapsed time comes from Stopwatch, never from subtracting wall clocks,
///     so an NTP correction or a DST shift cannot invent a throughput figure.
/// </summary>
public sealed partial class SystemMeters : UserControl
{
    /// <summary>Bytes per GB, for the RAM readout.</summary>
    private const double BytesPerGB = 1024d * 1024d * 1024d;

    /// <summary>Shown for a delta that has no previous sample yet. Never a number.</summary>
    private const string NoReading = "--";

    /// <summary>
    /// FIGURE SPACE (U+2007) - the pad character, and the reason the bars do
    /// not shuffle sideways as a number gains a digit.
    ///
    /// Tabular figures give every DIGIT a common advance, but an ordinary space
    /// is about half a digit wide, so right-aligning "  7%" against "100%" with
    /// ordinary spaces still changes the measured width and still moves the bar
    /// beside it. U+2007 is defined to be exactly one digit wide, so a padded
    /// string measures the same whatever the value is. Same problem ClockPanel
    /// has, solved the way a percentage allows - the clock zero-pads its hour,
    /// and "007%" is not an option here.
    /// </summary>
    private const char FigureSpace = ' ';

    /// <summary>Ticks between re-enumerations of the network adapters. See UpdateNetwork.</summary>
    private const int AdapterRescanTicks = 10;

    /// <summary>Ticks between process-table scans. See UpdateTopMemory.</summary>
    private const int ProcessRescanTicks = 5;

    private DispatcherQueueTimer? _timer;

    // The three RAM-eater cells, paired so the render loop can index them.
    private readonly (TextBlock Name, TextBlock Size)[] _eaterCells;

    private int _ticksSinceProcessScan = ProcessRescanTicks;

    // CPU: previous GetSystemTimes reading, in 100ns units.
    private long _prevIdle;
    private long _prevKernel;
    private long _prevUser;
    private bool _haveCpuSample;

    // Network: previous byte counts PER INTERFACE (keyed by adapter id), and
    // the monotonic timestamp they were taken at.
    private Dictionary<string, (long Received, long Sent)> _prevTraffic = new();
    private long _prevTrafficStamp;
    private bool _haveTrafficSample;

    // The adapters worth counting, re-scanned every AdapterRescanTicks, each
    // paired with the key its byte counts are remembered under.
    private (string Key, NetworkInterface Adapter)[] _adapters = Array.Empty<(string, NetworkInterface)>();
    private int _ticksSinceRescan = AdapterRescanTicks;

    public SystemMeters()
    {
        InitializeComponent();

        _eaterCells = new[]
        {
            (Eater1Name, Eater1Size),
            (Eater2Name, Eater2Size),
            (Eater3Name, Eater3Size),
        };

        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (_timer is null)
        {
            _timer = DispatcherQueue.CreateTimer();
            _timer.Interval = TimeSpan.FromSeconds(1);
            _timer.IsRepeating = true;
            _timer.Tick += (_, _) => Refresh();
        }

        // This first pass primes the CPU and network samples and renders the
        // placeholder for both. The tick a second later is the first one with
        // a delta behind it, and the first that shows a rate.
        Refresh();
        _timer.Start();
    }

    private void OnUnloaded(object sender, RoutedEventArgs e) => _timer?.Stop();

    private void Refresh()
    {
        UpdateCpu();
        UpdateMemory();
        UpdateTopMemory();
        UpdateNetwork();
    }

    private void UpdateCpu()
    {
        if (!Native.GetSystemTimes(out var idle, out var kernel, out var user))
        {
            return;
        }

        if (_haveCpuSample)
        {
            // KERNEL TIME ALREADY INCLUDES IDLE TIME. So kernel+user is the
            // whole interval summed over every core, and the busy part is that
            // total LESS idle - not the total less idle plus idle again, and
            // not kernel+user with idle added. Getting this wrong yields a
            // number that still looks plausible, which is why it survives.
            var total = (kernel - _prevKernel) + (user - _prevUser);
            var busy = total - (idle - _prevIdle);
            var load = total > 0 ? Math.Clamp((double)busy / total, 0d, 1d) : 0d;

            CpuValue.Text = Fixed(load * 100, "F0", 3) + "%";
            SetBar(CpuBarFill, CpuBarRest, load);
        }
        else
        {
            CpuValue.Text = NoReading.PadLeft(3, FigureSpace) + "%";
        }

        _prevIdle = idle;
        _prevKernel = kernel;
        _prevUser = user;
        _haveCpuSample = true;
    }

    private void UpdateMemory()
    {
        // No delta here - GlobalMemoryStatusEx is an instantaneous reading, so
        // RAM is correct on the very first pass and needs no placeholder.
        var status = new Native.MEMORYSTATUSEX
        {
            dwLength = (uint)Marshal.SizeOf<Native.MEMORYSTATUSEX>(),
        };

        if (!Native.GlobalMemoryStatusEx(ref status) || status.ullTotalPhys == 0)
        {
            return;
        }

        var used = status.ullTotalPhys - status.ullAvailPhys;
        var fraction = (double)used / status.ullTotalPhys;

        // The absolute figure earns its place: "61%" alone does not say whether
        // there are 12 GB free or 1.2.
        //
        // ponytail: the whole line is measured to fit 968px with 3px to spare at
        // its widest (verified against a capture with CPU pegged at 100%), and
        // that assumes a two-digit GB total. A machine with 100GB or more of RAM
        // adds three characters here and would overflow. Drop the type a step in
        // Theme.xaml if this ever runs on one - there is no point spending a
        // branch on a case this display will not meet.
        RamValue.Text =
            Fixed(fraction * 100, "F0", 3) + "% · " +
            Fixed(used / BytesPerGB, "F1", 4) + "/" +
            (status.ullTotalPhys / BytesPerGB).ToString("F0", CultureInfo.InvariantCulture) + " GB";

        SetBar(RamBarFill, RamBarRest, fraction);
    }

    private void UpdateTopMemory()
    {
        // ponytail: scanned every fifth tick, not every tick. Process.GetProcesses
        // is a full process-table snapshot - measured on this machine (~330
        // processes) at 25-40ms, against 0.05ms for the three OS calls the rest
        // of this control makes. Spending that every second on the UI thread to
        // watch a list that reorders every few minutes is not a trade worth
        // making. The ceiling: a process that balloons and exits inside five
        // seconds is never seen. If that matters, move the scan to a background
        // thread and marshal the result back rather than shortening the interval.
        if (_ticksSinceProcessScan++ < ProcessRescanTicks)
        {
            return;
        }

        _ticksSinceProcessScan = 0;

        // GROUPED BY IMAGE NAME, because the honest answer to "what is eating
        // the RAM" is "Chrome", not the largest one of Chrome's forty renderer
        // processes. Windows' own Task Manager groups the same way.
        //
        // Working set, matching Task Manager's Memory column and the RAM meter
        // below, which is also physical pages. It over-counts a grouped app
        // slightly - pages shared between those forty renderers are counted
        // once per process - so a group total is an upper bound, not a sum of
        // disjoint memory. Private bytes would trade that for under-counting
        // the shared pages the app genuinely caused to be resident. Neither is
        // "correct"; this one at least agrees with the tool the viewer would
        // reach for to check it.
        var processes = Array.Empty<Process>();
        try
        {
            processes = Process.GetProcesses();

            var top = processes
                .GroupBy(process => process.ProcessName, StringComparer.OrdinalIgnoreCase)
                .Select(group => (Name: group.Key, Bytes: group.Sum(process => process.WorkingSet64)))
                .OrderByDescending(entry => entry.Bytes)
                .Take(_eaterCells.Length)
                .ToArray();

            for (var i = 0; i < _eaterCells.Length; i++)
            {
                var (name, size) = _eaterCells[i];

                // Fewer distinct images than cells cannot happen on a running
                // Windows box, but an empty cell is still cheaper than an
                // IndexOutOfRangeException on a display that runs for days.
                if (i >= top.Length)
                {
                    name.Text = string.Empty;
                    size.Text = string.Empty;
                    continue;
                }

                // Upper-cased to sit in the same register as CPU / RAM / NET
                // below, which share this style - these read as labels on a
                // figure, not as sentence text.
                name.Text = top[i].Name.ToUpperInvariant();
                size.Text = Fixed(top[i].Bytes / BytesPerGB, "F1", 4) + " GB";
            }
        }
        catch (InvalidOperationException)
        {
            // A process exited between the snapshot and the read of its
            // counters. The cells keep their last values and the next scan
            // picks the table up again - the same self-healing the roster's
            // file reads rely on.
        }
        finally
        {
            // Each Process carries a handle. Enumerating 330 of these every
            // five seconds and leaving them to the finaliser is a handle leak
            // measured in thousands per hour.
            foreach (var process in processes)
            {
                process.Dispose();
            }
        }
    }

    private void UpdateNetwork()
    {
        // ponytail: the adapter LIST is cached and re-scanned every tenth tick;
        // the byte counts are read every tick. Measured on this machine, which
        // has 41 adapters (Hyper-V, WSL, VPN, the lot): GetAllNetworkInterfaces
        // is 46ms and reading all thirteen live adapters' statistics is 0.7ms.
        // 46ms of UI thread every second, forever, for a display that shows the
        // machine's own load is not a cost worth paying to notice a new VPN
        // adapter instantly. The ceiling: an adapter that appears or vanishes
        // takes up to ten seconds to be counted or dropped. If that ever
        // matters, re-scan on NetworkChange.NetworkAddressChanged as well -
        // keeping this interval as the backstop, because those events are
        // missable in the same way the roster's FileSystemWatcher is.
        if (_ticksSinceRescan >= AdapterRescanTicks)
        {
            // Filtered here rather than per tick because a cached adapter's
            // OperationalStatus is a snapshot and would not change anyway. A
            // dropped adapter keeps returning its frozen byte counts until the
            // next scan, which deltas to zero - stale, but never a spike.
            //
            // DistinctBy is the one that stops the meter reading four times the
            // real rate. Windows exposes every NDIS filter bound to an adapter
            // as an interface in its own right - "Ethernet-QoS Packet
            // Scheduler-0000", "Ethernet-WFP Native MAC Layer LightWeight
            // Filter-0000" - each with its own GUID but the MAC, the index and
            // the byte counters of the one real adapter underneath. On this
            // machine that is the same Ethernet card four times over. Keying on
            // Id counts the same wire once per filter; keying on the MAC counts
            // it once. Adapters with no MAC at all are not a link being counted
            // twice, so they keep their own identity.
            _adapters = NetworkInterface.GetAllNetworkInterfaces()
                .Where(nic => nic.OperationalStatus == OperationalStatus.Up &&
                              nic.NetworkInterfaceType is not (NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel))
                .DistinctBy(AdapterKey)
                .Select(nic => (Key: AdapterKey(nic), Adapter: nic))
                .ToArray();
            _ticksSinceRescan = 0;
        }

        _ticksSinceRescan++;

        var stamp = Stopwatch.GetTimestamp();
        var current = new Dictionary<string, (long Received, long Sent)>();
        long received = 0;
        long sent = 0;

        // Loopback is this machine talking to itself, and a Tunnel's traffic is
        // counted a second time on the adapter underneath it - both were left
        // out of the scan above, because either one invents traffic.
        foreach (var (key, nic) in _adapters)
        {
            long nowReceived;
            long nowSent;
            try
            {
                var stats = nic.GetIPv4Statistics();
                nowReceived = stats.BytesReceived;
                nowSent = stats.BytesSent;
            }
            catch (NetworkInformationException)
            {
                // The adapter went away between the enumeration and the query.
                // Dropping it also drops its previous sample, so it cannot
                // contribute a spike if it comes back.
                continue;
            }

            // Delta PER ADAPTER, never over the summed total. An adapter that
            // appears (docking, VPN up, wifi joining) arrives with its whole
            // lifetime byte count, and one that disappears takes its count with
            // it - deltaing the sum would read the first as a multi-gigabyte
            // spike and the second as a negative. A negative delta on an
            // adapter that IS still here means its counter reset, which clamps
            // to zero rather than to nonsense.
            if (_prevTraffic.TryGetValue(key, out var previous))
            {
                received += Math.Max(0, nowReceived - previous.Received);
                sent += Math.Max(0, nowSent - previous.Sent);
            }

            current[key] = (nowReceived, nowSent);
        }

        // Monotonic, so a clock correction between ticks cannot turn a normal
        // delta into an absurd rate (or a divide by a negative interval).
        var seconds = Stopwatch.GetElapsedTime(_prevTrafficStamp, stamp).TotalSeconds;

        NetValue.Text = _haveTrafficSample && seconds > 0
            ? $"↓ {Rate(received / seconds)}  ↑ {Rate(sent / seconds)}"
            : $"↓ {NoReading}  ↑ {NoReading}";

        _prevTraffic = current;
        _prevTrafficStamp = stamp;
        _haveTrafficSample = true;
    }

    /// <summary>
    /// Formats a number to a fixed rendered width - see <see cref="FigureSpace"/>.
    /// </summary>
    private static string Fixed(double value, string format, int width) =>
        value.ToString(format, CultureInfo.InvariantCulture).PadLeft(width, FigureSpace);

    /// <summary>
    /// What an adapter's byte counts are remembered under. The MAC, so that the
    /// filter bindings stacked on one adapter collapse to the one wire they all
    /// report - and so that a re-scan picking a different member of that stack
    /// still finds the previous sample. An adapter with no MAC keeps its own id.
    /// </summary>
    private static string AdapterKey(NetworkInterface adapter)
    {
        var mac = adapter.GetPhysicalAddress().ToString();
        return mac.Length > 0 ? mac : adapter.Id;
    }

    /// <summary>
    /// Formats a byte rate with the unit that keeps it in three significant
    /// figures. Padded to a fixed width, and every unit is four characters, so
    /// the rendered string never changes width as the number does.
    /// </summary>
    private static string Rate(double bytesPerSecond)
    {
        var perSecond = bytesPerSecond / 1024d;
        var unit = "KB/s";

        if (perSecond >= 1000d)
        {
            perSecond /= 1024d;
            unit = "MB/s";
        }

        if (perSecond >= 1000d)
        {
            perSecond /= 1024d;
            unit = "GB/s";
        }

        return Fixed(perSecond, "F1", 5) + " " + unit;
    }

    /// <summary>
    /// Sets a bar to a 0-1 fraction by weighting the fill and remainder columns
    /// against each other. No pixel arithmetic and no dependency on ActualWidth
    /// having been measured yet - layout resolves it against the track's width,
    /// whatever the theme makes that.
    /// </summary>
    private static void SetBar(ColumnDefinition fill, ColumnDefinition rest, double fraction)
    {
        fraction = Math.Clamp(fraction, 0d, 1d);
        fill.Width = new GridLength(fraction, GridUnitType.Star);
        rest.Width = new GridLength(1d - fraction, GridUnitType.Star);
    }
}
