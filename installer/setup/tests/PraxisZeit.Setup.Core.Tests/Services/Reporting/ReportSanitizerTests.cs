using System.Text.Json;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services.Reporting;

namespace PraxisZeit.Setup.Core.Tests.Services.Reporting;

/// <summary>
/// C#-Port der mrd-report-1-Bereinigung gegen dieselben Vektordateien wie das
/// Backend (backend/tests/data/mrd-report-1/sanitize-vectors.json und
/// backend/app/core/report_rules/praxiszeit-sanitize.json, per Link nach vectors/).
/// </summary>
public class ReportSanitizerTests
{
    private sealed record Case(string Id, string Input, string Expected, bool PatientData);

    private static readonly string VectorDir = Path.Combine(AppContext.BaseDirectory, "vectors");

    private static JsonDocument Load(string file) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(VectorDir, file)));

    private static Dictionary<string, Case> LoadCases(string file)
    {
        using var doc = Load(file);
        return doc.RootElement.GetProperty("cases").EnumerateArray()
            .Select(c => new Case(
                c.GetProperty("id").GetString()!,
                c.GetProperty("input").GetString()!,
                c.GetProperty("expected").GetString()!,
                c.GetProperty("patient_data").GetBoolean()))
            .ToDictionary(c => c.Id);
    }

    private static readonly Lazy<Dictionary<string, Case>> Shared = new(() => LoadCases("sanitize-vectors.json"));
    private static readonly Lazy<Dictionary<string, Case>> Pz = new(() => LoadCases("praxiszeit-sanitize.json"));

    public static TheoryData<string> SharedIds() => new(Shared.Value.Keys);
    public static TheoryData<string> PzIds() => new(Pz.Value.Keys);

    [Theory]
    [MemberData(nameof(SharedIds))]
    public void SharedVector_Passes(string id)
    {
        var c = Shared.Value[id];
        ReportSanitizer.Sanitize(c.Input).Should().Be(c.Expected, "sanitize(input) == expected");
        ReportSanitizer.Sanitize(c.Expected).Should().Be(c.Expected, "sanitize(expected) == expected");
        (ReportSanitizer.FindPatientData(c.Input).Count > 0).Should().Be(c.PatientData, "patient_data flag");
        ReportSanitizer.FindPatientData(c.Expected).Should().BeEmpty("find_patient_data(expected) is empty");
    }

    [Theory]
    [MemberData(nameof(PzIds))]
    public void PraxisZeitCase_Passes(string id)
    {
        var c = Pz.Value[id];
        var output = ReportSanitizer.SanitizePraxisZeit(c.Input);
        output.Should().Be(c.Expected);
        ReportSanitizer.SanitizePraxisZeit(output).Should().Be(output);
        (ReportSanitizer.FindPatientData(c.Input).Count > 0).Should().Be(c.PatientData);
    }

    [Theory]
    [MemberData(nameof(SharedIds))]
    public void PraxisZeitRules_KeepSharedGuarantees(string id)
    {
        var output = ReportSanitizer.SanitizePraxisZeit(Shared.Value[id].Input);
        ReportSanitizer.SanitizePraxisZeit(output).Should().Be(output);
        ReportSanitizer.FindPatientData(output).Should().BeEmpty();
    }

    [Fact]
    public void RuleCount_MatchesFiles()
    {
        using var shared = Load("sanitize-vectors.json");
        using var pz = Load("praxiszeit-sanitize.json");
        var sharedCount = shared.RootElement.GetProperty("rules").GetArrayLength();
        var pzCount = pz.RootElement.GetProperty("rules").GetArrayLength();

        ReportSanitizer.SharedRuleCount.Should().Be(sharedCount);
        ReportSanitizer.PraxisZeitRuleCount.Should().Be(pzCount);
        sharedCount.Should().Be(47);
        pzCount.Should().Be(7);
        Shared.Value.Should().HaveCount(shared.RootElement.GetProperty("cases").GetArrayLength());
    }

    [Theory]
    [InlineData("é192.168.1.1é", "é<ip>é")]
    [InlineData("xéBearer abc", "xéBearer <secret>")]
    public void WordBoundaries_AreAsciiOnly(string input, string expected)
    {
        // \b und Klassen sind ASCII-only (engine note): ein Nicht-ASCII-Buchstabe
        // vor dem Label zaehlt nicht als Wortzeichen.
        ReportSanitizer.Sanitize(input).Should().Be(expected);
    }
}
