using System.Net;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

/// <summary>
/// Deckt die Rechte-vor-Inhalt-Regel fuer vertrauliche Dateien ab.
///
/// <para>
/// Die Assertions laufen plattformabhaengig: unter Unix wird der Dateimodus
/// geprueft (0600), unter Windows die ACL (keine Vererbung, nur SYSTEM +
/// Administratoren). So testet dieselbe Testklasse auf dem Linux-CI-Lauf und
/// auf einer Windows-Maschine jeweils das, was dort gilt.
/// </para>
/// </summary>
public class SecretFileTests : IDisposable
{
    private readonly string _tempDir;

    public SecretFileTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"praxiszeit-secret-{Guid.NewGuid():N}");
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

    /// <summary>
    /// Zentrale Zusicherung: die Datei ist fuer niemanden ausser dem
    /// Eigentuemer (Unix) bzw. SYSTEM + Administratoren (Windows) zugaenglich.
    /// </summary>
    private static void AssertRestricted(string path)
    {
        File.Exists(path).Should().BeTrue();
        if (OperatingSystem.IsWindows())
        {
            AssertRestrictedWindows(path);
            return;
        }
        var mode = File.GetUnixFileMode(path);
        mode.Should().Be(UnixFileMode.UserRead | UnixFileMode.UserWrite,
            "eine vertrauliche Datei darf weder Gruppe noch Andere lesen lassen");
    }

    [SupportedOSPlatform("windows")]
    private static void AssertRestrictedWindows(string path)
    {
        var rules = new FileInfo(path)
            .GetAccessControl()
            .GetAccessRules(includeExplicit: true, includeInherited: true, typeof(SecurityIdentifier));

        var sids = rules.Cast<FileSystemAccessRule>()
            .Select(r => ((SecurityIdentifier)r.IdentityReference).Value)
            .ToList();

        var broad = new[]
        {
            new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null).Value,
            new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null).Value,
            new SecurityIdentifier(WellKnownSidType.WorldSid, null).Value,
        };
        sids.Should().NotIntersectWith(broad,
            "Users / Authentifizierte Benutzer / Jeder duerfen kein Recht auf der Datei haben");

        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null).Value;
        sids.Should().Contain(system,
            "das Dienstkonto (LocalSystem) muss die Datei weiterhin lesen koennen");
    }

    [Fact]
    public async Task WriteAllTextAsync_creates_file_with_restricted_permissions()
    {
        var path = Path.Combine(_tempDir, "sub", "secret.conf");
        await SecretFile.WriteAllTextAsync(path, "password = \"geheim\"\n", new UTF8Encoding(false));

        AssertRestricted(path);
        (await File.ReadAllTextAsync(path)).Should().Be("password = \"geheim\"\n");
    }

    [Fact]
    public void WriteAllText_creates_file_with_restricted_permissions()
    {
        var path = Path.Combine(_tempDir, "sync-secret.conf");
        SecretFile.WriteAllText(path, "geheim", new UTF8Encoding(false));

        AssertRestricted(path);
        File.ReadAllText(path).Should().Be("geheim");
    }

    [Fact]
    public void Create_restricts_permissions_before_the_caller_writes_anything()
    {
        var path = Path.Combine(_tempDir, "ordering.conf");
        using (var stream = SecretFile.Create(path))
        {
            // Genau hier steckt der Fix: die Datei existiert schon, ist aber
            // noch leer — und traegt bereits die eingeschraenkten Rechte.
            AssertRestricted(path);
            stream.Write("nachtraeglich"u8);
        }
        AssertRestricted(path);
    }

    [Fact]
    public void EnsureRestricted_repairs_an_existing_world_readable_file()
    {
        // Bestandsinstallation: mit Standardrechten angelegt.
        var path = Path.Combine(_tempDir, "legacy.conf");
        File.WriteAllText(path, "password = \"alt\"\n");
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path,
                UnixFileMode.UserRead | UnixFileMode.UserWrite |
                UnixFileMode.GroupRead | UnixFileMode.OtherRead);
        }

        SecretFile.EnsureRestricted(path);

        AssertRestricted(path);
        File.ReadAllText(path).Should().Be("password = \"alt\"\n",
            "die Reparatur darf den Inhalt nicht anfassen");
    }

    [Fact]
    public void EnsureRestricted_is_a_no_op_for_a_missing_file()
    {
        var act = () => SecretFile.EnsureRestricted(Path.Combine(_tempDir, "gibtsnicht.conf"));
        act.Should().NotThrow();
    }

    [Fact]
    public async Task Overwriting_an_existing_loose_file_restricts_it_first()
    {
        var path = Path.Combine(_tempDir, "overwrite.conf");
        File.WriteAllText(path, "alt");
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path,
                UnixFileMode.UserRead | UnixFileMode.UserWrite |
                UnixFileMode.GroupRead | UnixFileMode.OtherRead);
        }

        await SecretFile.WriteAllTextAsync(path, "neu-und-geheim", new UTF8Encoding(false));

        AssertRestricted(path);
        (await File.ReadAllTextAsync(path)).Should().Be("neu-und-geheim");
    }

    [Fact]
    public async Task ConfigWriter_writes_the_config_with_restricted_permissions()
    {
        var path = Path.Combine(_tempDir, "config", "praxiszeit.conf");
        await PraxisZeitConfigWriter.WriteAsync(path, new PraxisZeitConfigValues
        {
            PracticeName = "Testpraxis",
            AdminEmail = "admin@example.de",
            AdminPassword = "EinLangesPasswort1!",
        });

        AssertRestricted(path);
        // Inhalt weiterhin korrekt: UTF-8 OHNE BOM (F-053).
        var raw = await File.ReadAllBytesAsync(path);
        raw.Take(3).Should().NotEqual([(byte)0xEF, (byte)0xBB, (byte)0xBF]);
        Encoding.UTF8.GetString(raw).Should().Contain("EinLangesPasswort1!");
    }

    [Fact]
    public async Task License_file_is_written_with_restricted_permissions()
    {
        var configDir = Path.Combine(_tempDir, "lic");
        await PraxisZeitConfigWriter.WriteLicenseFileAsync(configDir, "eyJhbGciOiJFZERTQSJ9.token.sig");

        AssertRestricted(Path.Combine(configDir, "license.key"));
    }

    [Fact]
    public void CertificateGenerator_restricts_the_private_key_but_not_the_certificate()
    {
        var result = new CertificateGenerator()
            .Generate(IPAddress.Parse("192.168.1.5"), "Praxis Test", Path.Combine(_tempDir, "ssl"));

        AssertRestricted(result.KeyPath);
        // Das Zertifikat ist oeffentlich — es darf (und soll) lesbar bleiben,
        // sonst schlagen Diagnose-Werkzeuge des Betreibers ohne Not fehl.
        File.Exists(result.CertPath).Should().BeTrue();
        File.ReadAllText(result.CertPath).Should().Contain("BEGIN CERTIFICATE");
    }
}
