using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Text;
using System.Text.Json;

namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>Ergebnis eines Sendeversuchs. <see cref="Detail"/> ist ein deutscher Hinweistext, nie mit Schlüssel.</summary>
public sealed record ReportSendResult(bool Ok, int? Status, string? Ref, string? Detail);

/// <summary>
/// Sendet eine <see cref="SetupReport"/> per mrd-report-1 (<c>POST /v1/reports</c>,
/// multipart, alle Werte als Formularfelder plus <c>credential</c>). Verhalten wie
/// <c>backend/app/services/report_client.py</c>: ein einziger Ausweichversuch auf
/// <see cref="FallbackBase"/> nur bei einem DNS- oder TLS-Fehler beim Verbindungsaufbau
/// (keine Antwort; nie bei HTTP-Status, Verbindungsabbruch oder Timeout), ein
/// Gesamtbudget von 15 s inklusive Ausweichversuch, keine Weiterleitungen. Wirft nie.
/// </summary>
public sealed class ReportSender(HttpMessageHandler? handler = null, TimeSpan? timeout = null)
{
    public const string PrimaryBase = "https://report.mr-development.de";
    public const string FallbackBase = "https://praxiszeit.mr-development.de";
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(15);

    internal const string Unreachable = "Meldeserver nicht erreichbar.";
    internal const string DefaultDetail = "Meldeserver-Fehler, bitte später erneut versuchen.";
    private const int DetailMax = 300;

    private static readonly Dictionary<int, string> StatusDetail = new()
    {
        [400] = "Meldeprotokoll vom Server nicht unterstützt – bitte PraxisZeit aktualisieren.",
        [403] = "Meldung abgelehnt (Meldeschlüssel, Produkt oder Installation gesperrt).",
        [413] = "Anhang zu groß.",
        [422] = "Meldung vom Server abgelehnt.",
        [429] = "Zu viele Meldungen, bitte später erneut versuchen.",
    };

    private readonly TimeSpan _timeout = timeout ?? DefaultTimeout;

    public async Task<ReportSendResult> SendAsync(SetupReport report, string key, CancellationToken ct = default)
    {
        try
        {
            return await SendCoreAsync(report, key, ct).ConfigureAwait(false);
        }
        catch (Exception)
        {
            // Meldeweg darf das Setup nie stören; keine Ausnahmetexte (könnten Werte enthalten).
            return new ReportSendResult(false, null, null, Unreachable);
        }
    }

    private async Task<ReportSendResult> SendCoreAsync(SetupReport report, string key, CancellationToken ct)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(_timeout);

        var ownHandler = handler is null;
        var h = handler ?? new SocketsHttpHandler { AllowAutoRedirect = false };
        using var http = new HttpClient(h, disposeHandler: ownHandler) { Timeout = Timeout.InfiniteTimeSpan };

        string[] urls = [$"{PrimaryBase}/v1/reports", $"{FallbackBase}/v1/reports"];
        for (var i = 0; i < urls.Length; i++)
        {
            using var content = BuildContent(report, key);
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, urls[i]) { Content = content };
                // Nur Header abwarten: ein unlesbarer Körper nach 201 darf die Meldung nicht als „nicht gesendet“ zeigen.
                using var resp = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token)
                    .ConfigureAwait(false);
                return await InterpretAsync(resp, key, deadline.Token).ConfigureAwait(false);
            }
            catch (HttpRequestException ex) when (!deadline.IsCancellationRequested)
            {
                if (IsDnsOrTlsError(ex) && i + 1 < urls.Length)
                {
                    continue;
                }
                return new ReportSendResult(false, null, null, Unreachable);
            }
            catch (OperationCanceledException)
            {
                return new ReportSendResult(false, null, null, Unreachable);
            }
        }
        return new ReportSendResult(false, null, null, Unreachable);
    }

    private static MultipartFormDataContent BuildContent(SetupReport report, string key)
    {
        var content = new MultipartFormDataContent();
        foreach (var (name, value) in report.Fields)
        {
            if (name.Equals("credential", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            content.Add(Part(name, value));
        }
        content.Add(Part("credential", key));
        return content;
    }

    private static StringContent Part(string name, string value)
    {
        var part = new StringContent(value, Encoding.UTF8);
        // RFC 7578: Feldname in Anführungszeichen.
        part.Headers.ContentDisposition = new ContentDispositionHeaderValue("form-data") { Name = $"\"{name}\"" };
        return part;
    }

    /// <summary>
    /// True, wenn in der Ursachenkette ein Namensauflösungs- (HostNotFound, NoData,
    /// TryAgain) oder TLS-Fehler steckt. Nur für <see cref="HttpRequestException"/>
    /// ohne Antwort aufrufen.
    /// </summary>
    public static bool IsDnsOrTlsError(HttpRequestException ex)
    {
        if (ex.HttpRequestError is HttpRequestError.NameResolutionError or HttpRequestError.SecureConnectionError)
        {
            return true;
        }
        for (Exception? cur = ex.InnerException; cur is not null; cur = cur.InnerException)
        {
            switch (cur)
            {
                case SocketException { SocketErrorCode: SocketError.HostNotFound or SocketError.NoData or SocketError.TryAgain }:
                case AuthenticationException:
                    return true;
            }
        }
        return false;
    }

    private static async Task<ReportSendResult> InterpretAsync(HttpResponseMessage resp, string key, CancellationToken ct)
    {
        var status = (int)resp.StatusCode;
        string body;
        try
        {
            body = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        }
        catch (Exception)
        {
            body = string.Empty;
        }
        JsonElement? json = null;
        try
        {
            using var doc = JsonDocument.Parse(body);
            json = doc.RootElement.Clone();
        }
        catch (JsonException)
        {
        }

        if (status == 201)
        {
            return new ReportSendResult(true, 201, StringProp(json, "ref"), null);
        }
        var detail = StringProp(json, "detail");
        if (string.IsNullOrWhiteSpace(detail) || (key.Length > 0 && detail.Contains(key, StringComparison.Ordinal)))
        {
            detail = StatusDetail.GetValueOrDefault(status, DefaultDetail);
        }
        return new ReportSendResult(false, status, null, detail.Length > DetailMax ? detail[..DetailMax] : detail);
    }

    private static string? StringProp(JsonElement? json, string name) =>
        json is { ValueKind: JsonValueKind.Object } obj
        && obj.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String
            ? v.GetString()
            : null;
}
