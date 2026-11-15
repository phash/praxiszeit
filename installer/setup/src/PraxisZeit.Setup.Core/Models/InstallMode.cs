namespace PraxisZeit.Setup.Core.Models;

/// <summary>
/// Differenziert Erstinstallation von Update einer bereits vorhandenen
/// PraxisZeit-Installation. Der <see cref="Core.Services.IUpdateDetector"/>
/// ermittelt beim Wizard-Start, welcher Modus vorliegt, und skippt Seiten
/// die im Update-Fall nicht angefasst werden sollen (Praxis-Daten,
/// Admin-Account, SSL-Modus).
/// </summary>
public enum InstallMode
{
    /// <summary>Keine bestehende Installation erkannt — Erstinstallation.</summary>
    FreshInstall,

    /// <summary>Bestehende Installation erkannt — Update der Binaries.</summary>
    Update,

    /// <summary>Bestehende Installation mit identischer Version — Reparatur/Reinstall.</summary>
    Repair,
}

public static class InstallModeExtensions
{
    /// <summary>
    /// Update und Reparatur laufen ueber <c>update-wizard.ps1</c>: Backup,
    /// Dienst stoppen, Dateien kopieren, pruefen, starten. Konfiguration,
    /// Datenbank und Admin-Konto bleiben unangetastet. Nur die Erstinstallation
    /// fragt Ports und Admin-Daten ab und schreibt <c>praxiszeit.conf</c>.
    /// Kundenfall 2026-11-15: Ein abgebrochenes Update hinterliess schon die
    /// neue Version im Ordner, Setup bot danach nur noch "Reparieren" an — und
    /// die lief als Erstinstallation und haette die Konfiguration ueberschrieben.
    /// </summary>
    public static bool KeepsExistingInstallation(this InstallMode mode) =>
        mode is InstallMode.Update or InstallMode.Repair;
}
