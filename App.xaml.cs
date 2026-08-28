using Microsoft.UI.Xaml;

namespace ClockWall;

/// <summary>
/// Application entry point for the ClockWall kiosk display.
/// </summary>
public partial class App : Application
{
    private Window? _window;

    /// <summary>
    /// The single wall window. Available to the rest of the app (for example to
    /// resolve an <c>AppWindow</c> or a <c>DispatcherQueue</c>) once launched.
    /// </summary>
    public static Window? MainWindowInstance { get; private set; }

    public App()
    {
        // The app is dark-first: a wall panel that is on all night should not
        // flash a white screen if the machine happens to be in the light theme.
        RequestedTheme = ApplicationTheme.Dark;
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _window = new MainWindow();
        MainWindowInstance = _window;
        _window.Activate();
    }
}
