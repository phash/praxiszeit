using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

/// <summary>Audit 2026-11-07 S3-01: Neuinstallation nie in einen fremden, befuellten Ordner.</summary>
public class InstallDirGuardTests : IDisposable
{
    private readonly string _tempDir = Path.Combine(Path.GetTempPath(), $"praxiszeit-guard-{Guid.NewGuid():N}");

    public InstallDirGuardTests() => Directory.CreateDirectory(_tempDir);

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
        GC.SuppressFinalize(this);
    }

    [Fact]
    public void New_folder_is_allowed()
    {
        InstallDirGuard.FreshTargetProblem(Path.Combine(_tempDir, "PraxisZeit")).Should().BeNull();
    }

    [Fact]
    public void Existing_empty_folder_is_allowed()
    {
        var dir = Path.Combine(_tempDir, "leer");
        Directory.CreateDirectory(dir);
        InstallDirGuard.FreshTargetProblem(dir).Should().BeNull();
    }

    [Fact]
    public void Folder_with_planted_file_is_refused_with_hint()
    {
        var dir = Path.Combine(_tempDir, "PraxisZeit");
        var sitePackages = Path.Combine(dir, "bin", "python", "Lib", "site-packages");
        Directory.CreateDirectory(sitePackages);
        File.WriteAllText(Path.Combine(sitePackages, "zz.pth"), "import os; os.system('x')");

        var problem = InstallDirGuard.FreshTargetProblem(dir);

        problem.Should().NotBeNull();
        problem.Should().Contain("nicht leer").And.Contain("anderen Ordner");
    }

    [Fact]
    public void Folder_with_only_an_empty_subfolder_is_refused()
    {
        var dir = Path.Combine(_tempDir, "PraxisZeit");
        Directory.CreateDirectory(Path.Combine(dir, "bin"));
        InstallDirGuard.FreshTargetProblem(dir).Should().NotBeNull();
    }

    [Fact]
    public void File_path_is_refused()
    {
        var file = Path.Combine(_tempDir, "datei");
        File.WriteAllText(file, "x");
        InstallDirGuard.FreshTargetProblem(file).Should().Contain("Datei");
    }

    [Fact]
    public void Drive_root_is_refused()
    {
        var root = Path.GetPathRoot(Path.GetFullPath(_tempDir))!;
        InstallDirGuard.FreshTargetProblem(root).Should().Contain("Stammverzeichnis");
    }

    [Fact]
    public void Empty_path_is_refused()
    {
        InstallDirGuard.FreshTargetProblem("  ").Should().NotBeNull();
    }

    [Fact]
    public void Root_hardening_sets_owner_first_and_cuts_inheritance_last()
    {
        var cmds = InstallDirGuard.RootHardeningCommands(@"C:\PraxisZeit");

        cmds[0].Should().Equal("icacls", @"C:\PraxisZeit", "/setowner", "*S-1-5-32-544");
        cmds[^1].Should().Equal("icacls", @"C:\PraxisZeit", "/inheritance:r");
        cmds.Should().OnlyContain(c => c[0] == "icacls" && c[1] == @"C:\PraxisZeit");
        // nur SIDs, nie lokalisierte Namen
        cmds.SelectMany(c => c.Skip(2)).Where(a => !a.StartsWith('/'))
            .Should().OnlyContain(a => a.StartsWith("*S-1-"));
        // Benutzer nur Lesen/Ausfuehren, SYSTEM + Administratoren Vollzugriff
        cmds.Should().ContainEquivalentOf(new[] { "icacls", @"C:\PraxisZeit", "/grant:r", "*S-1-5-32-545:(OI)(CI)RX" });
        cmds.Should().ContainEquivalentOf(new[] { "icacls", @"C:\PraxisZeit", "/grant:r", "*S-1-5-18:(OI)(CI)F" });
        cmds.Should().ContainEquivalentOf(new[] { "icacls", @"C:\PraxisZeit", "/remove:g", "*S-1-5-11" });
        // alle Grants vor dem Kappen der Vererbung
        var protect = cmds.Count - 1;
        cmds.Take(protect).Where(c => c[2] == "/grant:r").Should().HaveCount(4);
    }

    [Fact]
    public void Remove_failures_are_not_fatal_but_grants_are()
    {
        foreach (var c in InstallDirGuard.RootHardeningCommands(@"C:\PraxisZeit"))
        {
            InstallDirGuard.IsMandatory(c).Should().Be(c[2] != "/remove:g");
        }
    }
}
