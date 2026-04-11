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
