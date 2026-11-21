using System.Text;

namespace PraxisZeit.Setup.Core.Services.Reporting;

/// <summary>
/// Liest das Ende des Setup-Protokolls (<see cref="SetupLog.FilePath"/>) für eine
/// Problemmeldung (#557): höchstens die letzten <c>maxBytes</c> Bytes und davon
/// die letzten <c>maxLines</c> Zeilen. Die Datei darf noch zum Schreiben offen
/// sein (<see cref="FileShare.ReadWrite"/>). Wirft nie.
/// </summary>
public static class SetupLogTail
{
    public static IReadOnlyList<string> Read(string? path, int maxLines = 200, int maxBytes = 262144)
    {
        if (string.IsNullOrWhiteSpace(path) || maxLines <= 0 || maxBytes <= 0)
        {
            return [];
        }
        try
        {
            if (!File.Exists(path))
            {
                return [];
            }
            using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var start = Math.Max(0, fs.Length - maxBytes);
            fs.Seek(start, SeekOrigin.Begin);
            var buffer = new byte[fs.Length - start];
            var read = 0;
            while (read < buffer.Length)
            {
                var n = fs.Read(buffer, read, buffer.Length - read);
                if (n == 0)
                {
                    break;
                }
                read += n;
            }
            var text = new UTF8Encoding(false, false).GetString(buffer, 0, read);
            if (text.Length > 0 && text[0] == '\uFEFF')
            {
                text = text[1..];
            }
            // NUL (z. B. UTF-16-Ausgabe von nssm im Protokoll) lehnt pzweb mit 422 ab.
            text = text.Replace("\0", "");
            var lines = text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n').ToList();
            if (start > 0 && lines.Count > 0)
            {
                // Erste Zeile ist abgeschnitten (mitten in Zeile/UTF-8-Zeichen).
                lines.RemoveAt(0);
            }
            if (lines.Count > 0 && lines[^1].Length == 0)
            {
                lines.RemoveAt(lines.Count - 1);
            }
            return lines.Count > maxLines ? lines.GetRange(lines.Count - maxLines, maxLines) : lines;
        }
        catch (Exception)
        {
            return [];
        }
    }
}
