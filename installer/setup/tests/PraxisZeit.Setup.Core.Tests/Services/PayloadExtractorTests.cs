using System.IO.Compression;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

public class PayloadExtractorTests : IDisposable
{
    private readonly string _tempDir;
    private readonly PayloadExtractor _extractor = new();

    public PayloadExtractorTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"praxiszeit-payload-{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
        GC.SuppressFinalize(this);
    }

    private string CreateTestZip(Dictionary<string, string> files)
    {
        var zipPath = Path.Combine(_tempDir, "test.zip");
        using var zip = ZipFile.Open(zipPath, ZipArchiveMode.Create);
        foreach (var (path, content) in files)
        {
            var entry = zip.CreateEntry(path.Replace('\\', '/'));
            using var writer = new StreamWriter(entry.Open());
            writer.Write(content);
        }
        return zipPath;
    }

    [Fact]
    public async Task ExtractAsync_fresh_install_extracts_all_files()
    {
        var zipPath = CreateTestZip(new()
        {
            ["app/backend/main.py"] = "# main",
            ["app/frontend/index.html"] = "<html/>",
            ["config/praxiszeit.conf.example"] = "[server]",
            ["praxiszeit-server.py"] = "# server",
        });

        var targetDir = Path.Combine(_tempDir, "install");
        await _extractor.ExtractAsync(zipPath, targetDir, isUpdate: false);

        File.Exists(Path.Combine(targetDir, "app", "backend", "main.py")).Should().BeTrue();
        File.Exists(Path.Combine(targetDir, "app", "frontend", "index.html")).Should().BeTrue();
        File.Exists(Path.Combine(targetDir, "config", "praxiszeit.conf.example")).Should().BeTrue();
        File.Exists(Path.Combine(targetDir, "praxiszeit-server.py")).Should().BeTrue();
    }

    [Fact]
    public async Task ExtractAsync_update_mode_skips_user_data_and_secrets()
    {
        var zipPath = CreateTestZip(new()
        {
            ["app/backend/new.py"] = "new",
            ["data/db/should-not-touch.txt"] = "zipped",
            ["config/praxiszeit.conf"] = "zipped-conf",
            ["config/.db-credentials"] = "zipped-creds",
            ["config/.secret-key"] = "zipped-secret",
            ["config/license.key"] = "zipped-license",
            ["config/ssl/cert.pem"] = "zipped-cert",
            ["logs/old.log"] = "zipped-log",
        });

        var targetDir = Path.Combine(_tempDir, "install");
        Directory.CreateDirectory(Path.Combine(targetDir, "data", "db"));
        await File.WriteAllTextAsync(Path.Combine(targetDir, "data", "db", "should-not-touch.txt"), "original");
        Directory.CreateDirectory(Path.Combine(targetDir, "config"));
        await File.WriteAllTextAsync(Path.Combine(targetDir, "config", "praxiszeit.conf"), "original-conf");

        await _extractor.ExtractAsync(zipPath, targetDir, isUpdate: true);

        // Neuer Code wurde kopiert
        File.Exists(Path.Combine(targetDir, "app", "backend", "new.py")).Should().BeTrue();

        // User-Daten unberuehrt
        File.ReadAllText(Path.Combine(targetDir, "data", "db", "should-not-touch.txt"))
            .Should().Be("original");
        File.ReadAllText(Path.Combine(targetDir, "config", "praxiszeit.conf"))
            .Should().Be("original-conf");

        // Secrets wurden nicht mal geschrieben
        File.Exists(Path.Combine(targetDir, "config", ".db-credentials")).Should().BeFalse();
        File.Exists(Path.Combine(targetDir, "config", ".secret-key")).Should().BeFalse();
        File.Exists(Path.Combine(targetDir, "config", "license.key")).Should().BeFalse();
        File.Exists(Path.Combine(targetDir, "config", "ssl", "cert.pem")).Should().BeFalse();
        File.Exists(Path.Combine(targetDir, "logs", "old.log")).Should().BeFalse();
    }

    [Fact]
    public async Task ExtractAsync_reports_progress()
    {
        var zipPath = CreateTestZip(new()
        {
            ["file1.txt"] = "1",
            ["file2.txt"] = "2",
            ["file3.txt"] = "3",
            ["file4.txt"] = "4",
        });

        var progressValues = new List<double>();
        var progress = new Progress<double>(v => progressValues.Add(v));

        await _extractor.ExtractAsync(zipPath, Path.Combine(_tempDir, "out"), isUpdate: false, progress);

        progressValues.Should().NotBeEmpty();
        progressValues.Last().Should().Be(1.0);
    }

    [Fact]
    public async Task ExtractAsync_throws_FileNotFoundException_for_missing_zip()
    {
        var act = () => _extractor.ExtractAsync(
            Path.Combine(_tempDir, "nonexistent.zip"),
            Path.Combine(_tempDir, "out"),
            isUpdate: false);

        await act.Should().ThrowAsync<FileNotFoundException>();
    }
}

public class ZipPathGuardTests
{
    private static readonly string Root = Path.Combine(Path.GetTempPath(), "pz-zipguard", "install");

    [Theory]
    [InlineData("../evil.txt")]
    [InlineData("..\\evil.txt")]
    [InlineData("app/../../evil.txt")]
    [InlineData("app\\..\\..\\Windows\\System32\\x.dll")]
    [InlineData("/etc/passwd")]
    [InlineData("C:/Windows/System32/x.dll")]
    [InlineData("C:x.dll")]
    public void ResolveEntryPath_rejects_entries_outside_the_target(string entry)
    {
        var act = () => ZipPathGuard.ResolveEntryPath(Root, entry);
        act.Should().Throw<InvalidDataException>();
    }

    [Fact]
    public void ResolveEntryPath_rejects_sibling_with_common_prefix()
    {
        // "install-evil" beginnt wie "install" - der Vergleich braucht den Trenner.
        var act = () => ZipPathGuard.ResolveEntryPath(Root, "../install-evil/x.txt");
        act.Should().Throw<InvalidDataException>();
    }

    [Theory]
    [InlineData("praxiszeit-server.py")]
    [InlineData("app/backend/main.py")]
    [InlineData("bin/python/./python.exe")]
    [InlineData("app/x/../y.txt")]
    public void ResolveEntryPath_keeps_regular_entries_below_the_target(string entry)
    {
        var full = ZipPathGuard.ResolveEntryPath(Root, entry);
        full.Should().StartWith(Path.GetFullPath(Root) + Path.DirectorySeparatorChar);
    }
}

public class PayloadExtractorZipSlipTests : IDisposable
{
    private readonly string _tempDir = Path.Combine(Path.GetTempPath(), $"praxiszeit-zipslip-{Guid.NewGuid():N}");

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
        GC.SuppressFinalize(this);
    }

    [Fact]
    public async Task ExtractAsync_refuses_zip_slip_and_writes_nothing_outside()
    {
        Directory.CreateDirectory(_tempDir);
        var zipPath = Path.Combine(_tempDir, "evil.zip");
        using (var zip = ZipFile.Open(zipPath, ZipArchiveMode.Create))
        {
            var entry = zip.CreateEntry("../outside.txt");
            using var writer = new StreamWriter(entry.Open());
            writer.Write("pwned");
        }
        var target = Path.Combine(_tempDir, "install");

        var act = () => new PayloadExtractor().ExtractAsync(zipPath, target, isUpdate: false);

        await act.Should().ThrowAsync<InvalidDataException>();
        File.Exists(Path.Combine(_tempDir, "outside.txt")).Should().BeFalse();
    }
}
