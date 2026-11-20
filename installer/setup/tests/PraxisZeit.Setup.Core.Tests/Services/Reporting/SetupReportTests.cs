using FluentAssertions;
using PraxisZeit.Setup.Core.Services.Reporting;

namespace PraxisZeit.Setup.Core.Tests.Services.Reporting;

public class SetupReportTests
{
    private const string InstallId = "0f8fad5b-d9cb-469f-a165-70867728950e";
    private static readonly DateTime Now = new(2026, 11, 20, 9, 41, 7, DateTimeKind.Utc);

    private static SetupReportInput Input(IReadOnlyList<string> lines, string summary = "Bitte prüfen Sie das Protokoll.") =>
        new("1.24.4", "Microsoft Windows 10.0.20348", "Update", "Installation fehlgeschlagen", summary,
            lines, Now, InstallId);

    [Fact]
    public void Description_FollowsSpecLayoutAndIsSanitized()
    {
        var report = SetupReport.Build(Input(
        [
            @"09:40:01 Kopiere nach C:\Users\aschmidt\AppData\Local\Temp\PraxisZeit-Setup",
            "09:40:02 FEHLER: robocopy exit=8",
        ]));

        report.Description.Should().Be(string.Join("\n",
            "Der Setup-Assistent meldet einen fehlgeschlagenen Lauf.",
            "",
            "---- Kontext (automatisch) ----",
            "Produkt: PraxisZeit 1.24.4 (stable)",
            "System: Microsoft Windows 10.0.20348, Installationsart: native",
            "Zeit: 2026-11-20T09:41:07Z",
            "Fehler: Installation fehlgeschlagen – Bitte prüfen Sie das Protokoll.",
            "Protokoll (bereinigt, letzte 2 Zeilen):",
            @"09:40:01 Kopiere nach C:\Users\<user>\AppData\Local\Temp\PraxisZeit-Setup",
            "09:40:02 FEHLER: robocopy exit=8"));
        ReportSanitizer.SanitizePraxisZeit(report.Description).Should().Be(report.Description);
        report.Title.Should().Be("Setup fehlgeschlagen: Update 1.24.4");
    }

    [Fact]
    public void Description_IsSanitizedAsAWhole()
    {
        var report = SetupReport.Build(Input(["AUTH login_failed user=anna.schmidt ip=192.168.178.20"],
            summary: @"Protokoll unter C:\Users\Anna Schmidt\logs\setup.log"));

        report.Description.Should().Contain("user=<user> ip=<ip>");
        report.Description.Should().NotContain("anna").And.NotContain("Anna");
    }

    [Fact]
    public void Description_NeverExceeds20000()
    {
        var lines = Enumerable.Range(0, 200).Select(i => $"Zeile {i} " + new string('x', 2000)).ToList();

        var report = SetupReport.Build(Input(lines));

        report.Description.Length.Should().BeLessThanOrEqualTo(20000);
        report.Description.Should().Contain("Zeile 199 ", "newest lines are kept");
        report.Description.Should().NotContain("Zeile 0 ");
        var kept = report.Description.Split('\n').Count(l => l.StartsWith("Zeile "));
        report.Description.Should().Contain($"Protokoll (bereinigt, letzte {kept} Zeilen):");
        report.Fields["description"].Should().Be(report.Description);
    }

    [Fact]
    public void LogLines_AreCappedAt200()
    {
        var lines = Enumerable.Range(0, 300).Select(i => $"Zeile {i}").ToList();

        var report = SetupReport.Build(Input(lines));

        report.Description.Should().Contain("letzte 200 Zeilen").And.Contain("Zeile 299").And.NotContain("Zeile 99\n");
    }

    [Fact]
    public void Title_IsCutTo200()
    {
        var input = Input([]) with { AppVersion = "1.24.4-" + new string('z', 300) };

        var report = SetupReport.Build(input);

        report.Title.Length.Should().BeLessThanOrEqualTo(200);
        report.Title.Should().EndWith("…");
    }

    [Fact]
    public void Fields_HaveNoCredential()
    {
        var report = SetupReport.Build(Input(["x"]));

        report.Fields.Keys.Should().BeEquivalentTo(
            "protocol", "product", "component", "kind", "severity", "install_id",
            "title", "description", "app_version", "os");
        report.Fields["protocol"].Should().Be("mrd-report-1");
        report.Fields["product"].Should().Be("praxiszeit");
        report.Fields["component"].Should().Be("setup");
        report.Fields["kind"].Should().Be("crash");
        report.Fields["severity"].Should().Be("high");
        report.Fields["install_id"].Should().Be(InstallId);
        report.Fields["title"].Should().Be(report.Title);
        report.Fields["app_version"].Should().Be("1.24.4");
        report.Fields["os"].Should().Be("Microsoft Windows 10.0.20348");
        report.Fields.Keys.Should().NotContain(k => k.Contains("credential", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void FileText_ContainsNoKey()
    {
        var report = SetupReport.Build(Input(["09:40:02 FEHLER: robocopy exit=8"]));

        var text = report.ToFileText(Now);

        text.Should().NotContain("mrk_").And.NotContain("credential");
        var lines = text.Split('\n');
        lines[0].Should().Be("PraxisZeit – Problemmeldung (nicht gesendet)");
        lines[1].Should().Be("Erstellt: 2026-11-20T09:41:07.000Z");
        lines[2].Should().Be("Ziel: POST https://report.mr-development.de/v1/reports (mrd-report-1)");
        lines[3].Should().Be("app_version: 1.24.4");
        text.Should().Contain("\n\nTitel: Setup fehlgeschlagen: Update 1.24.4\n\n" + report.Description);
        text.Should().NotContain("\ntitle: ").And.NotContain("\ndescription: ");
    }

    [Fact]
    public void FileName_UsesLocalTimestamp()
    {
        SetupReport.FileName(new DateTime(2026, 11, 20, 9, 5, 0))
            .Should().Be("praxiszeit-setup-meldung-20261120-0905.txt");
    }
}
