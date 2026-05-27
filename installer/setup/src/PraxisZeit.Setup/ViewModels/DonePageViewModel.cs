using System;
using System.Diagnostics;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace PraxisZeit.Setup.ViewModels;

public sealed partial class DonePageViewModel : WizardPageBase
{
    public override string Key => "done";
    public override string Title => "Fertig";
    public override bool CanGoBack => false;
    public override string NextButtonText => "Schließen";

    [ObservableProperty]
    public partial bool Success { get; set; } = true;

    [ObservableProperty]
    public partial string Headline { get; set; } = "Fertig!";

    [ObservableProperty]
    public partial string Summary { get; set; } = "PraxisZeit wurde erfolgreich eingerichtet.";

    [ObservableProperty]
    public partial string BrowserUrl { get; set; } = "https://localhost/";

    /// <summary>
    /// True sobald der Webserver auf dem konfigurierten Port antwortet. Erst dann
    /// ist "Im Browser öffnen" aktiv. Der Windows-Dienst meldet sich bei SCM als
    /// "running", bevor uvicorn nach PG-Start + Migrationen wirklich bedient —
    /// ein sofortiger Klick wuerde sonst auf "nicht erreichbar" laufen.
    /// </summary>
    [ObservableProperty]
    public partial bool IsServerReady { get; set; }

    /// <summary>True solange wir auf den Webserver warten (zeigt "Server startet…").</summary>
    [ObservableProperty]
    public partial bool IsWaitingForServer { get; set; }

    public bool ShowBrowserCard => Success;
    public bool ShowErrorCard => !Success;

    public string BrowserButtonText => IsServerReady ? "Im Browser öffnen" : "Startet…";

    partial void OnSuccessChanged(bool value)
    {
        OnPropertyChanged(nameof(ShowBrowserCard));
        OnPropertyChanged(nameof(ShowErrorCard));
    }

    partial void OnIsServerReadyChanged(bool value)
    {
        OnPropertyChanged(nameof(BrowserButtonText));
        OpenBrowserCommand.NotifyCanExecuteChanged();
    }

    private bool CanOpenBrowser => IsServerReady;

    [RelayCommand(CanExecute = nameof(CanOpenBrowser))]
    private void OpenBrowser()
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = BrowserUrl,
                UseShellExecute = true,
            });
        }
        catch
        {
            // best-effort: wenn der Default-Browser fehlt zeigen wir
            // weiterhin nur die URL — kein Crash.
        }
    }

    /// <summary>
    /// Pollt <see cref="BrowserUrl"/> bis der Webserver antwortet und gibt dann
    /// den "Im Browser öffnen"-Button frei. Self-signed-Zertifikate werden
    /// akzeptiert (lokaler Readiness-Check gegen die eigene Instanz). Nach einem
    /// Timeout wird der Button trotzdem freigegeben, damit der User es manuell
    /// versuchen kann. Best-effort, wirft nie.
    /// </summary>
    public async Task WaitForServerAsync(CancellationToken ct = default)
    {
        IsServerReady = false;
        IsWaitingForServer = true;

        using var handler = new HttpClientHandler
        {
            // Lokaler Readiness-Check: self-signed Cert der eigenen Instanz akzeptieren.
            ServerCertificateCustomValidationCallback = (_, _, _, _) => true,
        };
        using var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(3) };

        var deadline = DateTime.UtcNow.AddSeconds(90);
        while (DateTime.UtcNow < deadline && !ct.IsCancellationRequested)
        {
            try
            {
                using var resp = await http.GetAsync(BrowserUrl, ct).ConfigureAwait(true);
                // Irgendeine HTTP-Antwort = der Webserver nimmt Verbindungen an
                // und liefert aus -> "öffnen" ist jetzt sinnvoll.
                IsWaitingForServer = false;
                IsServerReady = true;
                return;
            }
            catch
            {
                // Noch nicht erreichbar (Connection refused o.Ae.) — kurz warten.
            }

            try { await Task.Delay(1000, ct).ConfigureAwait(true); }
            catch (OperationCanceledException) { break; }
        }

        // Timeout/Abbruch: Button trotzdem freigeben (best-effort).
        IsWaitingForServer = false;
        IsServerReady = true;
    }
}
