using System.Buffers.Text;
using System.Text;
using System.Text.Json;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.OpenSsl;
using Org.BouncyCastle.Security;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Result einer Lizenz-Verifikation. Mirror'd 1:1 von
/// <c>backend/app/core/license.py:LicenseInfo</c> — gleiche Felder, gleiche
/// Semantik fuer <see cref="IsExpired"/> und <see cref="DaysUntilExpiry"/>,
/// damit der Wizard dem User EXAKT das anzeigt, was das Backend nach dem
/// Install in der Statusbar zeigen wird.
/// </summary>
public sealed record LicenseInfo
{
    public required string CustomerId { get; init; }
    public required string CustomerName { get; init; }
    public required int MaxEmployees { get; init; }
    public IReadOnlyList<string> Features { get; init; } = ["base"];
    public DateTimeOffset? IssuedAt { get; init; }
    public DateTimeOffset? ExpiresAt { get; init; }
    public int Version { get; init; } = 1;

    public bool IsExpired => ExpiresAt is { } exp && DateTimeOffset.UtcNow > exp;

    public int? DaysUntilExpiry
    {
        get
        {
            if (ExpiresAt is not { } exp) return null;
            var delta = exp - DateTimeOffset.UtcNow;
            return Math.Max(0, (int)delta.TotalDays);
        }
    }
}

public abstract record LicenseResult;

public sealed record LicenseValid(LicenseInfo Info) : LicenseResult;

/// <summary>Lizenz war signaturlich gueltig, ist aber laut <c>exp</c> abgelaufen.</summary>
public sealed record LicenseExpired(LicenseInfo Info) : LicenseResult;

/// <summary>
/// Lizenz konnte nicht validiert werden — falsche Signatur, kaputte Datei,
/// falsches Format. <see cref="Reason"/> ist eine deutsche Fehlermeldung
/// die direkt im UI angezeigt werden kann.
/// </summary>
public sealed record LicenseInvalid(string Reason) : LicenseResult;

/// <summary>
/// Offline-Verifikation einer PraxisZeit-Lizenz. Reimplementiert das gleiche
/// Schema wie <c>backend/app/core/license.py</c>: EdDSA-signierter JWT,
/// Public-Key embedded, JWT enthaelt <c>sub | name | max_employees | iat |
/// exp? | features? | v?</c>. Wir nutzen BouncyCastle weil .NET 10 noch
/// keine native Ed25519-Unterstuetzung hat (MLDsa ist Post-Quantum, kein
/// Ed25519).
///
/// <para>
/// <strong>Public-Key-Sync:</strong> Diese Liste MUSS byte-für-byte mit
/// <c>backend/app/core/license.py:_PUBLIC_KEYS_PEM</c> synchron bleiben —
/// sonst akzeptiert der Wizard Lizenzen, die das Backend ablehnt (oder
/// umgekehrt). Es werden MEHRERE Schlüssel akzeptiert (aktuell + alt), damit
/// nach einer Rotation weder neue noch Bestandslizenzen abgelehnt werden.
/// </para>
/// </summary>
public static class LicenseValidator
{
    /// <summary>
    /// Akzeptierte Ed25519 Public Keys (NEU zuerst, dann ALT). MUSS synchron
    /// mit <c>backend/app/core/license.py:_PUBLIC_KEYS_PEM</c> sein.
    /// </summary>
    private static readonly string[] PublicKeysPem =
    {
        // NEU — aktuelle Shop-Ausstellung
        "-----BEGIN PUBLIC KEY-----\n" +
        "MCowBQYDK2VwAyEAt8zaDoRf4KldrPMxmX0uKhoaOrIAyU4wtgtn489WxdI=\n" +
        "-----END PUBLIC KEY-----",
        // ALT — Bestandslizenzen vor der 1.5.x-Rotation
        "-----BEGIN PUBLIC KEY-----\n" +
        "MCowBQYDK2VwAyEAB5ZiJro6fDM8M5BupMCdTWjVIFkPn+hsNYHNlajzIyY=\n" +
        "-----END PUBLIC KEY-----",
    };

    /// <summary>
    /// Parst und verifiziert ein Lizenz-Token (JWT-String, im Backend per
    /// <c>jwt.encode(...,algorithm="EdDSA")</c> erzeugt). Liefert ein
    /// <see cref="LicenseResult"/> das das UI direkt rendern kann —
    /// signaturlich gueltig, gueltig-aber-abgelaufen, oder ungueltig.
    /// </summary>
    public static LicenseResult ValidateToken(string token)
    {
        if (string.IsNullOrWhiteSpace(token))
        {
            return new LicenseInvalid("Lizenz ist leer.");
        }

        var trimmed = token.Trim();
        var parts = trimmed.Split('.');
        if (parts.Length != 3)
        {
            return new LicenseInvalid(
                "Lizenz hat nicht das erwartete JWT-Format (Header.Payload.Signature). "
                + "Bitte prüfen Sie, ob die Datei vollständig ist.");
        }

        var headerJson = TryDecodeBase64Url(parts[0]);
        var payloadJson = TryDecodeBase64Url(parts[1]);
        var signature = TryDecodeBase64UrlBytes(parts[2]);
        if (headerJson is null || payloadJson is null || signature is null)
        {
            return new LicenseInvalid("Lizenz enthält ungültiges Base64-URL-Encoding.");
        }

        // Header-Algorithm pruefen — alles ausser EdDSA ist hier nicht
        // unterstuetzt (HS256 etc.). Backend signiert ausschliesslich EdDSA.
        try
        {
            using var headerDoc = JsonDocument.Parse(headerJson);
            var alg = headerDoc.RootElement.TryGetProperty("alg", out var algEl)
                ? algEl.GetString()
                : null;
            if (!string.Equals(alg, "EdDSA", StringComparison.Ordinal))
            {
                return new LicenseInvalid(
                    $"Lizenz hat unbekannten Signatur-Algorithmus '{alg}'. "
                    + "Erwartet wird EdDSA (Ed25519).");
            }
        }
        catch (JsonException)
        {
            return new LicenseInvalid("Lizenz-Header ist kein gültiges JSON.");
        }

        // Signatur-Pruefung: signing_input = header_b64 + "." + payload_b64
        // (UTF-8 Bytes der base64url-encoded Strings, NICHT der decodierten
        // JSON-Strings). Das ist die JWT-Spec.
        var signingInput = Encoding.UTF8.GetBytes(parts[0] + "." + parts[1]);
        if (!VerifyEd25519(signingInput, signature))
        {
            return new LicenseInvalid(
                "Lizenz-Signatur passt zu keinem hinterlegten Schlüssel. Die Lizenz "
                + "wurde vermutlich für eine andere Schlüsselversion ausgestellt. "
                + "Bitte eine aktuelle Lizenz im Shop (praxiszeit.mr-development.de) anfordern.");
        }

        // Payload parsen + Required Claims validieren
        try
        {
            using var payloadDoc = JsonDocument.Parse(payloadJson);
            var root = payloadDoc.RootElement;

            string? sub = TryGetString(root, "sub");
            string? name = TryGetString(root, "name");
            int? maxEmployees = TryGetInt(root, "max_employees");
            long? iat = TryGetLong(root, "iat");

            if (sub is null || name is null || maxEmployees is null || iat is null)
            {
                return new LicenseInvalid(
                    "Lizenz fehlt eines der erforderlichen Felder (sub / name / max_employees / iat).");
            }

            var info = new LicenseInfo
            {
                CustomerId = sub,
                CustomerName = name,
                MaxEmployees = maxEmployees.Value,
                Features = TryGetStringArray(root, "features") ?? ["base"],
                IssuedAt = DateTimeOffset.FromUnixTimeSeconds(iat.Value),
                ExpiresAt = TryGetLong(root, "exp") is { } exp
                    ? DateTimeOffset.FromUnixTimeSeconds(exp)
                    : null,
                Version = TryGetInt(root, "v") ?? 1,
            };

            return info.IsExpired ? new LicenseExpired(info) : new LicenseValid(info);
        }
        catch (JsonException ex)
        {
            return new LicenseInvalid($"Lizenz-Payload ist kein gültiges JSON: {ex.Message}");
        }
    }

    /// <summary>
    /// Wrapper fuer Datei-Input — liest Datei und delegiert an
    /// <see cref="ValidateToken"/>. Datei-Encoding wird wie das Backend
    /// behandelt: nach <c>strip()</c>, jegliche Whitespace-Wrap egal.
    /// </summary>
    public static LicenseResult ValidateFile(string licensePath)
    {
        if (!File.Exists(licensePath))
        {
            return new LicenseInvalid($"Lizenz-Datei nicht gefunden: {licensePath}");
        }

        string token;
        try
        {
            token = File.ReadAllText(licensePath).Trim();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new LicenseInvalid($"Lizenz-Datei konnte nicht gelesen werden: {ex.Message}");
        }

        return ValidateToken(token);
    }

    // ---------- Internals ----------

    private static bool VerifyEd25519(byte[] message, byte[] signature)
    {
        // Gegen JEDEN hinterlegten Schlüssel prüfen — true, sobald einer passt.
        foreach (var pem in PublicKeysPem)
        {
            try
            {
                using var reader = new StringReader(pem);
                var pemReader = new PemReader(reader);
                var keyObj = pemReader.ReadObject();
                // BouncyCastle's PemReader returns SubjectPublicKeyInfo for the
                // OpenSSL "PUBLIC KEY" PEM block. Convert to typed key.
                Ed25519PublicKeyParameters publicKey = keyObj switch
                {
                    Ed25519PublicKeyParameters direct => direct,
                    Org.BouncyCastle.Asn1.X509.SubjectPublicKeyInfo spki
                        => (Ed25519PublicKeyParameters)PublicKeyFactory.CreateKey(spki),
                    _ => (Ed25519PublicKeyParameters)PublicKeyFactory.CreateKey(
                        Org.BouncyCastle.Asn1.X509.SubjectPublicKeyInfo.GetInstance(keyObj!)),
                };

                var verifier = new Ed25519Signer();
                verifier.Init(forSigning: false, publicKey);
                verifier.BlockUpdate(message, 0, message.Length);
                if (verifier.VerifySignature(signature))
                {
                    return true;
                }
            }
            catch
            {
                // Diesen Schlüssel überspringen, nächsten versuchen.
            }
        }
        return false;
    }

    private static string? TryDecodeBase64Url(string input)
    {
        var bytes = TryDecodeBase64UrlBytes(input);
        return bytes is null ? null : Encoding.UTF8.GetString(bytes);
    }

    private static byte[]? TryDecodeBase64UrlBytes(string input)
    {
        // JWT base64url: '-' → '+', '_' → '/', no padding. Pad to multiple of 4.
        var padded = input.Replace('-', '+').Replace('_', '/');
        switch (padded.Length % 4)
        {
            case 2: padded += "=="; break;
            case 3: padded += "="; break;
            case 0: break;
            default: return null;
        }
        try
        {
            return Convert.FromBase64String(padded);
        }
        catch (FormatException)
        {
            return null;
        }
    }

    private static string? TryGetString(JsonElement el, string name) =>
        el.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    private static int? TryGetInt(JsonElement el, string name)
    {
        if (!el.TryGetProperty(name, out var v)) return null;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i)) return i;
        if (v.ValueKind == JsonValueKind.String && int.TryParse(v.GetString(), out var i2)) return i2;
        return null;
    }

    private static long? TryGetLong(JsonElement el, string name)
    {
        if (!el.TryGetProperty(name, out var v)) return null;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var l)) return l;
        if (v.ValueKind == JsonValueKind.String && long.TryParse(v.GetString(), out var l2)) return l2;
        return null;
    }

    private static IReadOnlyList<string>? TryGetStringArray(JsonElement el, string name)
    {
        if (!el.TryGetProperty(name, out var v) || v.ValueKind != JsonValueKind.Array) return null;
        var list = new List<string>(v.GetArrayLength());
        foreach (var item in v.EnumerateArray())
        {
            if (item.ValueKind == JsonValueKind.String && item.GetString() is { } s) list.Add(s);
        }
        return list;
    }
}
