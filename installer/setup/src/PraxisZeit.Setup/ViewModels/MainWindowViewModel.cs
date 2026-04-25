using System.Collections.ObjectModel;
using System.Runtime.Versioning;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using PraxisZeit.Setup.Core.Models;
using PraxisZeit.Setup.Core.Platform;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// Wizard-Shell. Orchestriert das End-to-End:
///   Welcome  → User klickt "Update/Installation starten"
///   Progress → wir extrahieren das eingebettete Payload nach %TEMP%
///              und rufen <see cref="ScriptRunner"/> auf, der setup.bat
///              (Fresh) oder update-wizard.ps1 -Headless (Update) als
///              Subprocess startet. Marker-Events werden in der Page
///              auf Step-Liste / Log / Progress-Bar gerendert.
///   Done     → Erfolg/Fehler + "Im Browser oeffnen"-Button
/// </summary>
public sealed partial class MainWindowViewModel : ViewModelBase
{
    private readonly IPlatform _platform;
    private readonly UpdateDetector _updateDetector;
    private readonly EmbeddedPayloadExtractor _payloadExtractor;
    private readonly ScriptRunner _scriptRunner;

    private readonly WelcomePageViewModel _welcome;
    private readonly ConfigPageViewModel? _config;
    private readonly ProgressPageViewModel _progress;
    private readonly DonePageViewModel _done;

    private string? _extractedPayloadDir;
    private WizardPageBase? _previousPage;

    public ObservableCollection<WizardPageBase> Pages { get; } = [];

    [ObservableProperty]
    public partial WizardPageBase? CurrentPage { get; set; }

    [ObservableProperty]
    public partial int CurrentStepIndex { get; set; }

    [ObservableProperty]
    public partial string WindowTitle { get; set; } = "PraxisZeit Setup";

    public MainWindowViewModel()
        : this(PlatformFactory.Create(), new UpdateDetector(), new EmbeddedPayloadExtractor(), CreateRunner())
    {
    }

    public MainWindowViewModel(
        IPlatform platform,
        UpdateDetector updateDetector,
        EmbeddedPayloadExtractor payloadExtractor,
        ScriptRunner scriptRunner)
    {
        _platform = platform;
        _updateDetector = updateDetector;
        _payloadExtractor = payloadExtractor;
        _scriptRunner = scriptRunner;

        var installPath = _platform.DefaultInstallDirectory;
        var targetVersion = ReadVersionFromAssembly();
        var mode = _updateDetector.DetectMode(installPath, targetVersion);
        var current = _updateDetector.DetectCurrentVersion(installPath);

        _welcome = new WelcomePageViewModel
        {
            PlatformName = _platform.Name,
            DetectedInstallPath = installPath,
            TargetVersion = targetVersion,
            CurrentVersion = current ?? "(keine Installation erkannt)",
            Mode = mode,
        };

        _progress = new ProgressPageViewModel();
        _progress.InitializeSteps(mode);

        _done = new DonePageViewModel();

        // ConfigPage nur im Fresh-Install / Repair-Modus — Update behaelt
        // die existierende praxiszeit.conf (Backend-Bootstrap erkennt den
        // Admin schon in der DB, neue Werte wuerden im Update-Pfad ignoriert
        // bzw. wuerden bestehende User-Anpassungen ueberschreiben).
        _config = mode is InstallMode.FreshInstall or InstallMode.Repair
            ? new ConfigPageViewModel { AdminEmail = "admin@praxis.local" }
            : null;

        Pages.Add(_welcome);
        if (_config is not null)
        {
            Pages.Add(_config);
        }
        Pages.Add(_progress);
        Pages.Add(_done);
        CurrentPage = _welcome;
        CurrentStepIndex = 0;
        RebuildStepDots();

        WindowTitle = $"PraxisZeit Setup {targetVersion}";
    }

    /// <summary>
    /// Footer-Dot: true/false-State fuer den View-Trigger.
    /// </summary>
    public sealed partial class StepDot : ObservableObject
    {
        [ObservableProperty]
        public partial bool IsActive { get; set; }

        [ObservableProperty]
        public partial bool IsDone { get; set; }
    }

    public bool CanGoBack => CurrentPage?.CanGoBack == true && CurrentStepIndex > 0;
    public bool CanGoNext => CurrentPage?.CanGoNext == true;
    public string NextButtonText => CurrentPage?.NextButtonText ?? "Weiter";

    /// <summary>
    /// Step-Indicator-Dots im Footer: aktiv = aktueller Step, done =
    /// bereits erledigt. Anzahl haengt vom Modus ab — Update hat 3
    /// Pages (Welcome/Progress/Done), Fresh/Repair 4 (mit ConfigPage).
    /// </summary>
    public ObservableCollection<StepDot> StepDots { get; } = [];

    private void RebuildStepDots()
    {
        StepDots.Clear();
        for (int i = 0; i < Pages.Count; i++)
        {
            StepDots.Add(new StepDot
            {
                IsActive = i == CurrentStepIndex,
                IsDone = i < CurrentStepIndex,
            });
        }
    }

    partial void OnCurrentStepIndexChanged(int value)
    {
        RebuildStepDots();
    }

    partial void OnCurrentPageChanged(WizardPageBase? value)
    {
        if (_previousPage is not null)
        {
            _previousPage.PropertyChanged -= OnCurrentPagePropertyChanged;
        }
        _previousPage = value;
        if (value is not null)
        {
            value.PropertyChanged += OnCurrentPagePropertyChanged;
        }
        RaiseShellChanged();
    }

    private void OnCurrentPagePropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(WizardPageBase.CanGoNext) or nameof(WizardPageBase.NextButtonText))
        {
            RaiseShellChanged();
        }
    }

    [RelayCommand(CanExecute = nameof(CanGoBack))]
    private void GoBack()
    {
        if (CurrentStepIndex <= 0)
        {
            return;
        }
        CurrentStepIndex--;
        CurrentPage = Pages[CurrentStepIndex];
        RaiseShellChanged();
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

        // Welcome →  ConfigPage (Fresh/Repair) oder direkt Progress (Update)
        if (CurrentPage is WelcomePageViewModel)
        {
            if (_config is not null)
            {
                CurrentStepIndex = Pages.IndexOf(_config);
                CurrentPage = _config;
                RaiseShellChanged();
                return;
            }
            await TransitionToProgressAndRunAsync().ConfigureAwait(true);
            return;
        }

        // ConfigPage → Progress: Installation kicken
        if (CurrentPage is ConfigPageViewModel)
        {
            await TransitionToProgressAndRunAsync().ConfigureAwait(true);
            return;
        }

        // Progress → Done: nur wenn der Runner fertig ist (CanGoNext = true)
        if (CurrentPage is ProgressPageViewModel progress)
        {
            CurrentStepIndex = Pages.IndexOf(_done);
            CurrentPage = _done;
            RaiseShellChanged();
            return;
        }

        // Done → Close
        if (CurrentPage is DonePageViewModel)
        {
            CleanupTempPayload();
            CloseRequested?.Invoke();
        }
    }

    private async Task TransitionToProgressAndRunAsync()
    {
        CurrentStepIndex = Pages.IndexOf(_progress);
        CurrentPage = _progress;
        _progress.IsRunning = true;
        _progress.CanGoNext = false;
        RaiseShellChanged();

        var sink = new Progress<RunnerEvent>(_progress.Apply);
        bool success;

        try
        {
            // 1) Payload aus EmbeddedResource nach %TEMP% extrahieren
            sink.OnReportFallback(new RunnerLogEvent("Entpacke Installationspaket..."));
            if (_payloadExtractor.HasEmbeddedPayload)
            {
                _extractedPayloadDir = await _payloadExtractor.ExtractAsync(
                    progress: null,
                    ct: default).ConfigureAwait(true);
                sink.OnReportFallback(new RunnerLogEvent($"Payload entpackt nach {_extractedPayloadDir}"));
            }
            else
            {
                // Dev-Build ohne eingebettetes ZIP: setup.exe liegt neben dem
                // entpackten ZIP-Inhalt (build/release-X.Y.Z/windows/). Dann
                // nutzen wir das App-Verzeichnis als Payload-Quelle.
                _extractedPayloadDir = AppContext.BaseDirectory;
                sink.OnReportFallback(new RunnerLogEvent(
                    $"Dev-Build: nutze App-Verzeichnis als Payload ({_extractedPayloadDir})"));
            }

            // 2) Runner ausfuehren je nach Modus
            if (!OperatingSystem.IsWindows())
            {
                sink.OnReportFallback(new RunnerLogEvent(
                    "Diese Setup-Variante laeuft nur unter Windows. Linux/macOS: bitte install.sh aus dem .tar.gz nutzen."));
                success = false;
            }
            else
            {
                success = _welcome.Mode == InstallMode.Update
                    ? await RunUpdateOnWindowsAsync(_welcome.DetectedInstallPath, _extractedPayloadDir, sink)
                        .ConfigureAwait(true)
                    : await RunFreshOnWindowsAsync(_welcome.DetectedInstallPath, _extractedPayloadDir, sink, _config?.ToConfigValues())
                        .ConfigureAwait(true);
            }
        }
        catch (Exception ex)
        {
            sink.OnReportFallback(new RunnerLogEvent($"FEHLER: {ex.Message}"));
            sink.OnReportFallback(new RunnerDoneEvent(false));
            success = false;
        }

        // 3) Done-Page mit Ergebnis befuellen
        _done.Success = success;
        _done.Headline = success ? "Fertig!" : "Installation fehlgeschlagen";
        _done.Summary = success
            ? (_welcome.Mode == InstallMode.Update
                ? $"PraxisZeit wurde erfolgreich auf Version {_welcome.TargetVersion} aktualisiert. Eine Datenbank-Sicherung liegt unter data\\backups."
                : (_config is not null
                    ? $"PraxisZeit ist eingerichtet, der Service laeuft. Sie koennen sich jetzt mit dem Admin-Account ({_config.AdminUsername}) anmelden."
                    : "PraxisZeit wurde eingerichtet, der Service laeuft. Bevor Sie sich anmelden koennen, muss config\\praxiszeit.conf einmalig angepasst werden (Praxisname, Admin-E-Mail, Admin-Passwort)."))
            : "Bitte pruefen Sie das Protokoll der Progress-Page und logs\\service-stderr.log im Installationsverzeichnis. Ein automatisches Datenbank-Backup wurde unter data\\backups abgelegt.";
        _done.BrowserUrl = "https://localhost/";

        // CanGoNext freigeben damit der Footer-Button "Weiter" -> "Schliessen"
        // klickbar wird (siehe Progress.OnDoneEvent).
        _progress.IsRunning = false;
        _progress.CanGoNext = true;
        RaiseShellChanged();
    }

    [SupportedOSPlatform("windows")]
    private Task<bool> RunUpdateOnWindowsAsync(string installDir, string payloadDir, IProgress<RunnerEvent> sink) =>
        _scriptRunner.RunUpdateAsync(installDir, payloadDir, sink);

    [SupportedOSPlatform("windows")]
    private Task<bool> RunFreshOnWindowsAsync(string installDir, string payloadDir, IProgress<RunnerEvent> sink, PraxisZeitConfigValues? configValues) =>
        _scriptRunner.RunFreshInstallAsync(installDir, payloadDir, sink, configValues);

    private void CleanupTempPayload()
    {
        if (string.IsNullOrEmpty(_extractedPayloadDir))
        {
            return;
        }
        // Nur die selbst erzeugten Temp-Ordner loeschen, nicht das App-Verzeichnis
        // (Dev-Build-Fallback).
        if (_extractedPayloadDir.StartsWith(Path.GetTempPath(), StringComparison.OrdinalIgnoreCase))
        {
            EmbeddedPayloadExtractor.DeleteExtractedPayload(_extractedPayloadDir);
        }
        _extractedPayloadDir = null;
    }

    private void RaiseShellChanged()
    {
        OnPropertyChanged(nameof(CanGoBack));
        OnPropertyChanged(nameof(CanGoNext));
        OnPropertyChanged(nameof(NextButtonText));
        GoBackCommand.NotifyCanExecuteChanged();
        GoNextCommand.NotifyCanExecuteChanged();
    }

    public event Action? CloseRequested;

    private static string ReadVersionFromAssembly()
    {
        var version = typeof(MainWindowViewModel).Assembly.GetName().Version;
        return version is null ? "1.4.0" : $"{version.Major}.{version.Minor}.{version.Build}";
    }

    private static ScriptRunner CreateRunner()
    {
        // ScriptRunner ist [SupportedOSPlatform("windows")]; auf Linux/macOS
        // wird er nicht aufgerufen, kann aber instanziiert werden — die
        // Platform-Annotation ist nur ein Compile-Time-Check, keine
        // Windows-API im Konstruktor.
#pragma warning disable CA1416
        return new ScriptRunner();
#pragma warning restore CA1416
    }
}

internal static class ProgressExtensions
{
    /// <summary>
    /// IProgress&lt;T&gt;.Report ohne null-checks. Der Standard-Progress
    /// wirft bei null nicht, aber wenn wir den Sink mehrfach in einer
    /// Methode benutzen wollen ist diese Helper-Form bequemer.
    /// </summary>
    public static void OnReportFallback<T>(this IProgress<T>? progress, T value) =>
        progress?.Report(value);
}
