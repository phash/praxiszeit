using System.Text;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

/// <summary>
/// Negative-path-Tests fuer den Lizenz-Validator. Positive-path-Tests
/// (echte Lizenz, signaturlich gueltig) brauchen den Production-
/// Private-Key, den der Wizard nicht hat — die werden im Backend
/// (test_native_mode.py) gegen die identische Schluesselbasis gefahren.
/// </summary>
public sealed class LicenseValidatorTests
{
    [Fact]
    public void ValidateToken_rejects_empty_string()
    {
        var result = LicenseValidator.ValidateToken("");
        result.Should().BeOfType<LicenseInvalid>()
            .Which.Reason.Should().Contain("leer");
    }

    [Fact]
    public void ValidateToken_rejects_whitespace_only()
    {
        LicenseValidator.ValidateToken("   ").Should().BeOfType<LicenseInvalid>();
    }

    [Theory]
    [InlineData("nopart")]
    [InlineData("two.parts")]
    [InlineData("four.dots.in.token")]
    public void ValidateToken_rejects_wrong_segment_count(string input)
    {
        var result = LicenseValidator.ValidateToken(input);
        result.Should().BeOfType<LicenseInvalid>()
            .Which.Reason.Should().Contain("JWT");
    }

    [Fact]
    public void ValidateToken_rejects_invalid_base64url()
    {
        // '!' ist kein gueltiges base64url-Zeichen
        var result = LicenseValidator.ValidateToken("aGVhZA.!!!.c2ln");
        result.Should().BeOfType<LicenseInvalid>();
    }

    [Fact]
    public void ValidateToken_rejects_non_eddsa_algorithm()
    {
        // HS256 in Header → Validator soll ablehnen, weil Backend nur EdDSA signiert
        var header = Base64Url("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        var payload = Base64Url("{\"sub\":\"x\",\"name\":\"y\",\"max_employees\":1,\"iat\":1}");
        var sig = Base64UrlBytes(new byte[] { 1, 2, 3 });
        var token = $"{header}.{payload}.{sig}";

        var result = LicenseValidator.ValidateToken(token);
        result.Should().BeOfType<LicenseInvalid>()
            .Which.Reason.Should().Contain("EdDSA");
    }

    [Fact]
    public void ValidateToken_rejects_non_json_header()
    {
        // header decodiert sich, ist aber kein JSON
        var header = Base64Url("not-json");
        var payload = Base64Url("{}");
        var sig = Base64UrlBytes(new byte[] { 1, 2, 3 });
        var token = $"{header}.{payload}.{sig}";

        var result = LicenseValidator.ValidateToken(token);
        result.Should().BeOfType<LicenseInvalid>();
    }

    [Fact]
    public void ValidateToken_rejects_random_signature_with_correct_alg()
    {
        // Gueltiger EdDSA-Header, plausibler Payload, aber Random-Signatur:
        // muss als "Signatur ungueltig" abgelehnt werden.
        var header = Base64Url("{\"alg\":\"EdDSA\",\"typ\":\"JWT\"}");
        var payload = Base64Url(
            "{\"sub\":\"test\",\"name\":\"Test\",\"max_employees\":10,\"iat\":1700000000}");
        // 64 Bytes Random — Ed25519-Signatur ist immer 64 Bytes
        var sig = Base64UrlBytes(Enumerable.Range(0, 64).Select(i => (byte)i).ToArray());
        var token = $"{header}.{payload}.{sig}";

        var result = LicenseValidator.ValidateToken(token);
        result.Should().BeOfType<LicenseInvalid>()
            .Which.Reason.Should().Contain("Signatur");
    }

    [Fact]
    public void ValidateFile_returns_invalid_for_missing_file()
    {
        var fakePath = Path.Combine(Path.GetTempPath(), $"nonexistent-{Guid.NewGuid():N}.key");
        var result = LicenseValidator.ValidateFile(fakePath);
        result.Should().BeOfType<LicenseInvalid>()
            .Which.Reason.Should().Contain("nicht gefunden");
    }

    [Fact]
    public void LicenseInfo_IsExpired_true_for_past_exp()
    {
        var info = new LicenseInfo
        {
            CustomerId = "x",
            CustomerName = "y",
            MaxEmployees = 1,
            ExpiresAt = DateTimeOffset.UtcNow.AddDays(-1),
        };
        info.IsExpired.Should().BeTrue();
        info.DaysUntilExpiry.Should().Be(0);
    }

    [Fact]
    public void LicenseInfo_IsExpired_false_for_future_exp()
    {
        var info = new LicenseInfo
        {
            CustomerId = "x",
            CustomerName = "y",
            MaxEmployees = 1,
            ExpiresAt = DateTimeOffset.UtcNow.AddDays(60),
        };
        info.IsExpired.Should().BeFalse();
        info.DaysUntilExpiry.Should().BeGreaterThan(58).And.BeLessThan(61);
    }

    [Fact]
    public void LicenseInfo_DaysUntilExpiry_null_when_no_exp()
    {
        var info = new LicenseInfo
        {
            CustomerId = "x",
            CustomerName = "y",
            MaxEmployees = 1,
            ExpiresAt = null,
        };
        info.IsExpired.Should().BeFalse();
        info.DaysUntilExpiry.Should().BeNull();
    }

    private static string Base64Url(string s) => Base64UrlBytes(Encoding.UTF8.GetBytes(s));

    private static string Base64UrlBytes(byte[] bytes)
    {
        var b64 = Convert.ToBase64String(bytes);
        return b64.TrimEnd('=').Replace('+', '-').Replace('/', '_');
    }
}
