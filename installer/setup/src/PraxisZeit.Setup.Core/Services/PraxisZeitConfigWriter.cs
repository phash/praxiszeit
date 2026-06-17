using System.Text;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Werte aus der ConfigPage des Setup-Wizards. Wird vom
/// <see cref="PraxisZeitConfigWriter"/> in eine TOML-Datei serialisiert
/// und im Fresh-Install-Pfad nach <c>config\praxiszeit.conf</c>
/// geschrieben — bevor <c>setup.bat</c> laeuft, sodass das Backend beim
/// allerersten Start die korrekten Admin-Credentials zum Anlegen des
/// Initial-Admin-Users hat (siehe <c>backend/app/main.py</c>
/// Lifespan-Bootstrap).
/// </summary>
public sealed record PraxisZeitConfigValues
{
    public required string PracticeName { get; init; }
    public string PracticeAddress { get; init; } = string.Empty;
    public string HolidayState { get; init; } = "Bayern";

    public string AdminUsername { get; init; } = "admin";
    public required string AdminEmail { get; init; }
    public string AdminFirstName { get; init; } = "Admin";
    public string AdminLastName { get; init; } = "Praxis";
    public required string AdminPassword { get; init; }

    /// <summary>HTTPS-Port den uvicorn-Backend bedient. Default 443.</summary>
    public int HttpsPort { get; init; } = 443;

    /// <summary>HTTP-Port der nur ein 301-Redirect auf <see cref="HttpsPort"/>
    /// liefert. Default 80, kann auf 0 gesetzt werden um den Redirect ganz
    /// abzuschalten (manche Kunden wollen keine Port-80-Bindung).</summary>
    public int HttpRedirectPort { get; init; } = 80;

    /// <summary>JWT-Text der Lizenz (komplette EdDSA-signierte Token-Zeile).
    /// Null = Demo-Modus aktiv (siehe <see cref="DemoDays"/>).</summary>
    public string? LicenseToken { get; init; }

    /// <summary>Demo-Laufzeit in Tagen ab Install-Datum. Wird nur ausgewertet
    /// wenn <see cref="LicenseToken"/> null ist. Default null = kein Demo,
    /// Backend bricht ohne Lizenz beim Start ab (legacy).</summary>
    public int? DemoDays { get; init; }
}

/// <summary>
/// Generiert eine vollstaendige <c>praxiszeit.conf</c>-TOML-Datei aus den
/// User-Werten der ConfigPage. Verwendet den Inhalt von
/// <c>installer/praxiszeit.conf.example</c> als Vorlage und ersetzt nur
/// die User-relevanten Felder ([practice], [admin]). [server], [database],
/// [security], [license], [updates], [backup]-Sektionen bleiben bei den
/// Defaults — die werden vom Backend beim ersten Start automatisch
/// fertig-konfiguriert.
///
/// <para>
/// <strong>Encoding:</strong> UTF-8 OHNE BOM. Notepad-Default schreibt mit
/// BOM, der Backend-Parser bricht dann ab (CLAUDE.md F-053). Wir machen
/// das hier explizit richtig.
/// </para>
/// </summary>
public static class PraxisZeitConfigWriter
{
    /// <summary>
    /// Default-Liste der bekannten unsicheren Default-Passwoerter. Muss
    /// mit <c>backend/app/main.py:_WEAK_ADMIN_PASSWORDS</c> synchron sein —
    /// ist die Backend-seitige Liste laenger, lehnt der Service nach dem
    /// Install ab obwohl der Wizard das Passwort durchgewunken hat.
    /// </summary>
    public static readonly IReadOnlySet<string> WeakAdminPasswords = new HashSet<string>
    {
        "Admin2025!", "admin123", "password", "admin",
    };

    public const int MinPasswordLength = 12;

    /// <summary>
    /// Validiert die User-Eingaben gegen die gleichen Regeln, die das
    /// Backend beim Startup prueft. Gibt eine deutsche Fehlermeldung
    /// zurueck oder <c>null</c> wenn alles OK ist.
    /// </summary>
    public static string? ValidateValues(PraxisZeitConfigValues values)
    {
        if (string.IsNullOrWhiteSpace(values.PracticeName))
        {
            return "Praxisname darf nicht leer sein.";
        }
        if (string.IsNullOrWhiteSpace(values.AdminUsername))
        {
            return "Admin-Benutzername darf nicht leer sein.";
        }
        if (string.IsNullOrWhiteSpace(values.AdminEmail) || !values.AdminEmail.Contains('@'))
        {
            return "Admin-Email muss eine gueltige Email-Adresse sein.";
        }
        if (string.IsNullOrEmpty(values.AdminPassword))
        {
            return "Admin-Passwort darf nicht leer sein.";
        }
        if (values.AdminPassword.Length < MinPasswordLength)
        {
            return $"Admin-Passwort muss mindestens {MinPasswordLength} Zeichen lang sein.";
        }
        if (WeakAdminPasswords.Contains(values.AdminPassword))
        {
            return "Admin-Passwort ist auf der Liste bekannter Default-Passwoerter — bitte ein anderes waehlen.";
        }
        if (values.HttpsPort is < 1 or > 65535)
        {
            return $"HTTPS-Port muss zwischen 1 und 65535 liegen (aktuell: {values.HttpsPort}).";
        }
        if (values.HttpRedirectPort is < 0 or > 65535)
        {
            return $"HTTP-Redirect-Port muss zwischen 0 und 65535 liegen (aktuell: {values.HttpRedirectPort}).";
        }
        if (values.HttpRedirectPort > 0 && values.HttpRedirectPort == values.HttpsPort)
        {
            return "HTTP-Redirect-Port und HTTPS-Port duerfen nicht identisch sein.";
        }
        return null;
    }

    /// <summary>
    /// Serialisiert die Werte in eine vollstaendige TOML-Config. Strings
    /// werden TOML-konform escaped (Backslash, Doublequote, Steuerzeichen).
    /// </summary>
    public static string Serialize(PraxisZeitConfigValues values)
    {
        var sb = new StringBuilder();
        sb.AppendLine("# PraxisZeit Konfiguration (Native Installation)");
        sb.AppendLine("# ================================================");
        sb.AppendLine("# Vom Setup-Wizard generiert. Aenderungen erfordern einen Neustart des Dienstes.");
        sb.AppendLine();

        sb.AppendLine("[server]");
        sb.AppendLine($"port = {values.HttpsPort}");
        if (values.HttpRedirectPort > 0)
        {
            sb.AppendLine($"http_redirect_port = {values.HttpRedirectPort}");
        }
        sb.AppendLine("ssl_cert = \"config/ssl/cert.pem\"");
        sb.AppendLine("ssl_key = \"config/ssl/key.pem\"");
        sb.AppendLine();

        sb.AppendLine("[database]");
        sb.AppendLine("data_dir = \"data/db\"");
        sb.AppendLine("superuser = \"praxiszeit\"");
        sb.AppendLine("app_user = \"praxiszeit_app\"");
        sb.AppendLine();

        sb.AppendLine("[practice]");
        sb.AppendLine($"name = {EscapeToml(values.PracticeName)}");
        sb.AppendLine($"address = {EscapeToml(values.PracticeAddress)}");
        sb.AppendLine($"holiday_state = {EscapeToml(values.HolidayState)}");
        sb.AppendLine();

        sb.AppendLine("[admin]");
        sb.AppendLine($"username = {EscapeToml(values.AdminUsername)}");
        sb.AppendLine($"email = {EscapeToml(values.AdminEmail)}");
        sb.AppendLine($"password = {EscapeToml(values.AdminPassword)}");
        sb.AppendLine($"first_name = {EscapeToml(values.AdminFirstName)}");
        sb.AppendLine($"last_name = {EscapeToml(values.AdminLastName)}");
        sb.AppendLine();

        sb.AppendLine("[security]");
        sb.AppendLine("login_rate_limit = \"5/minute\"");
        sb.AppendLine("cookie_secure = true");
        sb.AppendLine();

        sb.AppendLine("[license]");
        sb.AppendLine("key_file = \"config/license.key\"");
        if (values.LicenseToken is null && values.DemoDays is { } demoDays && demoDays > 0)
        {
            // Demo-Modus: keine echte license.key, aber demo_expires_at
            // setzt eine Hard-Deadline. Backend liest den Wert in
            // app/main.py:lifespan und schaltet ab Ueberlauf in Read-Only.
            var demoUntil = DateTime.UtcNow.Date.AddDays(demoDays).ToString("yyyy-MM-dd");
            sb.AppendLine($"demo_expires_at = \"{demoUntil}\"");
        }
        sb.AppendLine();

        sb.AppendLine("[updates]");
        sb.AppendLine("check_enabled = true");
        sb.AppendLine("server_url = \"https://updates.mr-development.de\"");
        sb.AppendLine("check_interval_hours = 12");
        sb.AppendLine();

        sb.AppendLine("[backup]");
        sb.AppendLine("enabled = true");
        sb.AppendLine("schedule = \"02:00\"");
        sb.AppendLine("retention_days = 31");

        return sb.ToString();
    }

    /// <summary>
    /// Schreibt die TOML-Config nach <paramref name="targetPath"/>
    /// als UTF-8 OHNE BOM (sonst bricht der Backend-Parser, F-053).
    /// Erzeugt das Parent-Directory falls noetig.
    /// </summary>
    public static async Task WriteAsync(string targetPath, PraxisZeitConfigValues values, CancellationToken ct = default)
    {
        var validation = ValidateValues(values);
        if (validation is not null)
        {
            throw new ArgumentException(validation, nameof(values));
        }

        var dir = Path.GetDirectoryName(targetPath);
        if (!string.IsNullOrEmpty(dir))
        {
            Directory.CreateDirectory(dir);
        }

        // UTF-8 OHNE BOM — Backend-Parser bricht sonst (F-053). Encoding.UTF8
        // schreibt MIT BOM, deshalb explizit `new UTF8Encoding(false)`.
        var encoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);
        await File.WriteAllTextAsync(targetPath, Serialize(values), encoding, ct).ConfigureAwait(false);
    }

    /// <summary>
    /// Schreibt ein Lizenz-Token nach <c>{configDir}/license.key</c>.
    /// Wird im Fresh-Install nach <see cref="WriteAsync"/> gerufen — ist
    /// bewusst eine separate Methode, weil der Token auch beim Update
    /// neu eingespielt werden kann (License-Page erscheint in beiden
    /// Modi).
    /// </summary>
    public static async Task WriteLicenseFileAsync(string configDir, string token, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new ArgumentException("Lizenz-Token darf nicht leer sein.", nameof(token));
        }
        Directory.CreateDirectory(configDir);
        var licensePath = Path.Combine(configDir, "license.key");
        var encoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);
        await File.WriteAllTextAsync(licensePath, token.Trim(), encoding, ct).ConfigureAwait(false);
    }

    /// <summary>
    /// TOML-String-Escaping per Spec
    /// (https://toml.io/en/v1.0.0#string): basic strings sind in
    /// double-quotes, backslash + double-quote muessen escaped werden,
    /// Steuerzeichen via \uXXXX. Newlines im Klartext gehen nicht — wir
    /// klappen sie zu \n um.
    /// </summary>
    public static string EscapeToml(string value)
    {
        if (value is null)
        {
            return "\"\"";
        }
        var sb = new StringBuilder(value.Length + 2);
        sb.Append('"');
        foreach (var c in value)
        {
            switch (c)
            {
                case '\\': sb.Append("\\\\"); break;
                case '"':  sb.Append("\\\""); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (c < 0x20)
                    {
                        sb.Append($"\\u{(int)c:X4}");
                    }
                    else
                    {
                        sb.Append(c);
                    }
                    break;
            }
        }
        sb.Append('"');
        return sb.ToString();
    }
}
