using System;
using System.Diagnostics;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using PraxisZeit.Setup.Core.Services.Reporting;

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

    // ---- Problem melden (#557, mrd-report-1) --------------------------------

    public const string BoardUrl = "https://praxiszeit.mr-development.de/app/bugs?product=praxiszeit";
    public const string SendFailedText = "Senden fehlgeschlagen – als Datei speichern?";
    public static readonly string NoKeyHint =
        $"Bitte speichern Sie die Meldung als Datei und senden Sie sie an {LicensePageViewModel.LicenseContact}.";

    private SetupReport? _report;
    private string? _reportKey;
    private ReportSender _sender = new();

    /// <summary>
    /// Speichert Text unter einem vom Nutzer gewählten Namen (Dateidialog der
    /// View, <c>StorageProvider.SaveFilePickerAsync</c>). Rückgabe: gespeichert ja/nein.
    /// </summary>
    public Func<string, string, Task<bool>>? SaveFileHandler { get; set; }

    /// <summary>Aktionen „An Entwickler schicken“ / „Als Datei speichern“ nur nach einem Fehler.</summary>
    public bool ShowReportActions => !Success && _report is not null;

    public string NoKeyHintText => NoKeyHint;

    public bool HasReportKey => _reportKey is not null;

    /// <summary>Ohne eingebauten Meldeschlüssel: Hinweis auf Datei + Mail.</summary>
    public bool ShowNoKeyHint => ShowReportActions && !HasReportKey;

    [ObservableProperty]
    public partial string ReportPreviewText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string? ReportStatus { get; set; }

    [ObservableProperty]
    public partial string? ReportDetail { get; set; }

    [ObservableProperty]
    public partial bool ReportSent { get; set; }

    [ObservableProperty]
    public partial bool IsSendingReport { get; set; }

    public bool CanSendReport => HasReportKey && !ReportSent && !IsSendingReport && _report is not null;

    /// <summary>
    /// Meldung für den fehlgeschlagenen Lauf vorbereiten. <paramref name="key"/>
    /// bleibt privat (nie in Vorschau, Status oder Datei).
    /// </summary>
    public void PrepareReport(SetupReport report, string? key, ReportSender? sender = null)
    {
        _report = report;
        _reportKey = ReportKey.Normalize(key);
        _sender = sender ?? new ReportSender();
        ReportSent = false;
        ReportStatus = null;
        ReportDetail = null;
        ReportPreviewText = report.ToPreviewText(HasReportKey);
        RaiseReportChanged();
    }

    private void RaiseReportChanged()
    {
        OnPropertyChanged(nameof(ShowReportActions));
        OnPropertyChanged(nameof(HasReportKey));
        OnPropertyChanged(nameof(ShowNoKeyHint));
        OnPropertyChanged(nameof(CanSendReport));
        SendReportCommand.NotifyCanExecuteChanged();
        SaveReportCommand.NotifyCanExecuteChanged();
    }

    partial void OnReportSentChanged(bool value) => RaiseReportChanged();

    partial void OnIsSendingReportChanged(bool value) => RaiseReportChanged();

    [RelayCommand(CanExecute = nameof(CanSendReport))]
    private async Task SendReportAsync()
    {
        if (_report is null || _reportKey is null || IsSendingReport || ReportSent)
        {
            return;
        }
        IsSendingReport = true;
        ReportStatus = "Meldung wird gesendet …";
        ReportDetail = null;
        try
        {
            var result = await _sender.SendAsync(_report, _reportKey).ConfigureAwait(true);
            if (result.Ok)
            {
                ReportSent = true;
                ReportStatus = string.IsNullOrEmpty(result.Ref) ? "Meldung gesendet." : $"Meldung gesendet: {result.Ref}.";
            }
            else
            {
                ReportStatus = SendFailedText;
                ReportDetail = result.Detail;
            }
        }
        finally
        {
            IsSendingReport = false;
        }
    }

    private bool CanSaveReport => _report is not null;

    [RelayCommand(CanExecute = nameof(CanSaveReport))]
    private async Task SaveReportAsync()
    {
        if (_report is null || SaveFileHandler is null)
        {
            return;
        }
        try
        {
            var saved = await SaveFileHandler(SetupReport.FileName(DateTime.Now), _report.ToFileText())
                .ConfigureAwait(true);
            if (saved && !ReportSent)
            {
                ReportStatus = "Meldung als Datei gespeichert.";
                ReportDetail = null;
            }
        }
        catch (Exception)
        {
            ReportStatus = "Datei konnte nicht gespeichert werden.";
        }
    }

    [RelayCommand]
    private void OpenBoard()
    {
        try
        {
            Process.Start(new ProcessStartInfo { FileName = BoardUrl, UseShellExecute = true });
        }
        catch
        {
            // best-effort
        }
    }

    public string BrowserButtonText => IsServerReady ? "Im Browser öffnen" : "Startet…";

    partial void OnSuccessChanged(bool value)
    {
        OnPropertyChanged(nameof(ShowBrowserCard));
        OnPropertyChanged(nameof(ShowErrorCard));
        RaiseReportChanged();
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
