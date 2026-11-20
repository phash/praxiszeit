using System.Net;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Text;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services.Reporting;

namespace PraxisZeit.Setup.Core.Tests.Services.Reporting;

public class ReportSenderTests
{
    private const string Key = "mrk_praxiszeit_test1234";

    private sealed class StubHandler(Func<HttpRequestMessage, int, CancellationToken, Task<HttpResponseMessage>> respond)
        : HttpMessageHandler
    {
        public List<Uri> Requests { get; } = [];
        public List<string> Bodies { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Requests.Add(request.RequestUri!);
            Bodies.Add(request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct));
            return await respond(request, Requests.Count, ct);
        }
    }

    private static HttpResponseMessage Json(HttpStatusCode status, string body) =>
        new(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };

    private static SetupReport Report() => SetupReport.Build(new SetupReportInput(
        "1.24.4", "Microsoft Windows 10.0.20348", "Update", "Installation fehlgeschlagen", "Protokoll prüfen.",
        ["09:40:02 FEHLER: robocopy exit=8"], new DateTime(2026, 11, 20, 9, 41, 7, DateTimeKind.Utc),
        "0f8fad5b-d9cb-469f-a165-70867728950e"));

    private sealed class ThrowingContent : HttpContent
    {
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) =>
            throw new IOException("body broke");

        protected override bool TryComputeLength(out long length)
        {
            length = 0;
            return false;
        }
    }

    [Fact]
    public async Task Created_WithUnreadableBody_StillOkWithoutRef()
    {
        var stub = new StubHandler((_, _, _) => Task.FromResult(
            new HttpResponseMessage(HttpStatusCode.Created) { Content = new ThrowingContent() }));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        result.Should().Be(new ReportSendResult(true, 201, null, null));
        stub.Requests.Should().ContainSingle();
    }

    [Fact]
    public async Task Created_WithInvalidJson_StillOkWithoutRef()
    {
        var stub = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.Created, "<html>")));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        result.Should().Be(new ReportSendResult(true, 201, null, null));
    }

    [Fact]
    public async Task Created_ReturnsRef()
    {
        var stub = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.Created,
            """{"id":"a1b2","ref":"PZ-2026-0042"}""")));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        result.Should().Be(new ReportSendResult(true, 201, "PZ-2026-0042", null));
        stub.Requests.Should().ContainSingle().Which.Should().Be(new Uri("https://report.mr-development.de/v1/reports"));
    }

    [Fact]
    public async Task SendsCredentialAndProtocol()
    {
        HttpRequestMessage? seen = null;
        var stub = new StubHandler((req, _, _) =>
        {
            seen = req;
            return Task.FromResult(Json(HttpStatusCode.Created, """{"ref":"PZ-1"}"""));
        });

        await new ReportSender(stub).SendAsync(Report(), Key);

        seen!.Method.Should().Be(HttpMethod.Post);
        seen.Content.Should().BeOfType<MultipartFormDataContent>();
        var body = stub.Bodies.Single();
        body.Should().Contain("name=\"credential\"").And.Contain(Key);
        body.Should().Contain("name=\"protocol\"").And.Contain("mrd-report-1");
        body.Should().Contain("name=\"component\"").And.Contain("name=\"install_id\"");
        body.Should().Contain("name=\"description\"");
    }

    [Fact]
    public async Task DnsFailure_FallsBackOnce()
    {
        var stub = new StubHandler((_, _, _) => throw new HttpRequestException(
            "Name or service not known", new SocketException((int)SocketError.HostNotFound)));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        stub.Requests.Should().HaveCount(2);
        stub.Requests[0].Host.Should().Be("report.mr-development.de");
        stub.Requests[1].Should().Be(new Uri("https://praxiszeit.mr-development.de/v1/reports"));
        result.Ok.Should().BeFalse();
        result.Status.Should().BeNull();
        result.Detail.Should().Be("Meldeserver nicht erreichbar.");
    }

    [Fact]
    public async Task TlsFailure_FallsBackAndSecondHostAnswers()
    {
        var stub = new StubHandler((_, n, _) => n == 1
            ? throw new HttpRequestException("SSL", new AuthenticationException("handshake"))
            : Task.FromResult(Json(HttpStatusCode.Created, """{"ref":"PZ-7"}""")));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        stub.Requests.Should().HaveCount(2);
        result.Ok.Should().BeTrue();
        result.Ref.Should().Be("PZ-7");
    }

    [Fact]
    public async Task ConnectionReset_NoFallback()
    {
        var stub = new StubHandler((_, _, _) => throw new HttpRequestException(
            "reset", new IOException("reset", new SocketException((int)SocketError.ConnectionReset))));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        stub.Requests.Should().ContainSingle();
        result.Ok.Should().BeFalse();
        result.Detail.Should().Be("Meldeserver nicht erreichbar.");
    }

    [Fact]
    public async Task BadRequest_ServerDetailGetsUpdateHint()
    {
        var withDetail = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.BadRequest,
            "{\"detail\":\"Unbekanntes Protokoll\"}")));
        var without = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.BadRequest, "{}")));

        (await new ReportSender(withDetail).SendAsync(Report(), Key)).Detail
            .Should().Be("Unbekanntes Protokoll – bitte PraxisZeit aktualisieren.");
        (await new ReportSender(without).SendAsync(Report(), Key)).Detail
            .Should().Be("Meldeprotokoll vom Server nicht unterstützt – bitte PraxisZeit aktualisieren.");
    }

    [Fact]
    public async Task ServerError_NoFallback()
    {
        var stub = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.InternalServerError, "oops")));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        stub.Requests.Should().ContainSingle();
        result.Should().Be(new ReportSendResult(false, 500, null, "Meldeserver-Fehler, bitte später erneut versuchen."));
    }

    [Fact]
    public async Task Timeout_ReturnsFailureWithoutThrowing()
    {
        var stub = new StubHandler(async (_, _, ct) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(30), ct);
            return Json(HttpStatusCode.Created, "{}");
        });

        var result = await new ReportSender(stub, TimeSpan.FromMilliseconds(200)).SendAsync(Report(), Key);

        stub.Requests.Should().ContainSingle();
        result.Ok.Should().BeFalse();
        result.Status.Should().BeNull();
        result.Detail.Should().Be("Meldeserver nicht erreichbar.");
    }

    [Fact]
    public async Task Status429_UsesDetail()
    {
        var stub = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.TooManyRequests, "{}")));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        result.Should().Be(new ReportSendResult(false, 429, null, "Zu viele Meldungen, bitte später erneut versuchen."));
    }

    [Fact]
    public async Task ServerDetail_IsUsedUnlessItContainsTheKey()
    {
        var withDetail = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.UnprocessableEntity,
            """{"detail":"Meldung enthält vermutlich Patientendaten"}""")));
        var leaking = new StubHandler((_, _, _) => Task.FromResult(Json(HttpStatusCode.Forbidden,
            $$"""{"detail":"bad key {{Key}}"}""")));

        (await new ReportSender(withDetail).SendAsync(Report(), Key)).Detail
            .Should().Be("Meldung enthält vermutlich Patientendaten");
        (await new ReportSender(leaking).SendAsync(Report(), Key)).Detail
            .Should().Be("Meldung abgelehnt (Meldeschlüssel, Produkt oder Installation gesperrt).");
    }

    [Fact]
    public async Task UnexpectedException_NeverThrows()
    {
        var stub = new StubHandler((_, _, _) => throw new InvalidOperationException("boom " + Key));

        var result = await new ReportSender(stub).SendAsync(Report(), Key);

        result.Ok.Should().BeFalse();
        result.Detail.Should().NotContain(Key);
    }
}
