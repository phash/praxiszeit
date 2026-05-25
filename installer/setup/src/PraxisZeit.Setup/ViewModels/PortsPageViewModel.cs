using System.Net.NetworkInformation;
using CommunityToolkit.Mvvm.ComponentModel;

namespace PraxisZeit.Setup.ViewModels;

/// <summary>
/// User waehlt HTTPS-Port (Default 443) und HTTP-Redirect-Port (Default 80).
/// Auf "Weiter" wird via <see cref="IPGlobalProperties"/> geprueft, ob die
/// gewaehlten Ports bereits von einem anderen Prozess gebunden sind —
/// das ist eine Warnung, kein Hard-Block (manche Konflikte sind auf
/// dem Setup-Server temporaer, z.B. ein anderer nginx der gleich gestoppt
/// wird).
/// </summary>
public sealed partial class PortsPageViewModel : WizardPageBase
{
    public override string Key => "ports";
    public override string Title => "Ports";

    [ObservableProperty]
    public partial int HttpsPort { get; set; } = 443;

    [ObservableProperty]
    public partial int HttpRedirectPort { get; set; } = 80;

    /// <summary>
    /// True = User hat einen HTTP-Redirect-Port gesetzt (>0). Default ja —
    /// wenn der User ihn auf 0 setzt, wird kein Redirect-Listener gestartet.
    /// </summary>
    [ObservableProperty]
    public partial bool EnableHttpRedirect { get; set; } = true;

    [ObservableProperty]
    public partial string? ValidationMessage { get; set; }

    [ObservableProperty]
    public partial string? PortConflictWarning { get; set; }

    public bool HasValidationMessage => !string.IsNullOrEmpty(ValidationMessage);
    public bool HasPortConflictWarning => !string.IsNullOrEmpty(PortConflictWarning);

    public PortsPageViewModel()
    {
        Validate();
    }

    partial void OnHttpsPortChanged(int value) => Validate();
    partial void OnHttpRedirectPortChanged(int value) => Validate();
    partial void OnEnableHttpRedirectChanged(bool value) => Validate();

    /// <summary>
    /// Effektiver Redirect-Port: 0 wenn der User die Checkbox abgewaehlt
    /// hat, sonst <see cref="HttpRedirectPort"/>. Wird vom ConfigWriter
    /// genutzt — 0 unterdrueckt den http_redirect_port-Eintrag.
    /// </summary>
    public int EffectiveHttpRedirectPort => EnableHttpRedirect ? HttpRedirectPort : 0;

    private void Validate()
    {
        // Range-Check: HTTPS muss 1..65535, HTTP 1..65535 wenn aktiv.
        if (HttpsPort is < 1 or > 65535)
        {
            ValidationMessage = $"HTTPS-Port muss zwischen 1 und 65535 liegen (aktuell: {HttpsPort}).";
            CanGoNext = false;
        }
        else if (EnableHttpRedirect && HttpRedirectPort is < 1 or > 65535)
        {
            ValidationMessage = $"HTTP-Redirect-Port muss zwischen 1 und 65535 liegen (aktuell: {HttpRedirectPort}).";
            CanGoNext = false;
        }
        else if (EnableHttpRedirect && HttpRedirectPort == HttpsPort)
        {
            ValidationMessage = "HTTPS-Port und HTTP-Redirect-Port duerfen nicht identisch sein.";
            CanGoNext = false;
        }
        else
        {
            ValidationMessage = null;
            CanGoNext = true;
            CheckPortConflicts();
        }

        OnPropertyChanged(nameof(HasValidationMessage));
        OnPropertyChanged(nameof(EffectiveHttpRedirectPort));
    }

    /// <summary>
    /// Reine Warnung — blockiert nicht. Nutzt
    /// <see cref="IPGlobalProperties.GetActiveTcpListeners"/> um zu sehen,
    /// ob auf einem der Ports schon jemand lauscht. Wir wollen das hier
    /// nicht hard-blocken, weil:
    /// - der existierende Listener kann ein zu beendender alter Service sein
    /// - die User-Maschine kann gerade unter Load sein und eine andere Bindung
    ///   haben die nach dem Reboot weg ist
    /// </summary>
    private void CheckPortConflicts()
    {
        try
        {
            var listeners = IPGlobalProperties.GetIPGlobalProperties()
                .GetActiveTcpListeners();
            var bound = listeners.Select(l => l.Port).ToHashSet();

            var conflicts = new List<string>();
            if (bound.Contains(HttpsPort))
            {
                conflicts.Add($"HTTPS-Port {HttpsPort}");
            }
            if (EnableHttpRedirect && bound.Contains(HttpRedirectPort))
            {
                conflicts.Add($"HTTP-Redirect-Port {HttpRedirectPort}");
            }

            PortConflictWarning = conflicts.Count == 0
                ? null
                : $"Achtung: {string.Join(" und ", conflicts)} ist bereits belegt. "
                  + "Beim Service-Start kann es zu Bind-Fehlern kommen — prüfen Sie laufende "
                  + "Webserver (IIS, nginx, Apache) oder wählen Sie andere Ports.";
        }
        catch
        {
            // Privilege-Problem (z.B. ohne Admin) oder Plattform-Spezifisches.
            // Kein Hard-Fail — Port-Check ist Komfort.
            PortConflictWarning = null;
        }
        OnPropertyChanged(nameof(HasPortConflictWarning));
    }
}
