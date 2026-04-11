using System.Net;
using System.Security.Cryptography.X509Certificates;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

public class CertificateGeneratorTests : IDisposable
{
    private readonly string _tempDir;
    private readonly CertificateGenerator _generator = new();

    public CertificateGeneratorTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"praxiszeit-test-{Guid.NewGuid():N}");
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
    public void Generate_writes_cert_and_key_files()
    {
        var ip = IPAddress.Parse("192.168.1.5");
        var result = _generator.Generate(ip, "Praxis Test", _tempDir);

        File.Exists(result.CertPath).Should().BeTrue();
        File.Exists(result.KeyPath).Should().BeTrue();
        result.Thumbprint.Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public void Generate_produces_valid_x509_pem()
    {
        var ip = IPAddress.Parse("10.0.0.20");
        var result = _generator.Generate(ip, "Test Practice", _tempDir);

        var pem = File.ReadAllText(result.CertPath);
        pem.Should().Contain("-----BEGIN CERTIFICATE-----");
        pem.Should().Contain("-----END CERTIFICATE-----");

        // Parseable durch X509Certificate2
        using var cert = X509CertificateLoader.LoadCertificateFromFile(result.CertPath);
        cert.Subject.Should().Contain("10.0.0.20");
        cert.Subject.Should().Contain("Test Practice");
    }

    [Fact]
    public void Generate_sets_subject_alt_name_with_ip_and_localhost()
    {
        var ip = IPAddress.Parse("192.168.178.50");
        var result = _generator.Generate(ip, "Praxis XY", _tempDir);

        using var cert = X509CertificateLoader.LoadCertificateFromFile(result.CertPath);
        var san = cert.Extensions.OfType<X509SubjectAlternativeNameExtension>().SingleOrDefault();

        san.Should().NotBeNull();
        var dnsNames = san!.EnumerateDnsNames().ToList();
        var ipAddresses = san.EnumerateIPAddresses().ToList();

        dnsNames.Should().Contain("localhost");
        ipAddresses.Should().Contain(IPAddress.Loopback);
        ipAddresses.Should().Contain(ip);
    }

    [Fact]
    public void Generate_produces_valid_pkcs8_private_key_pem()
    {
        var result = _generator.Generate(IPAddress.Parse("127.0.0.1"), "Test", _tempDir);

        var keyPem = File.ReadAllText(result.KeyPath);
        keyPem.Should().Contain("-----BEGIN PRIVATE KEY-----");
        keyPem.Should().Contain("-----END PRIVATE KEY-----");

        // Key muss re-importierbar sein
        using var rsa = System.Security.Cryptography.RSA.Create();
        rsa.ImportFromPem(keyPem);
        rsa.KeySize.Should().Be(2048);
    }

    [Fact]
    public void Generate_sets_validity_to_ten_years_by_default()
    {
        var result = _generator.Generate(IPAddress.Parse("127.0.0.1"), "Test", _tempDir);

        using var cert = X509CertificateLoader.LoadCertificateFromFile(result.CertPath);
        var validityDays = (cert.NotAfter - cert.NotBefore).TotalDays;
        validityDays.Should().BeGreaterThan(3600); // 10 years minus margin
    }

    [Fact]
    public void Generate_respects_custom_validity()
    {
        var result = _generator.Generate(
            IPAddress.Parse("127.0.0.1"),
            "Test",
            _tempDir,
            validity: TimeSpan.FromDays(365));

        using var cert = X509CertificateLoader.LoadCertificateFromFile(result.CertPath);
        var validityDays = (cert.NotAfter - cert.NotBefore).TotalDays;
        validityDays.Should().BeInRange(364, 366);
    }

    [Fact]
    public void Generate_creates_output_directory_if_missing()
    {
        var nestedDir = Path.Combine(_tempDir, "nested", "ssl");
        // Nicht vorab anlegen

        var result = _generator.Generate(IPAddress.Parse("127.0.0.1"), "Test", nestedDir);

        Directory.Exists(nestedDir).Should().BeTrue();
        File.Exists(result.CertPath).Should().BeTrue();
    }
}
