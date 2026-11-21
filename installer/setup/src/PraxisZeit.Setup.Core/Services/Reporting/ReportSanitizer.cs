using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>
/// C#-Port der Textbereinigung von mrd-report-1 (#557). Die Regeln kommen
/// unverändert aus den eingebetteten Dateien, die auch das Backend nutzt:
/// <c>mrd-sanitize-vectors.json</c> (gemeinsame Regeln, pzweb
/// <c>report_sanitize.py</c>) und <c>praxiszeit-sanitize.json</c>
/// (PraxisZeit-Regeln, <c>report_sanitize_pz.py</c>). Schritt 0, Durchläufe,
/// Bedingungen und <c>find_patient_data</c> folgen den <c>engine_notes</c>
/// der Vektordatei.
///
/// .NET-Besonderheit (engine note „\b and character classes are ASCII-only“):
/// <c>\b \B \w \W \d \D</c> sind in .NET Unicode-fähig. Sie werden beim Laden
/// in ASCII-Klassen bzw. Lookarounds umgeschrieben.
/// </summary>
public static class ReportSanitizer
{
    public const string PatientToken = "<patient>";
    public const int MaxPasses = 4;
    private static readonly string[] PatientCategories = ["gdt", "dicom", "patient"];
    private static readonly TimeSpan MatchTimeout = TimeSpan.FromSeconds(2);

    // Schritt 0 (engine note 1). Steuerzeichen als Escapes, Quelltext bleibt ASCII.
    private static readonly Regex Ansi = new(
        @"\x1b\[[0-9;:?]{0,64}[ -/]{0,8}[@-~]|\x1b\][^\x07\x1b\n\r]{0,256}(?:\x07|\x1b\\)",
        RegexOptions.CultureInvariant, MatchTimeout);
    private static readonly Regex AnsiRest = new(
        @"\x1b\[[0-9;:?]*[ -/]*[@-~]?|\x1b", RegexOptions.CultureInvariant, MatchTimeout);
    private static readonly Regex EscHead = new(
        @"\x1b(?:\[[0-9;:?]*[ -/]*)?", RegexOptions.CultureInvariant, MatchTimeout);
    private static readonly Regex TemplatePart = new(@"\{([0-9])\}", RegexOptions.CultureInvariant, MatchTimeout);

    private const string AsciiWord = "[A-Za-z0-9_]";
    // (?-i:...) hält die ASCII-Klasse auch unter "i" eng (sonst zählt z. B. U+212A KELVIN SIGN als k).
    private const string WordBoundary =
        "(?-i:(?:(?<=[A-Za-z0-9_])(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])(?=[A-Za-z0-9_])))";
    private const string NonWordBoundary =
        "(?-i:(?:(?<=[A-Za-z0-9_])(?=[A-Za-z0-9_])|(?<![A-Za-z0-9_])(?![A-Za-z0-9_])))";

    internal sealed class Rule
    {
        public required string Name { get; init; }
        public required string Category { get; init; }
        public required Regex Regex { get; init; }
        public required string Replacement { get; init; }
        public string? Condition { get; init; }
        public int? PatientValueGroup { get; init; }

        public bool Holds(Match m) => Condition is null || Conditions(Condition, m);

        public string? PatientValue(Match m) =>
            PatientValueGroup is { } g ? m.Groups[g].Value.TrimEnd(' ', '\t') : null;

        public string Apply(string text, HashSet<string>? hits) =>
            Regex.Replace(text, m =>
            {
                if (!Holds(m))
                {
                    return m.Value;
                }
                if (hits is not null && PatientValueGroup is not null && PatientValue(m) != PatientToken)
                {
                    hits.Add(Category);
                }
                return TemplatePart.Replace(Replacement, t =>
                {
                    var g = m.Groups[t.Groups[1].Value[0] - '0'];
                    return g.Success ? g.Value : string.Empty;
                });
            });
    }

    private static readonly Lazy<(Rule[] Shared, Rule[] Pz)> Rules = new(LoadRules);

    public static int SharedRuleCount => Rules.Value.Shared.Length;
    public static int PraxisZeitRuleCount => Rules.Value.Pz.Length;

    /// <summary><c>sanitize_report_text</c>: gemeinsame Regeln, bis sich nichts mehr ändert (≤ 4 Durchläufe).</summary>
    public static string Sanitize(string text) => SanitizeCore(text ?? string.Empty, null);

    /// <summary><c>sanitize_praxiszeit_text</c>: gemeinsame Regeln, dann PraxisZeit-Regeln im Wechsel (wie Task 2).</summary>
    public static string SanitizePraxisZeit(string text)
    {
        var pz = Rules.Value.Pz;
        var t = Sanitize(text);
        for (var i = 0; i < MaxPasses; i++)
        {
            var prev = t;
            foreach (var rule in pz)
            {
                t = rule.Apply(t, null);
            }
            t = Sanitize(t);
            if (t == prev)
            {
                break;
            }
        }
        return t;
    }

    /// <summary><c>find_patient_data</c>: Kategorien gdt, dicom, patient (in dieser Reihenfolge).</summary>
    public static IReadOnlyList<string> FindPatientData(string text)
    {
        text ??= string.Empty;
        var hits = new HashSet<string>();
        RawPatientHits(Normalize(text), hits);
        if (text.Contains('\x1b'))
        {
            RawPatientHits(NormalizeLines(AnsiRest.Replace(text, " ")), hits);
            RawPatientHits(NormalizeLines(EscHead.Replace(text, " ")), hits);
        }
        SanitizeCore(text, hits);
        return PatientCategories.Where(hits.Contains).ToList();
    }

    public static string Normalize(string text)
    {
        if (text.Contains('\x1b'))
        {
            text = AnsiRest.Replace(Ansi.Replace(text, string.Empty), " ");
        }
        return NormalizeLines(text);
    }

    private static string NormalizeLines(string text) =>
        text.Replace("\r\n", "\n").Replace('\r', '\n').Replace('\u00A0', ' ');

    private static string SanitizeCore(string text, HashSet<string>? hits)
    {
        var shared = Rules.Value.Shared;
        text = Normalize(text);
        for (var i = 0; i < MaxPasses; i++)
        {
            var masked = text;
            foreach (var rule in shared)
            {
                masked = rule.Apply(masked, hits);
            }
            if (masked == text)
            {
                break;
            }
            text = masked;
        }
        return text;
    }

    private static void RawPatientHits(string text, HashSet<string> hits)
    {
        foreach (var rule in Rules.Value.Shared)
        {
            if (rule.PatientValueGroup is null || hits.Contains(rule.Category))
            {
                continue;
            }
            for (var m = rule.Regex.Match(text); m.Success; m = m.NextMatch())
            {
                if (rule.Holds(m) && rule.PatientValue(m) != PatientToken)
                {
                    hits.Add(rule.Category);
                    break;
                }
            }
        }
    }

    private static bool Conditions(string name, Match m) => name switch
    {
        "ipv4_octets" => Ipv4Octets(m.Value),
        "contains_digit" => m.Value.Any(IsDigit),
        "upper_lower_digit" => m.Value.Any(c => c is >= 'A' and <= 'Z')
                               && m.Value.Any(c => c is >= 'a' and <= 'z')
                               && m.Value.Any(IsDigit),
        "gdt_length" => GdtLength(m),
        "gdt_length_prefix" => GdtLengthPrefix(m),
        _ => throw new InvalidOperationException($"unknown condition {name}"),
    };

    private static bool IsDigit(char c) => c is >= '0' and <= '9';

    private static bool Ipv4Octets(string s)
    {
        var parts = s.Split('.');
        return parts.Length == 4 && parts.All(p =>
            p.Length is >= 1 and <= 3 && p.All(IsDigit) && int.Parse(p, System.Globalization.CultureInfo.InvariantCulture) <= 255);
    }

    // Python zählt Codepoints: Runen statt UTF-16-Einheiten.
    private static int CodePoints(string s) => s.EnumerateRunes().Count();

    private static int Utf8Bytes(string s) => Encoding.UTF8.GetByteCount(s);

    private static bool GdtLength(Match m)
    {
        var rest = int.Parse(m.Groups[2].Value, System.Globalization.CultureInfo.InvariantCulture) - 7;
        var content = m.Groups[4].Value;
        var byChars = rest - CodePoints(content);
        var byBytes = rest - Utf8Bytes(content);
        return byChars is >= 0 and <= 2 || byBytes is >= 0 and <= 2;
    }

    private static bool GdtLengthPrefix(Match m)
    {
        var declared = int.Parse(m.Groups[2].Value, System.Globalization.CultureInfo.InvariantCulture) - 7;
        var content = m.Groups[4].Value;
        return declared >= 6 && declared - 2 <= Math.Max(CodePoints(content), Utf8Bytes(content));
    }

    private static (Rule[], Rule[]) LoadRules() =>
        (ReadRules("mrd-sanitize-vectors.json"), ReadRules("praxiszeit-sanitize.json"));

    private static Rule[] ReadRules(string resource)
    {
        var asm = typeof(ReportSanitizer).Assembly;
        using var stream = asm.GetManifestResourceStream(resource)
            ?? throw new InvalidOperationException($"embedded resource {resource} missing");
        using var doc = JsonDocument.Parse(stream);
        var rules = new List<Rule>();
        foreach (var r in doc.RootElement.GetProperty("rules").EnumerateArray())
        {
            var options = RegexOptions.CultureInvariant;
            if (r.TryGetProperty("flags", out var flags))
            {
                foreach (var f in flags.EnumerateArray())
                {
                    options |= f.GetString() switch
                    {
                        "i" => RegexOptions.IgnoreCase,
                        "m" => RegexOptions.Multiline,
                        var other => throw new InvalidOperationException($"unknown flag {other}"),
                    };
                }
            }
            rules.Add(new Rule
            {
                Name = r.GetProperty("name").GetString()!,
                Category = r.GetProperty("category").GetString()!,
                Regex = new Regex(ToAsciiPattern(r.GetProperty("pattern").GetString()!), options, MatchTimeout),
                Replacement = r.GetProperty("replacement").GetString()!,
                Condition = r.TryGetProperty("condition", out var c) && c.ValueKind == JsonValueKind.String
                    ? c.GetString() : null,
                PatientValueGroup = r.TryGetProperty("patient_value_group", out var g) && g.ValueKind == JsonValueKind.Number
                    ? g.GetInt32() : null,
            });
        }
        return [.. rules];
    }

    /// <summary>
    /// Schreibt <c>\b \B \w \W \d \D</c> in ASCII-Formen um (engine note 7).
    /// Innerhalb einer Zeichenklasse nur <c>\d</c> und <c>\w</c> (die Muster
    /// nutzen dort keine negierten Kurzformen).
    /// </summary>
    public static string ToAsciiPattern(string pattern)
    {
        var sb = new StringBuilder(pattern.Length + 64);
        var inClass = false;
        for (var i = 0; i < pattern.Length; i++)
        {
            var ch = pattern[i];
            if (ch == '\\' && i + 1 < pattern.Length)
            {
                var next = pattern[++i];
                if (inClass)
                {
                    sb.Append(next switch
                    {
                        'd' => "0-9",
                        'w' => "A-Za-z0-9_",
                        'D' or 'W' or 's' or 'S' => throw new NotSupportedException($"\\{next} inside a class"),
                        _ => "\\" + next,
                    });
                }
                else
                {
                    sb.Append(next switch
                    {
                        'b' => WordBoundary,
                        'B' => NonWordBoundary,
                        'w' => "(?-i:" + AsciiWord + ")",
                        'W' => "(?-i:[^A-Za-z0-9_])",
                        'd' => "[0-9]",
                        'D' => "[^0-9]",
                        _ => "\\" + next,
                    });
                }
                continue;
            }
            if (!inClass && ch == '[')
            {
                inClass = true;
                sb.Append(ch);
                // "]" direkt nach "[" oder "[^" ist ein Literal.
                if (i + 1 < pattern.Length && pattern[i + 1] == '^')
                {
                    sb.Append('^');
                    i++;
                }
                if (i + 1 < pattern.Length && pattern[i + 1] == ']')
                {
                    sb.Append("\\]");
                    i++;
                }
                continue;
            }
            if (inClass && ch == ']')
            {
                inClass = false;
            }
            sb.Append(ch);
        }
        return sb.ToString();
    }
}
