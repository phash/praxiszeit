namespace PraxisZeit.Setup.Core.Models;

/// <summary>SSL-Konfigurationsmodus fuer den Native-Install.</summary>
public enum SslMode
{
    /// <summary>
    /// Self-signed Zertifikat wird automatisch via Bouncy Castle / .NET
    /// <c>CertificateRequest</c> erzeugt. Fuer LAN-Deployments mit einer
    /// handvoll Clients die einmalig den Cert-Trust importieren.
    /// </summary>
    SelfSigned,

    /// <summary>
    /// Kunde bringt eigene Cert-Dateien mit (cert.pem + key.pem). Pfade
    /// werden im Wizard abgefragt und nach <c>config/ssl/</c> kopiert.
    /// </summary>
    BringYourOwn,

    /// <summary>
    /// Kein SSL. Der Server bindet an 127.0.0.1 (nicht 0.0.0.0), damit
    /// Login-Cookies nicht im Klartext uebers LAN gehen. Fuer Dev /
    /// Reverse-Proxy-Szenarien (Caddy, IIS vor PraxisZeit).
    /// </summary>
    HttpOnly,
}
