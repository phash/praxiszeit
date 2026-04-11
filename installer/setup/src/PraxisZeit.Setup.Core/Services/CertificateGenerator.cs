using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Generiert self-signed SSL-Zertifikate fuer PraxisZeit-Installationen im
/// LAN. 100% cross-platform (nutzt nur <c>System.Security.Cryptography</c>),
/// kein openssl oder cryptography-Python-Modul noetig.
///
/// Das Cert wird als RSA-2048 mit SHA-256 ausgestellt, SubjectAltName
/// enthaelt <c>localhost</c> + <c>127.0.0.1</c> + die angegebene IP,
/// 10 Jahre Gueltigkeit. Key wird als unverschluesseltes PKCS#8-PEM
/// exportiert (kompatibel zu uvicorn <c>--ssl-keyfile</c>), Cert als
/// X.509-PEM.
/// </summary>
public sealed class CertificateGenerator
{
    public record GeneratedCert(string CertPath, string KeyPath, string Thumbprint);

    /// <summary>
    /// Erzeugt ein self-signed Zertifikat fuer die angegebene IP und
    /// schreibt es nach <paramref name="outputDirectory"/> als
    /// <c>cert.pem</c> + <c>key.pem</c>.
    /// </summary>
    public GeneratedCert Generate(
        IPAddress ipAddress,
        string practiceName,
        string outputDirectory,
        TimeSpan? validity = null)
    {
        Directory.CreateDirectory(outputDirectory);

        using var rsa = RSA.Create(2048);
        var dn = new X500DistinguishedName($"CN={ipAddress}, O={practiceName}");

        var request = new CertificateRequest(
            dn,
            rsa,
            HashAlgorithmName.SHA256,
            RSASignaturePadding.Pkcs1);

        // BasicConstraints: nicht CA, endEntity
        request.CertificateExtensions.Add(
            new X509BasicConstraintsExtension(certificateAuthority: false, hasPathLengthConstraint: false, pathLengthConstraint: 0, critical: true));

        // KeyUsage: digital signature + key encipherment (TLS server)
        request.CertificateExtensions.Add(
            new X509KeyUsageExtension(
                X509KeyUsageFlags.DigitalSignature | X509KeyUsageFlags.KeyEncipherment,
                critical: true));

        // ExtendedKeyUsage: TLS Server Authentication
        request.CertificateExtensions.Add(
            new X509EnhancedKeyUsageExtension(
                [new Oid("1.3.6.1.5.5.7.3.1", "TLS Server Authentication")],
                critical: false));

        // SubjectAltName
        var sanBuilder = new SubjectAlternativeNameBuilder();
        sanBuilder.AddDnsName("localhost");
        sanBuilder.AddIpAddress(IPAddress.Loopback);
        sanBuilder.AddIpAddress(ipAddress);
        request.CertificateExtensions.Add(sanBuilder.Build(critical: false));

        // Subject Key Identifier
        request.CertificateExtensions.Add(
            new X509SubjectKeyIdentifierExtension(request.PublicKey, critical: false));

        var notBefore = DateTimeOffset.UtcNow.AddMinutes(-5);
        var notAfter = DateTimeOffset.UtcNow.Add(validity ?? TimeSpan.FromDays(3650));

        using var cert = request.CreateSelfSigned(notBefore, notAfter);

        var certPath = Path.Combine(outputDirectory, "cert.pem");
        var keyPath = Path.Combine(outputDirectory, "key.pem");

        var certPem = PemEncoding.WriteString("CERTIFICATE", cert.Export(X509ContentType.Cert));
        File.WriteAllText(certPath, certPem);

        // PKCS#8 unencrypted — uvicorn --ssl-keyfile versteht das direkt
        var keyPem = PemEncoding.WriteString("PRIVATE KEY", rsa.ExportPkcs8PrivateKey());
        File.WriteAllText(keyPath, keyPem);

        // Auf Unix: 0600 fuer den Key
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(keyPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }

        return new GeneratedCert(certPath, keyPath, cert.Thumbprint);
    }
}
