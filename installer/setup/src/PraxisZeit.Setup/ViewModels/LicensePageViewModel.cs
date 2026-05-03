using System.Globalization;
using CommunityToolkit.Mvvm.ComponentModel;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// User entscheidet sich fuer einen von drei Wegen:
///
/// <list type="number">
/// <item>Lizenz-Token paste/Datei waehlen → Live-Validierung gegen den
///       gleichen Ed25519-Public-Key, den auch das Backend nutzt. Bei
///       Erfolg zeigen wir Kunde, Mitarbeiter-Limit und Ablaufdatum.</item>
/// <item>30-Tage-Demo → keine Lizenz noetig, schreibt nur eine
///       <c>demo_expires_at</c>-Markierung in <c>praxiszeit.conf</c>.</item>
/// </list>
///
/// "Skip ohne irgendwas" ist nicht moeglich — der Wizard erzwingt eine
/// Entscheidung, sonst koennte das Backend nach dem Install nicht starten
/// (siehe <c>backend/app/main.py</c>: kein License + kein Demo = sys.exit).
/// </summary>
public sealed partial class LicensePageViewModel : WizardPageBase
{
    public override string Key => "license";
    public override string Title => "Lizenz";

    /// <summary>Anzahl Tage Demo-Laufzeit, wenn der User Demo waehlt.</summary>
    public const int DemoDurationDays = 30;

    /// <summary>Mailto-/Web-Adresse fuer Lizenz-Bestellung. UI zeigt den
    /// String als Link an. Aktuell projekt@phash.de — wird spaeter durch
    /// die Verkaufsadresse ersetzt.</summary>
    public const string LicenseContact = "projekt@phash.de";

    /// <summary>"license" oder "demo" — wird vom MainWindow ausgewertet
    /// um zwischen den Modi zu unterscheiden beim Conf-Schreiben.</summary>
    [ObservableProperty]
    public partial string SelectedMode { get; set; } = "license";

    [ObservableProperty]
    public partial string LicenseToken { get; set; } = string.Empty;

    /// <summary>Wenn der User eine Datei via Browse waehlt, merken wir
    /// uns den Pfad — fuer den UI-Hint "geladen aus: …"</summary>
    [ObservableProperty]
    public partial string? LoadedFromPath { get; set; }

    [ObservableProperty]
    public partial LicenseInfo? ValidatedInfo { get; set; }

    [ObservableProperty]
    public partial string? ValidationError { get; set; }

    [ObservableProperty]
    public partial bool IsExpiredButOtherwiseValid { get; set; }

    public bool HasValidatedInfo => ValidatedInfo is not null;
    public bool HasValidationError => !string.IsNullOrEmpty(ValidationError);

    /// <summary>"Gueltig bis 31.12.2026" oder "(unbefristet)".</summary>
    public string ExpiryDisplay
    {
        get
        {
            if (ValidatedInfo?.ExpiresAt is not { } exp)
            {
                return "Unbefristet gueltig";
            }
            var formatted = exp.ToLocalTime().ToString("dd.MM.yyyy", CultureInfo.GetCultureInfo("de-DE"));
            if (ValidatedInfo.IsExpired)
            {
                return $"Abgelaufen am {formatted}";
            }
            var days = ValidatedInfo.DaysUntilExpiry ?? 0;
            return days <= 30
                ? $"Gueltig bis {formatted} (nur noch {days} Tage)"
                : $"Gueltig bis {formatted}";
        }
    }

    public string DemoEndDisplay
    {
        get
        {
            var d = DateTime.Now.AddDays(DemoDurationDays);
            return d.ToString("dd.MM.yyyy", CultureInfo.GetCultureInfo("de-DE"));
        }
    }

    public LicensePageViewModel()
    {
        Recompute();
    }

    partial void OnSelectedModeChanged(string value)
    {
        Recompute();
    }

    partial void OnLicenseTokenChanged(string value)
    {
        Recompute();
    }

    /// <summary>
    /// Wird vom Code-Behind beim File-Picker-Erfolg aufgerufen — laedt
    /// den Datei-Inhalt in <see cref="LicenseToken"/> und merkt sich
    /// den Pfad. Token-Validierung passiert via OnLicenseTokenChanged.
    /// </summary>
    public void LoadFromFile(string path, string content)
    {
        LoadedFromPath = path;
        LicenseToken = content.Trim();
    }

    private void Recompute()
    {
        if (SelectedMode == "demo")
        {
            ValidatedInfo = null;
            ValidationError = null;
            IsExpiredButOtherwiseValid = false;
            CanGoNext = true;
            EmitDerivedChanges();
            return;
        }

        if (string.IsNullOrWhiteSpace(LicenseToken))
        {
            ValidatedInfo = null;
            ValidationError = null;
            IsExpiredButOtherwiseValid = false;
            CanGoNext = false;
            EmitDerivedChanges();
            return;
        }

        var result = LicenseValidator.ValidateToken(LicenseToken);
        switch (result)
        {
            case LicenseValid v:
                ValidatedInfo = v.Info;
                ValidationError = null;
                IsExpiredButOtherwiseValid = false;
                CanGoNext = true;
                break;
            case LicenseExpired ex:
                // Abgelaufen aber signaturlich gueltig: User soll das
                // sehen, aber Continue ist erlaubt — Backend laeuft dann
                // im Read-Only-Mode. Wir haben aber keine Demo-Verlaengerung
                // mehr.
                ValidatedInfo = ex.Info;
                ValidationError = null;
                IsExpiredButOtherwiseValid = true;
                CanGoNext = true;
                break;
            case LicenseInvalid inv:
                ValidatedInfo = null;
                ValidationError = inv.Reason;
                IsExpiredButOtherwiseValid = false;
                CanGoNext = false;
                break;
        }

        EmitDerivedChanges();
    }

    private void EmitDerivedChanges()
    {
        OnPropertyChanged(nameof(HasValidatedInfo));
        OnPropertyChanged(nameof(HasValidationError));
        OnPropertyChanged(nameof(ExpiryDisplay));
    }
}
