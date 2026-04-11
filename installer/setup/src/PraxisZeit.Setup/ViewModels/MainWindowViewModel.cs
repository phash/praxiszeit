using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using PraxisZeit.Setup.Core.Models;
using PraxisZeit.Setup.Core.Platform;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// Die Wizard-Shell. Haelt eine Liste von <see cref="WizardPageBase"/>-
/// Instanzen, exposed die aktuelle Page als <see cref="CurrentPage"/>
/// (die Views binden darauf), und handled Next/Back per Command.
///
/// Die Liste der Pages wird im Konstruktor anhand des erkannten
/// <see cref="InstallMode"/> zusammengebaut — Update skippt
/// Praxis-Daten / Admin / SSL, weil die Config schon existiert.
/// </summary>
public sealed partial class MainWindowViewModel : ViewModelBase
{
    private readonly IPlatform _platform;
    private readonly UpdateDetector _updateDetector;

    public ObservableCollection<WizardPageBase> Pages { get; } = [];

    [ObservableProperty]
    public partial WizardPageBase? CurrentPage { get; set; }

    [ObservableProperty]
    public partial int CurrentStepIndex { get; set; }

    [ObservableProperty]
    public partial string WindowTitle { get; set; } = "PraxisZeit Setup";

    public MainWindowViewModel()
        : this(PlatformFactory.Create(), new UpdateDetector())
    {
    }

    public MainWindowViewModel(IPlatform platform, UpdateDetector updateDetector)
    {
        _platform = platform;
        _updateDetector = updateDetector;

        var installPath = _platform.DefaultInstallDirectory;
        var targetVersion = ReadVersionFromAssembly();
        var mode = _updateDetector.DetectMode(installPath, targetVersion);
        var current = _updateDetector.DetectCurrentVersion(installPath);

        var welcome = new WelcomePageViewModel
        {
            PlatformName = _platform.Name,
            DetectedInstallPath = installPath,
            TargetVersion = targetVersion,
            CurrentVersion = current ?? "(keine Installation erkannt)",
            Mode = mode,
        };

        var done = new DonePageViewModel();

        Pages.Add(welcome);
        Pages.Add(done);
        CurrentPage = welcome;
        CurrentStepIndex = 0;

        WindowTitle = $"PraxisZeit Setup {targetVersion}";
    }

    public bool CanGoBack => CurrentPage?.CanGoBack == true && CurrentStepIndex > 0;
    public bool CanGoNext => CurrentPage?.CanGoNext == true;
    public string NextButtonText => CurrentPage?.NextButtonText ?? "Weiter";

    [RelayCommand(CanExecute = nameof(CanGoBack))]
    private void GoBack()
    {
        if (CurrentStepIndex <= 0)
        {
            return;
        }
        CurrentStepIndex--;
        CurrentPage = Pages[CurrentStepIndex];
        OnPropertyChanged(nameof(CanGoBack));
        OnPropertyChanged(nameof(CanGoNext));
        OnPropertyChanged(nameof(NextButtonText));
    }

    [RelayCommand(CanExecute = nameof(CanGoNext))]
    private async Task GoNextAsync()
    {
        if (CurrentPage is null)
        {
            return;
        }

        var canLeave = await CurrentPage.OnLeaveAsync().ConfigureAwait(true);
        if (!canLeave)
        {
            return;
        }

        if (CurrentStepIndex < Pages.Count - 1)
        {
            CurrentStepIndex++;
            CurrentPage = Pages[CurrentStepIndex];
        }
        else
        {
            // Letzte Page: Close-Signal fuer die View
            CloseRequested?.Invoke();
        }

        OnPropertyChanged(nameof(CanGoBack));
        OnPropertyChanged(nameof(CanGoNext));
        OnPropertyChanged(nameof(NextButtonText));
    }

    public event Action? CloseRequested;

    private static string ReadVersionFromAssembly()
    {
        var version = typeof(MainWindowViewModel).Assembly.GetName().Version;
        return version is null ? "1.4.0" : $"{version.Major}.{version.Minor}.{version.Build}";
    }
}
