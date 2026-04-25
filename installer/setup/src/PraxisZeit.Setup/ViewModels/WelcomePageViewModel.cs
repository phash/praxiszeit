using CommunityToolkit.Mvvm.ComponentModel;
using PraxisZeit.Setup.Core.Models;

namespace PraxisZeit.Setup.ViewModels;

public sealed partial class WelcomePageViewModel : WizardPageBase
{
    public override string Key => "welcome";
    public override string Title => "Willkommen";
    public override bool CanGoBack => false;

    [ObservableProperty]
    public partial string PlatformName { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string DetectedInstallPath { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string CurrentVersion { get; set; } = "(keine Installation erkannt)";

    [ObservableProperty]
    public partial string TargetVersion { get; set; } = string.Empty;

    [ObservableProperty]
    public partial InstallMode Mode { get; set; } = InstallMode.FreshInstall;

    [ObservableProperty]
    public partial string ModeDescription { get; set; } = string.Empty;

    /// <summary>
    /// True nur im Update-Modus — die Welcome-Page zeigt dann einen
    /// expliziten DB-Backup-Hinweis ("Bevor Dateien ersetzt werden, wird
    /// ein vollstaendiges Backup nach data\backups erstellt").
    /// </summary>
    public bool ShowBackupCallout => Mode == InstallMode.Update;

    public override string NextButtonText => Mode switch
    {
        InstallMode.FreshInstall => "Installation starten",
        InstallMode.Update => "Update starten",
        InstallMode.Repair => "Reparieren",
        _ => "Weiter",
    };

    partial void OnModeChanged(InstallMode value)
    {
        ModeDescription = value switch
        {
            InstallMode.FreshInstall => "Es wird eine neue PraxisZeit-Installation eingerichtet. PostgreSQL, Python-Dependencies, Service und Firewall-Regeln werden konfiguriert.",
            InstallMode.Update => $"Bestehende Installation ({CurrentVersion}) wird auf {TargetVersion} aktualisiert. Datenbank, Config und Secrets bleiben unangetastet.",
            InstallMode.Repair => "Bestehende Installation wird repariert. Binaries werden neu kopiert, Config bleibt.",
            _ => string.Empty,
        };
        OnPropertyChanged(nameof(NextButtonText));
        OnPropertyChanged(nameof(ShowBackupCallout));
    }
}
