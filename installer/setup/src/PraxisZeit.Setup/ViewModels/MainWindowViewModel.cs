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
    private readonly InstallLocationPageViewModel _location;
    private readonly PortsPageViewModel _ports;
    private readonly LicensePageViewModel _license;
    private readonly ConfigPageViewModel _config;
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

        _location = new InstallLocationPageViewModel(_updateDetector, targetVersion, installPath, mode);
        _location.PropertyChanged += OnLocationModeChanged;

        _ports = new PortsPageViewModel();
        _license = new LicensePageViewModel();

        // ConfigPage existiert immer (im Update-Flow wird sie spaeter
        // uebersprungen — siehe RebuildPagesForMode). Das vermeidet eine
        // teure Re-Instanziierung wenn der User in der Location-Page
        // doch noch von Fresh auf Update umschaltet.
        _config = new ConfigPageViewModel { AdminEmail = "admin@praxis.local" };

        RebuildPagesForMode(mode);
        CurrentPage = _welcome;
        CurrentStepIndex = 0;
        RebuildStepDots();

        WindowTitle = $"PraxisZeit Setup {targetVersion}";
    }

    /// <summary>
    /// Reagiert auf User-Klick "Auf Update umschalten" in der Location-
    /// Page (oder beliebigen IntentMode-Wechsel). Die ConfigPage wird
    /// im Update-Flow uebersprungen, also muss die Page-Liste neu gebaut
    /// werden. Welcome-Mode-Property fuer den Backup-Hinweis aktualisieren
    /// wir mit.
    /// </summary>
    private void OnLocationModeChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(InstallLocationPageViewModel.IntentMode)) return;
        var newMode = _location.IntentMode;
        _welcome.Mode = newMode;
        _progress.InitializeSteps(newMode);
        RebuildPagesForMode(newMode);
        RebuildStepDots();
        RaiseShellChanged();
    }

    /// <summary>
    /// Setzt die <see cref="Pages"/>-Reihenfolge je nach Modus. ConfigPage
    /// laeuft nur im Fresh-Install / Repair (Update behaelt die existierende
    /// praxiszeit.conf — neue Werte wuerden bestehende User-Anpassungen
    /// stillschweigend ueberschreiben).
    /// </summary>
    private void RebuildPagesForMode(InstallMode mode)
    {
        Pages.Clear();
        Pages.Add(_welcome);
        Pages.Add(_location);
        if (mode is InstallMode.FreshInstall or InstallMode.Repair)
        {
            Pages.Add(_ports);
        }
        Pages.Add(_license);
        if (mode is InstallMode.FreshInstall or InstallMode.Repair)
        {
            Pages.Add(_config);
        }
        Pages.Add(_progress);
        Pages.Add(_done);
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

        // Done → Close
        if (CurrentPage is DonePageViewModel)
        {
            CleanupTempPayload();
            CloseRequested?.Invoke();
            return;
        }

        // Naechste Page in der Liste finden
        var idx = Pages.IndexOf(CurrentPage);
        var next = idx + 1 < Pages.Count ? Pages[idx + 1] : null;

        // Wenn die naechste Page Progress ist, kicken wir die Installation
        // — Pages-Liste enthaelt Progress immer als zweitletzten Eintrag.
        if (next is ProgressPageViewModel)
        {
            await TransitionToProgressAndRunAsync().ConfigureAwait(true);
            return;
        }

        // Progress → Done: nur wenn der Runner fertig ist (CanGoNext = true)
        if (CurrentPage is ProgressPageViewModel)
        {
            CurrentStepIndex = Pages.IndexOf(_done);
            CurrentPage = _done;
            RaiseShellChanged();
            return;
        }

        if (next is null)
        {
            return;
        }

        CurrentStepIndex = Pages.IndexOf(next);
        CurrentPage = next;
        RaiseShellChanged();
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
                    "Diese Setup-Variante läuft nur unter Windows. Linux/macOS: bitte install.sh aus dem .tar.gz nutzen."));
                success = false;
            }
            else
            {
                var installDir = _location.InstallPath;
                if (_welcome.Mode == InstallMode.Update)
                {
                    success = await RunUpdateOnWindowsAsync(installDir, _extractedPayloadDir, sink)
                        .ConfigureAwait(true);
                    // Update-Pfad: License-Page kann eine NEUE Lizenz
                    // einspielen (Erneuerung). Wir schreiben nur die Datei,
                    // praxiszeit.conf bleibt unangetastet.
                    if (success && _license.SelectedMode == "license"
                        && !string.IsNullOrWhiteSpace(_license.LicenseToken))
                    {
                        var configDir = Path.Combine(installDir, "config");
                        await PraxisZeitConfigWriter.WriteLicenseFileAsync(configDir, _license.LicenseToken).ConfigureAwait(true);
                        sink.OnReportFallback(new RunnerLogEvent("Lizenz-Datei aktualisiert."));
                    }
                }
                else
                {
                    var configValues = BuildConfigValues();
                    success = await RunFreshOnWindowsAsync(installDir, _extractedPayloadDir, sink, configValues)
                        .ConfigureAwait(true);
                    // Fresh-Install: License-File schreiben falls eine
                    // echte Lizenz vorliegt. Demo schreibt KEINE license.key
                    // — der ConfigWriter hat das demo_expires_at-Feld
                    // bereits in praxiszeit.conf gesetzt.
                    if (success && _license.SelectedMode == "license"
                        && !string.IsNullOrWhiteSpace(_license.LicenseToken))
                    {
                        var configDir = Path.Combine(installDir, "config");
                        await PraxisZeitConfigWriter.WriteLicenseFileAsync(configDir, _license.LicenseToken).ConfigureAwait(true);
                        sink.OnReportFallback(new RunnerLogEvent("Lizenz-Datei eingespielt."));
                    }
                }
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
                    ? $"PraxisZeit ist eingerichtet, der Service läuft. Sie können sich jetzt mit dem Admin-Account ({_config.AdminUsername}) anmelden."
                    : "PraxisZeit wurde eingerichtet, der Service läuft. Bevor Sie sich anmelden können, muss config\\praxiszeit.conf einmalig angepasst werden (Praxisname, Admin-E-Mail, Admin-Passwort)."))
            : "Bitte prüfen Sie das Protokoll der Progress-Page und logs\\service-stderr.log im Installationsverzeichnis. Ein automatisches Datenbank-Backup wurde unter data\\backups abgelegt.";
        var browserUrl = _ports.HttpsPort == 443
            ? "https://localhost/"
            : $"https://localhost:{_ports.HttpsPort}/";
        _done.BrowserUrl = browserUrl;

        // Der Dienst meldet sich bei SCM als "running", bevor uvicorn den Web-Port
        // wirklich bedient (PG-Start + Migrationen laufen noch). Wir pollen den Port
        // und geben "Im Browser öffnen" erst frei, wenn der Server antwortet — sonst
        // landet ein sofortiger Klick auf "nicht erreichbar". Fire-and-forget, der
        // Poller aktualisiert IsServerReady auf dem UI-Kontext (ConfigureAwait(true)).
        if (success)
        {
            _ = _done.WaitForServerAsync();
        }

        // Nach erfolgreichem Install: optionale Verknüpfungen + Apps-&-Features-Eintrag.
        if (success && OperatingSystem.IsWindows())
        {
            CreateShortcutsIfRequested(browserUrl);
            RegisterInAppsAndFeatures();
        }

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

    /// <summary>
    /// Legt optional eine Desktop-Verknüpfung und/oder einen Startmenü-Eintrag
    /// an, die den Browser auf die lokale PraxisZeit-Instanz öffnen. Best-effort:
    /// schlägt das fehl (z.B. Rechte), bricht die Installation NICHT ab.
    /// </summary>
    [SupportedOSPlatform("windows")]
    private void CreateShortcutsIfRequested(string url)
    {
        try
        {
            if (_location.CreateDesktopShortcut) { ShortcutCreator.CreateDesktopShortcut(url); }
            if (_location.CreateStartMenuEntry) { ShortcutCreator.CreateStartMenuShortcut(url); }
        }
        catch
        {
            // Verknüpfungen sind optional — Fehler hier dürfen den Install nicht stoppen.
        }
    }

    /// <summary>
    /// Registriert PraxisZeit in „Apps &amp; Features", sodass es dort sichtbar
    /// ist und über die gebündelte uninstall.bat deinstalliert werden kann.
    /// Best-effort.
    /// </summary>
    [SupportedOSPlatform("windows")]
    private void RegisterInAppsAndFeatures()
    {
        try
        {
            UninstallRegistrar.Register(_location.InstallPath, _welcome.TargetVersion);
        }
        catch
        {
            // Registry-Eintrag ist optional — Fehler darf den Install nicht stoppen.
        }
    }

    /// <summary>
    /// Merged die Werte aus den drei User-Eingabe-Pages (Ports, Lizenz,
    /// Config) zu einem ConfigValues-Snapshot, den der ConfigWriter in
    /// die TOML-Datei serialisiert. Lizenz-File wird separat geschrieben
    /// (siehe TransitionToProgressAndRunAsync).
    /// </summary>
    private PraxisZeitConfigValues BuildConfigValues()
    {
        var baseValues = _config.ToConfigValues();
        return baseValues with
        {
            HttpsPort = _ports.HttpsPort,
            HttpRedirectPort = _ports.EffectiveHttpRedirectPort,
            LicenseToken = _license.SelectedMode == "license" ? _license.LicenseToken : null,
            DemoDays = _license.SelectedMode == "demo" ? LicensePageViewModel.DemoDurationDays : null,
        };
    }

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
