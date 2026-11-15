using FluentAssertions;
using PraxisZeit.Setup.Core.Models;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

public class UpdateDetectorTests : IDisposable
{
    private readonly string _tempDir;
    private readonly UpdateDetector _detector = new();

    public UpdateDetectorTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"praxiszeit-detect-{Guid.NewGuid():N}");
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

    [Fact]
    public void DetectCurrentVersion_returns_null_for_empty_directory()
    {
        _detector.DetectCurrentVersion(_tempDir).Should().BeNull();
    }

    [Fact]
    public void DetectCurrentVersion_returns_null_for_nonexistent_directory()
    {
        _detector.DetectCurrentVersion(Path.Combine(_tempDir, "does-not-exist")).Should().BeNull();
    }

    [Fact]
    public void DetectCurrentVersion_reads_APP_VERSION_from_native_install_layout()
    {
        var updaterDir = Path.Combine(_tempDir, "app", "backend", "app", "core");
        Directory.CreateDirectory(updaterDir);
        File.WriteAllText(
            Path.Combine(updaterDir, "updater.py"),
            """""
            """PraxisZeit Update Checker"""

            # Current application version
            APP_VERSION = "1.3.4"

            _ALLOWED_UPDATE_HOSTS = {"updates.praxiszeit.de"}
            """"");

        _detector.DetectCurrentVersion(_tempDir).Should().Be("1.3.4");
    }

    [Fact]
    public void DetectCurrentVersion_reads_APP_VERSION_from_dev_layout()
    {
        var updaterDir = Path.Combine(_tempDir, "backend", "app", "core");
        Directory.CreateDirectory(updaterDir);
        File.WriteAllText(
            Path.Combine(updaterDir, "updater.py"),
            "APP_VERSION = \"2.0.0-alpha\"\n");

        _detector.DetectCurrentVersion(_tempDir).Should().Be("2.0.0-alpha");
    }

    [Fact]
    public void DetectCurrentVersion_returns_unknown_for_legacy_install()
    {
        // Nur praxiszeit-server.py, kein updater.py (pre-1.3.0)
        File.WriteAllText(Path.Combine(_tempDir, "praxiszeit-server.py"), "# legacy");

        _detector.DetectCurrentVersion(_tempDir).Should().Be("unknown");
    }

    [Fact]
    public void DetectMode_returns_FreshInstall_when_no_current_version()
    {
        _detector.DetectMode(_tempDir, "1.4.0").Should().Be(InstallMode.FreshInstall);
    }

    [Fact]
    public void DetectMode_returns_Update_when_versions_differ()
    {
        var updaterDir = Path.Combine(_tempDir, "app", "backend", "app", "core");
        Directory.CreateDirectory(updaterDir);
        File.WriteAllText(Path.Combine(updaterDir, "updater.py"), "APP_VERSION = \"1.3.4\"\n");

        _detector.DetectMode(_tempDir, "1.4.0").Should().Be(InstallMode.Update);
    }

    [Fact]
    public void DetectMode_returns_Repair_when_versions_match()
    {
        var updaterDir = Path.Combine(_tempDir, "app", "backend", "app", "core");
        Directory.CreateDirectory(updaterDir);
        File.WriteAllText(Path.Combine(updaterDir, "updater.py"), "APP_VERSION = \"1.4.0\"\n");
        Directory.CreateDirectory(Path.Combine(_tempDir, "config"));
        File.WriteAllText(Path.Combine(_tempDir, "config", ".db-credentials"), "x");

        _detector.DetectMode(_tempDir, "1.4.0").Should().Be(InstallMode.Repair);
    }

    [Fact]
    public void DetectMode_returns_Resume_when_same_version_but_database_never_initialized()
    {
        // Review 2026-11-15: Erstinstallation brach nach dem Kopieren ab
        // (setup.bat/initdb). Ohne config\.db-credentials kann der
        // Update-Wizard nichts reparieren - die Erstinstallation muss weiterlaufen.
        var updaterDir = Path.Combine(_tempDir, "app", "backend", "app", "core");
        Directory.CreateDirectory(updaterDir);
        File.WriteAllText(Path.Combine(updaterDir, "updater.py"), "APP_VERSION = \"1.4.0\"\n");

        _detector.DetectMode(_tempDir, "1.4.0").Should().Be(InstallMode.Resume);
    }

    [Fact]
    public void DetectMode_never_resumes_into_a_folder_not_owned_by_administrators()
    {
        // Sicherheitsreview 2026-11-15: ein Nicht-Admin legt C:\praxiszeit mit
        // passender updater.py an - "Fortsetzen" haette S3-01 umgangen.
        var updaterDir = Path.Combine(_tempDir, "app", "backend", "app", "core");
        Directory.CreateDirectory(updaterDir);
        File.WriteAllText(Path.Combine(updaterDir, "updater.py"), "APP_VERSION = \"1.4.0\"\n");

        new UpdateDetector(_ => false).DetectMode(_tempDir, "1.4.0").Should().Be(InstallMode.FreshInstall);
    }
}
