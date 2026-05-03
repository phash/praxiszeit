using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using PraxisZeit.Setup.Core.Models;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// User waehlt das Zielverzeichnis. Bei jedem Pfad-Wechsel laeuft der
/// <see cref="UpdateDetector"/> erneut: zeigt der Pfad eine bestehende
/// Installation, wechselt der detektierte Modus von Fresh auf Update.
///
/// <para>
/// Wenn der User-Intent (Welcome-Seite) ein Fresh-Install war, der Pfad
/// aber eine existierende Installation enthaelt, blenden wir eine
/// rote Warnung ein und blockieren "Weiter" — bis der User entweder
/// einen anderen Pfad waehlt ODER per Button auf Update umschaltet
/// (sicherer Default: kein Daten-Clobber).
/// </para>
/// </summary>
public sealed partial class InstallLocationPageViewModel : WizardPageBase
{
    public override string Key => "location";
    public override string Title => "Installationsort";

    private readonly UpdateDetector _detector;
    private readonly string _targetVersion;

    /// <summary>
    /// Vom User gewaehlter Modus (initial = Welcome-Page-Detect-Ergebnis).
    /// Setzt sich automatisch um, wenn der User explizit auf Update
    /// umschaltet via <see cref="SwitchToUpdateCommand"/>.
    /// </summary>
    [ObservableProperty]
    public partial InstallMode IntentMode { get; set; }

    /// <summary>
    /// Vom Detector erkannter Modus auf dem aktuellen <see cref="InstallPath"/>.
    /// Bei jedem Pfad-Wechsel neu berechnet.
    /// </summary>
    [ObservableProperty]
    public partial InstallMode DetectedMode { get; set; }

    [ObservableProperty]
    public partial string? DetectedVersion { get; set; }

    [ObservableProperty]
    public partial string InstallPath { get; set; } = string.Empty;

    [ObservableProperty]
    public partial bool IsPathReadOnly { get; set; }

    [ObservableProperty]
    public partial string? ValidationMessage { get; set; }

    public bool HasValidationMessage => !string.IsNullOrEmpty(ValidationMessage);

    /// <summary>
    /// True, wenn User-Intent Fresh ist, Pfad aber existierende
    /// Installation hat. Blendet die Warning-Card ein.
    /// </summary>
    public bool IsConflict =>
        IntentMode == InstallMode.FreshInstall && DetectedMode != InstallMode.FreshInstall;

    public string ConflictHeadline => DetectedMode switch
    {
        InstallMode.Update =>
            $"In diesem Verzeichnis liegt bereits PraxisZeit {DetectedVersion}.",
        InstallMode.Repair =>
            $"In diesem Verzeichnis liegt bereits PraxisZeit {DetectedVersion} (gleiche Version).",
        _ => string.Empty,
    };

    public string ConflictDescription =>
        "Eine Neuinstallation in diesem Verzeichnis wuerde die bestehende Installation und alle Daten "
        + "(Datenbank, Konfiguration, Lizenz) ueberschreiben. Empfohlene Alternative: auf Update "
        + "umschalten — dann wird die Datenbank gesichert, nur Binaries werden ersetzt.";

    public bool CanSwitchToUpdate => IsConflict && DetectedMode == InstallMode.Update;

    public InstallLocationPageViewModel()
        : this(new UpdateDetector(), "1.0.0", string.Empty, InstallMode.FreshInstall)
    {
    }

    public InstallLocationPageViewModel(
        UpdateDetector detector,
        string targetVersion,
        string defaultPath,
        InstallMode initialIntent)
    {
        _detector = detector;
        _targetVersion = targetVersion;
        IntentMode = initialIntent;
        InstallPath = defaultPath;
        // Update-Modus: User darf den Pfad nicht aendern (Update muss in
        // den Pfad einer existierenden Installation laufen — sonst waere
        // es kein Update).
        IsPathReadOnly = initialIntent == InstallMode.Update;
        Recompute();
    }

    partial void OnInstallPathChanged(string value)
    {
        Recompute();
    }

    partial void OnIntentModeChanged(InstallMode value)
    {
        Recompute();
        OnPropertyChanged(nameof(IsConflict));
        OnPropertyChanged(nameof(CanSwitchToUpdate));
    }

    private void Recompute()
    {
        if (string.IsNullOrWhiteSpace(InstallPath))
        {
            ValidationMessage = "Bitte einen Installationspfad waehlen.";
            CanGoNext = false;
            DetectedMode = InstallMode.FreshInstall;
            DetectedVersion = null;
            OnPropertyChanged(nameof(HasValidationMessage));
            OnPropertyChanged(nameof(IsConflict));
            OnPropertyChanged(nameof(CanSwitchToUpdate));
            OnPropertyChanged(nameof(ConflictHeadline));
            return;
        }

        DetectedVersion = _detector.DetectCurrentVersion(InstallPath);
        DetectedMode = _detector.DetectMode(InstallPath, _targetVersion);

        // Update-Intent + Pfad ohne Installation -> wir koennen das Update
        // nicht ausfuehren (es gibt nichts zu updaten). Klare Fehlermeldung.
        if (IntentMode == InstallMode.Update && DetectedMode == InstallMode.FreshInstall)
        {
            ValidationMessage =
                "Im gewaehlten Pfad wurde keine bestehende PraxisZeit-Installation gefunden. "
                + "Update ist in diesem Pfad nicht moeglich.";
            CanGoNext = false;
        }
        else if (IsConflict)
        {
            // Fresh-Intent + bestehende Installation -> blockieren bis aufgeloest
            ValidationMessage = null;
            CanGoNext = false;
        }
        else
        {
            ValidationMessage = null;
            CanGoNext = true;
        }

        OnPropertyChanged(nameof(HasValidationMessage));
        OnPropertyChanged(nameof(IsConflict));
        OnPropertyChanged(nameof(CanSwitchToUpdate));
        OnPropertyChanged(nameof(ConflictHeadline));
        SwitchToUpdateCommand.NotifyCanExecuteChanged();
    }

    /// <summary>
    /// User klickt "Auf Update umschalten" auf dem Conflict-Panel —
    /// IntentMode wechselt auf Update, der Wizard rebuilt die Pages
    /// (Update-Flow ueberspringt die ConfigPage). Wird vom MainWindow
    /// observiert.
    /// </summary>
    [RelayCommand(CanExecute = nameof(CanSwitchToUpdate))]
    private void SwitchToUpdate()
    {
        IntentMode = InstallMode.Update;
        IsPathReadOnly = true;
    }
}
