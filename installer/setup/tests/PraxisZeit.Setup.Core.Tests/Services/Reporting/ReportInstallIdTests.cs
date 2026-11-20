using FluentAssertions;
using PraxisZeit.Setup.Core.Services.Reporting;

namespace PraxisZeit.Setup.Core.Tests.Services.Reporting;

public class ReportInstallIdTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), $"pz-installid-{Guid.NewGuid():N}");

    public void Dispose()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, recursive: true);
        GC.SuppressFinalize(this);
    }

    private string IdFile => Path.Combine(_dir, "PraxisZeit", "report-install-id");

    private static bool IsUuidV4(string s) =>
        Guid.TryParseExact(s, "D", out _) && s == s.ToLowerInvariant() && s[14] == '4';

    [Fact]
    public void CreatesOnceAndReuses()
    {
        var first = ReportInstallId.GetOrCreate(_dir);
        var second = ReportInstallId.GetOrCreate(_dir);

        IsUuidV4(first).Should().BeTrue();
        second.Should().Be(first);
        File.ReadAllText(IdFile).Trim().Should().Be(first);
    }

    [Fact]
    public void InvalidContentIsReplaced()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(IdFile)!);
        File.WriteAllText(IdFile, "kaputt");

        var id = ReportInstallId.GetOrCreate(_dir);

        IsUuidV4(id).Should().BeTrue();
        File.ReadAllText(IdFile).Trim().Should().Be(id);
    }

    [Fact]
    public void UnwritableLocation_StillReturnsAnId()
    {
        // Eine Datei an der Stelle des Ordners: weder lesbar noch anlegbar.
        Directory.CreateDirectory(_dir);
        File.WriteAllText(Path.Combine(_dir, "PraxisZeit"), "");

        IsUuidV4(ReportInstallId.GetOrCreate(_dir)).Should().BeTrue();
    }

    [Fact]
    public void SymlinkedFile_IsNeverWrittenThrough()
    {
        var victim = Path.Combine(_dir, "victim.txt");
        Directory.CreateDirectory(Path.GetDirectoryName(IdFile)!);
        File.WriteAllText(victim, "original");
        File.CreateSymbolicLink(IdFile, victim);

        IsUuidV4(ReportInstallId.GetOrCreate(_dir)).Should().BeTrue();

        File.ReadAllText(victim).Should().Be("original");
    }

    [Fact]
    public void SymlinkedFolder_IsAvoided()
    {
        var victimDir = Path.Combine(_dir, "victim");
        Directory.CreateDirectory(victimDir);
        Directory.CreateSymbolicLink(Path.Combine(_dir, "PraxisZeit"), victimDir);

        IsUuidV4(ReportInstallId.GetOrCreate(_dir)).Should().BeTrue();

        Directory.EnumerateFileSystemEntries(victimDir).Should().BeEmpty();
    }

    [Theory]
    [InlineData(null, null)]
    [InlineData("", null)]
    [InlineData("   ", null)]
    [InlineData(" mrk_praxiszeit_abc ", "mrk_praxiszeit_abc")]
    public void ReportKey_NormalizesEmptyToNull(string? raw, string? expected)
    {
        ReportKey.Normalize(raw).Should().Be(expected);
    }

    [Fact]
    public void ReportKey_AssemblyWithoutMetadata_IsNull()
    {
        ReportKey.FromAssembly(typeof(ReportInstallIdTests).Assembly).Should().BeNull();
        ReportKey.FromAssembly(null).Should().BeNull();
    }
}
