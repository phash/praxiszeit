using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// Wizard-Seite die Praxis-Stammdaten und Admin-Account abfragt.
/// Nur im Fresh-Install / Repair-Modus aktiv (Update behaelt die
/// existierende <c>praxiszeit.conf</c>).
///
/// <para>
/// Bei "Weiter" schreibt der Wizard mittels
/// <see cref="PraxisZeitConfigWriter"/> eine TOML-Config nach
/// <c>&lt;installDir&gt;\config\praxiszeit.conf</c>, BEVOR <c>setup.bat</c>
/// laeuft. Das Backend-Bootstrap (siehe <c>backend/app/main.py</c>
/// Lifespan) liest beim ersten Service-Start daraus den Admin und legt
/// ihn in der DB an — kein "BITTE_AENDERN"-Crash mehr.
/// </para>
/// </summary>
public sealed partial class ConfigPageViewModel : WizardPageBase
{
    public override string Key => "config";
    public override string Title => "Konfiguration";
    public override bool CanGoBack => true;
    public override string NextButtonText => "Weiter";

    public ObservableCollection<string> HolidayStates { get; } = new()
    {
        "Baden-Wuerttemberg",
        "Bayern",
        "Berlin",
        "Brandenburg",
        "Bremen",
        "Hamburg",
        "Hessen",
        "Mecklenburg-Vorpommern",
        "Niedersachsen",
        "Nordrhein-Westfalen",
        "Rheinland-Pfalz",
        "Saarland",
        "Sachsen",
        "Sachsen-Anhalt",
        "Schleswig-Holstein",
        "Thueringen",
    };

    [ObservableProperty]
    public partial string PracticeName { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string PracticeAddress { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string HolidayState { get; set; } = "Bayern";

    [ObservableProperty]
    public partial string AdminUsername { get; set; } = "admin";

    [ObservableProperty]
    public partial string AdminEmail { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string AdminFirstName { get; set; } = "Admin";

    [ObservableProperty]
    public partial string AdminLastName { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string AdminPassword { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string AdminPasswordRepeat { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string ValidationMessage { get; set; } = string.Empty;

    public bool HasValidationMessage => !string.IsNullOrEmpty(ValidationMessage);

    public ConfigPageViewModel()
    {
        // CanGoNext bleibt false bis alle Felder valide sind
        CanGoNext = false;
        Revalidate();
    }

    /// <summary>
    /// Schnappschuss der eingegebenen Werte fuer den ConfigWriter.
    /// </summary>
    public PraxisZeitConfigValues ToConfigValues() => new()
    {
        PracticeName = PracticeName.Trim(),
        PracticeAddress = PracticeAddress.Trim(),
        HolidayState = HolidayState,
        AdminUsername = AdminUsername.Trim(),
        AdminEmail = AdminEmail.Trim(),
        AdminFirstName = AdminFirstName.Trim(),
        AdminLastName = AdminLastName.Trim(),
        AdminPassword = AdminPassword,
    };

    private void Revalidate()
    {
        // Erst die zentrale Backend-kompatible Validierung
        var coreError = PraxisZeitConfigWriter.ValidateValues(ToConfigValues());
        if (coreError is not null)
        {
            ValidationMessage = coreError;
            CanGoNext = false;
            OnPropertyChanged(nameof(HasValidationMessage));
            return;
        }

        // Dann zusaetzliche UI-only Checks (Passwort-Wiederholung)
        if (AdminPassword != AdminPasswordRepeat)
        {
            ValidationMessage = "Passwörter stimmen nicht überein.";
            CanGoNext = false;
            OnPropertyChanged(nameof(HasValidationMessage));
            return;
        }

        if (string.IsNullOrWhiteSpace(AdminLastName))
        {
            ValidationMessage = "Admin-Nachname darf nicht leer sein.";
            CanGoNext = false;
            OnPropertyChanged(nameof(HasValidationMessage));
            return;
        }

        ValidationMessage = string.Empty;
        CanGoNext = true;
        OnPropertyChanged(nameof(HasValidationMessage));
    }

    partial void OnPracticeNameChanged(string value) => Revalidate();
    partial void OnAdminUsernameChanged(string value) => Revalidate();
    partial void OnAdminEmailChanged(string value) => Revalidate();
    partial void OnAdminLastNameChanged(string value) => Revalidate();
    partial void OnAdminPasswordChanged(string value) => Revalidate();
    partial void OnAdminPasswordRepeatChanged(string value) => Revalidate();
}
