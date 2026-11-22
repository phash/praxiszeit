# Shared text sanitizer for mrd-report-1. Source: phash/pzweb backend/app/core/report_sanitize.py @ 1b2a639 (text part only).
# Update together with tests/data/mrd-report-1/sanitize-vectors.json.
"""Reference sanitizer for app reports (protocol mrd-report-1).

The rule table below is published 1:1 in
``docs/protocols/mrd-report-1/sanitize-vectors.json`` (a test keeps both equal).
Every client repo ports these rules and must pass the shared vectors.

Portability: no lookaround, no backreferences (Go RE2, Rust, Java, JS, Python).
Every pattern runs in linear time: a rule that starts with an unbounded run is
anchored on a delimiter group, and no unbounded class is followed by a literal that
the class itself may contain more than once per start.

Before the rules run, the text is normalized: ANSI escape sequences (CSI colours, OSC titles/links)
are removed, CRLF and lone CR become LF, U+00A0 becomes a space.
Replacement templates use ``{n}`` for the text of group n (empty if unmatched).
A rule with a ``condition`` is applied to a match only if the condition holds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

PATIENT_TOKEN = "<patient>"
PATIENT_CATEGORIES = ("gdt", "dicom", "patient")
UNCHECKED = "unchecked"
# ZIP members not scanned because a size limit is reached (also "not passed as clean").
TOO_LARGE = "too-large"

_Q = "'"  # kept out of raw strings: an escaped quote is rejected by Rust and JS-u
# Characters that end a user name in a path.
_NAME = r'[^\\/ \t\n"' + _Q + r'<>|:*?,;]'
# Key endings whose value is a secret; the key may carry any prefix (DB_PASSWORD, client_secret,
# X-Amz-Signature, aws_secret_access_key, BACKUP_PASSPHRASE, DB_ENC_KEY, MRD_REPORT_KEY). "key" and "auth"
# count only after a known prefix or separator, so primary key, hotkey, monkey, OAuth and author stay readable.
_SECRET_KEYS = (
    r'(?:password|passwd|pwd|passphrase|token|secret|credential|signature|license_id|apikey|sessid'
    r'|(?:api|secret|private|access|signing|encryption|enc|report|client|master|session|ssh|gpg|pgp|app|account'
    r'|storage)'
    r'[_.-]?key|session[_.-]?id|[_.-]sig|[_.-]auth)s?'
)
# Short keys that are secrets only as a whole key: key=, sig=, auth=, session= (query strings), and
# "key"/"auth"/... as a whole JSON key (docker config "auth": "...").
_SHORT_SECRET_KEYS = r'(?:key|sig|auth|session)'
# Secret JSON key names, plain ("password") and escaped inside a JSON string (\"password\").
_JSON_SECRET_KEYS = r'(?:[A-Za-z0-9_.-]*' + _SECRET_KEYS + r'|' + _SHORT_SECRET_KEYS + r')'
# E-mail delimiters: the local part and the domain labels consist of everything else.
_MAIL_DELIM = r' \t\n@<>()\[\]{},;:"' + _Q + r'\\/=|'
_DICOM_PATIENT_TAGS = r'(?:0010|0020|0030|0040|1000|1001|1005|1040|1060|2154)'
_DICOM_KEYWORDS = (
    r'(?:PatientName|PatientID|PatientBirthDate|PatientSex|PatientAddress|PatientBirthName'
    r'|PatientMotherBirthName|PatientTelephoneNumbers|OtherPatientIDs|OtherPatientNames)'
)
_NAME_PARTS = r'(?:first|last|given|family|middle|sur)[ _.-]?name'
_PATIENT_LABELS = (
    r"(?:patient(?:(?:'s|’s)[ _.-]?|[ _.-])(?:name|id|birth[ _.-]?date|birth[ _.-]?name|sex|gender|address|dob|"
    + _NAME_PARTS + r")"
    r"|patient" + _NAME_PARTS + r"|patientgender|patientdob"
    r"|birth[ _.-]?date|birth[ _.-]?time|date[ _.-]?of[ _.-]?birth|dob"
    r"|patienten[ _.-]?(?:name|id|nummer|nr\.?)|patient[ _.-]?(?:nummer|nr\.?)|geburtsdatum|geburtstag|geb\.?[ _.-]?datum"
    r"|(?:name|vorname|nachname|telefon(?:nummer)?|adresse|anschrift|geburtsdatum)[ \t]+de[rs][ \t]+patient(?:en|in)"
    r"|pat[ _.-]{0,2}nr\.?|vers[ _.-]{0,2}nr\.?|fall[ _.-]?(?:nr\.?|nummer)"
    r"|krankenversichertennummer|versichertennummer|versicherten[ _.-]?(?:nr\.?|id)|kvnr|kvid"
    r"|insurance[ _.-]?(?:number|no|id))"
)
# Words that are a patient field only when followed by "=" or ":" ("Patient: Max Mustermann",
# firstName=Max in a toString or JSON).
_PERSON_WORDS = r'(?:patient|patientin|vorname|nachname|geburtsname|' + _NAME_PARTS + r')'
# Closing quote of a JSON key or Python dict key ("PatientName": ..., 'Vorname': ...), also escaped
# inside a JSON string (\"patientName\": ..., up to three backslashes).
_KEY_END = r'\\{0,3}["' + _Q + r']?'
# Separator between a patient keyword/label and its value: =, :, > (XML) or ^, optionally
# followed by up to three line breaks when the value sits on a later line; or blanks.
_KV_SEP = r'(' + _KEY_END + r'[ \t]*[=:>^][ \t]*(?:\n[ \t]*){0,3}|[ \t]+)'
# No ">" here: the token <patient> itself would read as "patient>" (XML elements: person_xml, patient_xml).
_COLON_SEP = r'(' + _KEY_END + r'[ \t]*[=:][ \t]*(?:\n[ \t]*){0,3})'
# A JSON string quote, optionally escaped (JSON inside a JSON string).
_JQ = r'\\{0,3}"'
# A table block: the rest of the line and every following non-empty line (up to a blank line).
_BLOCK = r'[^\n]*(?:\n[^\n]+)*'
# Cell labels of a delimited table header (CSV, TSV, ; or | separated).
_TABLE_LABELS = r'(?:' + _PATIENT_LABELS + r'|' + _PERSON_WORDS + r')'
# Words that are a person column only as a whole cell of a header line made of cells (Nr;Name,
# Mitarbeiterin|Stunden): in prose, as a key or in a SQL column list they stay readable ("name": "Export",
# name=Export, Spalte Name fehlt, insert into t (id,name)).
# Gender forms: -in, -innen, :in, *in, /in, _in, /-in, (in), (innen).
_IN = r'(?:[:*/_]?in(?:nen)?|/-in(?:nen)?|\(in(?:nen)?\))?'
_TABLE_PERSON_WORDS = (
    r'(?:name|name[ _.-]?[0-9]|(?:full|display|voll(?:er)?)[ _.-]?name|vor-?[ \t]*(?:und|&)[ \t]*nachname'
    r'|mitarbeiter' + _IN + r'(?:[ _.-]?name)?|mitarbeitende|employee(?:[ _.-]?name)?'
    r'|user[ _.-]?name|benutzer(?:[ _.-]?name|\(name\))?|person(?:[ _.-]?name)?'
    r'|versicherte(?:[rn]|\([rn]\)|\*r)?|kunde(?:n|\(n\)|/kundin)?'
    r'|kund(?:[:*/_]?in(?:nen)?|\(in\))|kunden(?:[ _.-]?name)?'
    r'|(?:zahn|fach|haus)?(?:arzt(?:/(?:ä|Ä|ae)rztin)?|(?:ä|Ä|ae)rzt(?:e|[:*/_]?in(?:nen)?|\(in\)))'
    r'|patient(?:en|innen|[:*/_]in(?:nen)?|\(in(?:nen)?\))|pat\.?|(?:be)?nutzer' + _IN
    + r'|(?:teilnehm|behandel)ende'
    + r'|(?:behandler|bearbeiter|therapeut|teilnehmer|ansprechpartner|inhaber|klient|betreuer)' + _IN
    + r'|customer|client|doctor|physician|staff)'
)
# Cells before such a word, from the line start: { } = only inside groups, ( ) [ ] only as balanced, not nested
# groups, so
# the word is no table header inside a SQL column list (id,name), a JSON array or after key=value; a
# timestamp, [INFO], "label:" or a cell "Dauer (h)" before the header does not stop it (fails closed).
# Linear: a group starts with ( or [, which the class run cannot contain, so every prefix has one parse. One class run (blanks included, no
# separate leading [ \t]*: two overlapping runs would make a line of tabs quadratic), then a delimiter.
_CELLS = r'[^\n(){}\[\]=]*(?:(?:\([^\n()]*\)|\[[^\n\[\]]*\])[^\n(){}\[\]=]*)*[;\t|,]'
_HEADER_CELLS = r'^((?:' + _CELLS + r')?)'
_VALUE = r'([^ \t\n][^\n]*)'
# Left delimiter of an inline GDT record. "/" and "\" (paths, URLs) only for the rules with a
# length condition: GET /api/items/1233104/ is no record.
_GDT_PREFIX = r'[ \t:|=>"' + _Q + r',;(\[]'
_GDT_PREFIX_PATH = r'[ \t:|=>"' + _Q + r',;(\[/\\]'
_GDT_TEXT_FIELDS = r'(?:3101|3102|3104|3105|3106|3107|3112|3113)'
# XML element start tag with optional namespace prefix and attributes; the text may start on the next line.
_XML_NS = r'(?:[A-Za-z0-9_.-]+:)?'
_XML_TAG_END = r'(?:[ \t][^<>\n]*)?>[ \t]*(?:\n[ \t]*)?'
_XML_TEXT = r'([^ \t\n<][^<\n]*)'
# Element text that ends on a non-blank, so that blanks before the closing tag belong to exactly
# one group (an overlap would make '<patient>a' + many blanks quadratic).
_XML_TEXT_TRIMMED = r'([^ \t\n<](?:[^<\n]*[^ \t\n<])?)'
_LEFT = r'(^|[^A-Za-z0-9])'


def _ipv4_octets(m: re.Match) -> bool:
    parts = m.group(0).split(".")
    return len(parts) == 4 and all(1 <= len(p) <= 3 and int(p) <= 255 for p in parts)


def _contains_digit(m: re.Match) -> bool:
    return any("0" <= ch <= "9" for ch in m.group(0))


def _upper_lower_digit(m: re.Match) -> bool:
    s = m.group(0)
    return any("A" <= ch <= "Z" for ch in s) and any("a" <= ch <= "z" for ch in s) and _contains_digit(m)


def _gdt_length(m: re.Match) -> bool:
    # GDT record length = 3 (length) + 4 (field id) + content + line end (0-2 bytes); the content
    # counted in characters (ISO 8859-15 export) or UTF-8 bytes (UTF-8 export).
    rest = int(m.group(2)) - 7
    content = m.group(4)
    return rest - len(content) in (0, 1, 2) or rest - len(content.encode("utf-8")) in (0, 1, 2)


def _gdt_length_prefix(m: re.Match) -> bool:
    # The declared content (length - 7 - line end) is at least 6 long and fits into the matched
    # text, counted in characters or UTF-8 bytes (the rest of the line may follow the record).
    declared = int(m.group(2)) - 7
    content = m.group(4)
    return declared >= 6 and declared - 2 <= max(len(content), len(content.encode("utf-8")))


_CONDITIONS: dict[str, Callable[[re.Match], bool]] = {
    "ipv4_octets": _ipv4_octets,
    "contains_digit": _contains_digit,
    "upper_lower_digit": _upper_lower_digit,
    "gdt_length": _gdt_length,
    "gdt_length_prefix": _gdt_length_prefix,
}

_FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE}
_TEMPLATE_PART = re.compile(r"\{(\d)\}")


@dataclass(frozen=True)
class Rule:
    name: str
    category: str
    pattern: str
    replacement: str
    description: str
    flags: tuple[str, ...] = ()
    condition: Optional[str] = None
    patient_value_group: Optional[int] = None
    # Server-side shortcut, not part of the published rule: the rule is skipped if the text contains
    # none of these literals (lower case for "i" rules). Every match contains one of them.
    required: tuple[str, ...] = field(default=(), compare=False)
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        flags = re.ASCII
        for f in self.flags:
            flags |= _FLAGS[f]
        object.__setattr__(self, "regex", re.compile(self.pattern, flags))

    def can_match(self, text: str) -> bool:
        if not self.required:
            return True
        if "i" in self.flags:
            text = text.lower()
        return any(literal in text for literal in self.required)

    def apply(self, text: str, hits: Optional[set[str]] = None) -> str:
        if not self.can_match(text):
            return text

        def replace(m: re.Match) -> str:
            if self.condition and not _CONDITIONS[self.condition](m):
                return m.group(0)
            if (
                hits is not None
                and self.patient_value_group
                and m.group(self.patient_value_group).rstrip(" \t") != PATIENT_TOKEN
            ):
                hits.add(self.category)
            return _TEMPLATE_PART.sub(lambda t: m.group(int(t.group(1))) or "", self.replacement)

        return self.regex.sub(replace, text)


RULES: tuple[Rule, ...] = (
    # 1. secrets and auth headers
    Rule("auth_header", "secret",
         r'\b((?:Proxy-)?Authorization|Set-Cookie|Cookie|X-Api-Key|Api-Key|X-Auth-Token|X-Access-Token'
         r'|X-Csrf-Token)("?[ \t]*:[ \t]*)[^\n]+',
         "{1}{2}<secret>",
         "Credential headers (Authorization, Cookie, X-Api-Key, ...): everything after the colon to end of line.",
         ("i",)),
    Rule("bearer", "secret", r'\b(Bearer[ \t]+)[A-Za-z0-9._~+/=-]+', "{1}<secret>", "Bearer <token>.", ("i",)),
    Rule("url_credentials", "secret",
         r'(^|[^A-Za-z0-9+.-])([a-z][a-z0-9+.-]*://)[^ \t\n/:@]+:[^ \t\n/@]+@', "{1}{2}<user>:<secret>@",
         "scheme://user:password@ in URLs.", ("i",)),
    Rule("kv_secret", "secret",
         r'(^|[^A-Za-z0-9_.-])([A-Za-z0-9_.-]*' + _SECRET_KEYS + r'[ \t]*[=:][ \t]*)("?)[^ \t\n&;"]+',
         "{1}{2}{3}<secret>",
         "key=value or key: value where the key ends in password, passwd, pwd, passphrase, token, secret, "
         "credential, signature, license_id, apikey, sessid, <api|secret|private|access|signing|encryption|enc|"
         "report|client|master|session|ssh|gpg|pgp|app|account|storage>[_.-]key, session_id, _sig or _auth "
         "(optional plural s; DB_ENC_KEY, MRD_REPORT_KEY, set \"X_TOKEN=...\"); an opening \" is kept; the value "
         "runs to whitespace, &, ; or \".",
         ("i",), required=("=", ":")),
    Rule("kv_secret_short", "secret",
         r'(^|[^A-Za-z0-9_.-])(' + _SHORT_SECRET_KEYS + r'[ \t]*=[ \t]*)("?)[^ \t\n&;"]+',
         "{1}{2}{3}<secret>",
         "Whole keys key, sig, auth, session followed by = (query strings): the value. No colon form, so "
         "'primary key: id' and 'Session: 3 open' stay.",
         ("i",)),
    Rule("json_secret", "secret",
         r'("' + _JSON_SECRET_KEYS + r'"[ \t]*:[ \t]*")[^"\n]*"',
         '{1}<secret>"',
         "JSON \"<secret key>\": \"value\" (also the whole keys \"key\", \"auth\", \"sig\", \"session\").", ("i",)),
    Rule("json_secret_escaped", "secret",
         r'(\\{1,3}"' + _JSON_SECRET_KEYS + r'\\{1,3}"[ \t]*:[ \t]*\\{1,3}")[^"\\\n]*(?:\\+[^"\\\n][^"\\\n]*)*',
         "{1}<secret>",
         "JSON inside a JSON string, \\\"<secret key>\\\":\\\"value\\\" (same keys as json_secret): the value up to "
         "the escaped closing quote; escapes inside the value (\\\\u00e4) belong to it.", ("i",),
         required=('\\"',)),
    Rule("kv_passphrase", "secret",
         r'(^|[^A-Za-z0-9_.-])([A-Za-z0-9_.-]*passphrases?' + _Q + r'?[ \t]*[=:][ \t]*)(["' + _Q + r']?)[^\n"]+',
         "{1}{2}{3}<secret>",
         "Passphrase key (BACKUP_PASSPHRASE=, passphrase:, set \"X_PASSPHRASE=...\", Python 'passphrase': ...) "
         "followed by = or :: the value including blanks, up to a \" or end of line (kv_secret stops at the first "
         "blank).", ("i",),
         required=("passphrase",)),
    Rule("cli_secret", "secret",
         r'(^|[^A-Za-z0-9_.-])(--passphrase[ \t]+|setx(?:\.exe)?[ \t]+"?[A-Za-z0-9_.-]*' + _SECRET_KEYS
         + r'"?[ \t]+|SetEnvironmentVariable[ \t]*\([ \t]*["' + _Q + r']?[A-Za-z0-9_.-]*' + _SECRET_KEYS + r'["' + _Q
         + r']?[ \t]*,[ \t]*)("[^"\n]*"|' + _Q + r'[^' + _Q + r'\n]*' + _Q + r'|[^ \t\n"' + _Q + r',)]+)',
         "{1}{2}<secret>",
         "Secret as a command-line argument: gpg --passphrase <value>, setx <secret key> <value>, PowerShell "
         "SetEnvironmentVariable(\"<secret key>\", <value>, ...): the value, quoted or up to the next blank.",
         ("i",), required=("passphrase", "setx", "setenvironmentvariable")),
    # 2. e-mail
    Rule("email", "email",
         r'(^|[' + _MAIL_DELIM + r'])[^' + _MAIL_DELIM + r']+@[^' + _MAIL_DELIM + r'.]+(?:\.[^'
         + _MAIL_DELIM + r'.]+)*\.[A-Za-z]{2,}',
         "{1}<email>",
         "E-mail address, local part and domain labels may contain non-ASCII characters."),
    # 3. IP addresses
    Rule("ipv4", "ip", r'\b[0-9]+(?:\.[0-9]+)+\b', "<ip>",
         "Dotted number run; replaced only if it has exactly 4 parts of 1-3 digits each <= 255 "
         "(so 1.24.3, v18.6, 10.0.19045.1 survive).",
         condition="ipv4_octets"),
    Rule("ipv6", "ip",
         r'\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b'
         r'|(?:\b[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6}\b)?',
         "<ip>",
         "Full 8-group or ::-compressed IPv6; replaced only if the match contains a digit 0-9 "
         "(so Foo::Bar and a bare :: survive). Times like 10:15:30 and MAC addresses never match.",
         condition="contains_digit"),
    # 4. user names in paths
    Rule("win_user_path_spaced", "path",
         r'\b([A-Z]:(?:\\+|/)Users(?:\\+|/))' + _NAME + r'+(?: +' + _NAME + r'+)+([\\/"' + _Q + r'])',
         "{1}<user>{2}",
         "C:\\Users\\<name with spaces> when a separator or quote follows the name.", ("i",)),
    Rule("win_user_path", "path", r'\b([A-Z]:(?:\\+|/)Users(?:\\+|/))' + _NAME + r'+', "{1}<user>",
         "C:\\Users\\<name> (also C:/Users/ and JSON-escaped C:\\\\Users\\\\).", ("i",)),
    Rule("unix_user_path_spaced", "path",
         r'(/(?:home|Users)/)' + _NAME + r'+(?: +' + _NAME + r'+)+([/"' + _Q + r'])', "{1}<user>{2}",
         "/home/<name with spaces> and /Users/<name with spaces> when / or a quote follows."),
    Rule("unix_user_path", "path", r'(/(?:home|Users)/)' + _NAME + r'+', "{1}<user>",
         "/home/<name>, /Users/<name>."),
    # 5. patient fields
    Rule("gdt_line", "gdt",
         r'^([ \t]*[0-9]{3}(?:3000|3101|3102|3103|3104|3105|3106|3107|3110|3112|3113))([^\n]+)', "{1}<patient>",
         "GDT/BDT line (optionally indented) with a patient field id: content to end of line.",
         ("m",), patient_value_group=2),
    Rule("gdt_inline", "gdt",
         r'(' + _GDT_PREFIX + r'[0-9]{3}' + _GDT_TEXT_FIELDS + r')([^ \t\n0-9,;.:/\\)\]}&=<>|"' + _Q + r'][^\n]*)',
         "{1}<patient>",
         "GDT name/title/insurance/address record inside a line (after space, tab, : | = > \" ' , ; ( [), "
         "content starting with neither a digit nor punctuation (id=1233104, survives): to end of line.",
         patient_value_group=2),
    Rule("gdt_inline_path_spaced", "gdt",
         r'([/\\])([0-9]{3})(' + _GDT_TEXT_FIELDS + r')([^ \t\n0-9/\\.<][^\t\n/\\.<]*)', "{1}{2}{3}<patient>",
         "GDT name/title/insurance/address record as a path segment after / or \\ (export/0253102Max Muster.txt): "
         "the content up to the next / \\ . < or line end, blanks included; replaced only if the 3-digit length "
         "fits the content (gdt_length).",
         condition="gdt_length", patient_value_group=4),
    Rule("gdt_inline_path", "gdt",
         r'([/\\])([0-9]{3})(' + _GDT_TEXT_FIELDS + r')([^ \t\n0-9/\\.<][^ \t\n/\\.<]*)', "{1}{2}{3}<patient>",
         "Same as gdt_inline_path_spaced, content up to the next blank as well (C:\\gdt\\0153101Muster.gdt, "
         "/0193101Mustermann and more); replaced only if the length fits (gdt_length). GET /api/items/1233104/ "
         "survives.",
         condition="gdt_length", patient_value_group=4),
    Rule("gdt_inline_city", "gdt",
         r'(' + _GDT_PREFIX_PATH + r')([0-9]{3})(3106)([0-9]{4,5}[ \t]+[^ \t\n0-9][^\n]*)', "{1}{2}{3}<patient>",
         "GDT 3106 postcode and city inside a line (also after / or \\; \"0233106 80331 München\" without the "
         "blank after the id): "
         "to end of line; replaced only if the length prefix fits (gdt_length_prefix).",
         condition="gdt_length_prefix", patient_value_group=4),
    Rule("gdt_inline_numeric", "gdt",
         r'(' + _GDT_PREFIX_PATH + r')([0-9]{3})(3000|3103|3105|3106|3110|3112|3113)( ?[0-9A-Za-z]+)',
         "{1}{2}{3}<patient>",
         "GDT number/birth date/insurance/sex/zip record inside a line (also after / or \\; one blank before the "
         "content allowed); "
         "replaced only if the 3-digit length fits the content (gdt_length).",
         condition="gdt_length", patient_value_group=4),
    Rule("dicom_json_object", "dicom",
         r'("0010,?' + _DICOM_PATIENT_TAGS + _JQ + r'[ \t\n]*:[ \t\n]*\{[^{}]*"(?:Value|InlineBinary)' + _JQ
         + r'[ \t\n]*:[ \t\n]*)'
         r'(\[[^\]\[{]*\]|' + _JQ + r'[^"\n]*"|[^ \t\n,{}\[\]"][^,}\n"]*)',
         "{1}<patient>",
         "DICOM JSON / Orthanc object of a patient tag (may span lines; also escaped inside a JSON string, "
         "\\\"00100010\\\"): its \"Value\" (array, string or scalar) or \"InlineBinary\".",
         patient_value_group=2),
    Rule("dicom_json", "dicom",
         r'("(?:0010,?' + _DICOM_PATIENT_TAGS + r'|Alphabetic|Ideographic|Phonetic)' + _JQ
         + r'[ \t]*:[ \t]*(?:\n[ \t]*)?)'
         r'([^ \t\n{][^\n]*)',
         "{1}<patient>",
         "DICOM JSON patient tag key or person-name component with a value (same or next line, not an object; "
         "the key may be escaped inside a JSON string): rest of the value line.",
         patient_value_group=2),
    Rule("dicom_xml_pn", "dicom",
         r'(<(?:FamilyName|GivenName|MiddleName|NamePrefix|NameSuffix)>)([^<\n]+)', "{1}<patient>",
         "Person-name components of DICOM XML (native DICOM model): element text.",
         patient_value_group=2),
    Rule("dicom_tag", "dicom",
         r'([(\[]0010,[ \t]*' + _DICOM_PATIENT_TAGS + r'[)\]][ \t]*(?:[=:][ \t]*)?)' + _VALUE, "{1}<patient>",
         "DICOM patient tag (0010,xxxx) or [0010,xxxx] (dcmtk/pydicom dumps): rest of line, including the VR.",
         patient_value_group=2),
    Rule("dicom_tag_bare", "dicom",
         r'\b(0010,[ \t]*' + _DICOM_PATIENT_TAGS + r'\b(?:[ \t]*[=:][ \t]*|[ \t]+))([^ \t\n"][^\n]*)', "{1}<patient>",
         "Bare DICOM patient tag 0010,xxxx followed by =, : or blanks: rest of line.",
         patient_value_group=2),
    Rule("dicom_keyword", "dicom",
         _LEFT + r'(' + _DICOM_KEYWORDS + r')' + _KV_SEP + _VALUE, "{1}{2}{3}<patient>",
         "DICOM keyword (any case, not glued to a letter or digit on the left) followed by =, :, >, ^ (value may "
         "be on the next line) or blanks: rest of the value line. Prose like 'PatientID missing' is masked too.",
         ("i",), patient_value_group=4, required=("patient",)),
    Rule("fhir_patient", "patient",
         r'(' + _JQ + r'resourceType' + _JQ + r'[ \t\n]*:[ \t\n]*' + _JQ + r'Patient' + _JQ + r')(' + _BLOCK + r')',
         "{1}<patient>",
         "FHIR Patient resource as JSON (\"resourceType\": \"Patient\", also escaped or across a line break): the "
         "rest of the line and every following non-empty line. The marker "
         "counts as patient data even if nothing follows it.",
         patient_value_group=2, required=("resourceType",)),
    Rule("fhir_patient_xml", "patient",
         r'(<(?:[A-Za-z0-9_.-]+:)?Patient[ \t]+xmlns=' + _JQ + r'http://hl7\.org/fhir' + _JQ + r'[^<>\n]*>'
         r'|<(?:[A-Za-z0-9_.-]+:)?Patient(?:[ \t][^<>\n]*)?>(?:[ \t\n]*<!--(?:[^-\n]|-[^-\n]){0,200}-->){0,3}'
         r'[ \t\n]*<(?:[A-Za-z0-9_.-]+:)?(?:id|meta|text|extension|modifierExtension|implicitRules|language|contained'
         r'|identifier|active|name|telecom|gender|birthDate|deceasedBoolean|deceasedDateTime|address|maritalStatus'
         r'|multipleBirthBoolean|multipleBirthInteger|photo|contact|communication|generalPractitioner'
         r'|managingOrganization|link)[ \t/>])(' + _BLOCK + r')',
         "{1}<patient>",
         "FHIR Patient resource as XML: <Patient xmlns=\"http://hl7.org/fhir\" ...> always; an element <Patient> "
         "without its own xmlns (inside a Bundle; case-sensitive, namespace prefix and attributes allowed) when, "
         "after up to three comments, a FHIR Patient child element follows (id, meta, text, extension, identifier, "
         "active, name, telecom, gender, birthDate, address, contact, ...): the rest of the line and every "
         "following non-empty line. <Patient>text</Patient> is left to patient_xml.",
         patient_value_group=2, required=("<Patient", ":Patient")),
    Rule("fhir_person_array", "patient",
         r'(' + _JQ + r'(?:name|address|telecom)' + _JQ + r'[ \t]*:[ \t\n]*\[[ \t\n]*\{[ \t\n]*)([^{} \t\n][^{}]*)',
         "{1}<patient>",
         "FHIR HumanName/Address/ContactPoint array \"name\": [{...}] (also \"address\", \"telecom\"; may span "
         "lines): the content of its first object up to the next brace.",
         patient_value_group=2, required=("name", "address", "telecom")),
    Rule("fhir_kvid", "patient",
         r'([/:]kvid[A-Za-z0-9_.-]*' + _JQ + r'[ \t]*,[ \t\n]*' + _JQ + r'value' + _JQ + r'[ \t]*:[ \t]*)([^ \t\n][^\n]*)',
         "{1}<patient>",
         "FHIR identifier with a KVID system (http://fhir.de/sid/gkv/kvid-10, kvid after / or :) followed by "
         "its \"value\": rest of the value line.",
         ("i",), patient_value_group=2, required=("kvid",)),
    Rule("fhir_kvid_value_first", "patient",
         r'(' + _JQ + r'value' + _JQ + r'[ \t]*:[ \t]*)(' + _JQ + r'[^"\n]*"[ \t]*,[ \t\n]*' + _JQ + r'system' + _JQ
         + r'[ \t]*:[ \t]*' + _JQ + r'[^"\n]*[/:]kvid[^\n]*)',
         "{1}<patient>",
         "FHIR identifier \"value\" followed by a KVID \"system\" (value-before-system order): the value to end "
         "of line.",
         ("i",), patient_value_group=2, required=("kvid",)),
    Rule("fhir_kvid_xml", "patient",
         r'([/:]kvid[A-Za-z0-9_.-]*' + _JQ + r'[ \t]*/?>[ \t\n]*<(?:[A-Za-z0-9_.-]+:)?value[ \t]+value=' + _JQ
         + r')([^"\n]+)',
         "{1}<patient>",
         "FHIR XML identifier: <system value=\".../kvid-10\"/> followed by <value value=\"...\"/>: the value.",
         ("i",), patient_value_group=2, required=("kvid",)),
    Rule("fhir_xml_name", "patient",
         r'(<(?:[A-Za-z0-9_.-]+:)?(?:family|given)[ \t]+value=' + _JQ + r')([^"\n]+)',
         "{1}<patient>",
         "FHIR XML name parts <family value=\"...\"/>, <given value=\"...\"/>: the attribute value.",
         patient_value_group=2, required=("family", "given")),
    Rule("cda_patient", "patient",
         r'(<' + _XML_NS + r'(?:recordTarget|patientRole)' + _XML_TAG_END + r')(' + _BLOCK + r')',
         "{1}<patient>",
         "HL7 CDA / eArztbrief <recordTarget> or <patientRole>: the rest of the line and every following "
         "non-empty line. The element counts as patient data even if nothing follows it.",
         ("i",), patient_value_group=2, required=("recordtarget", "patientrole")),
    Rule("hl7_pid", "patient",
         r'^([ \t]*PID\|)([^\n]*)', "{1}<patient>",
         "HL7 v2 PID segment (patient identification): the rest of the segment line.",
         ("m",), patient_value_group=2, required=("PID|",)),
    Rule("csv_patient_header", "patient",
         r'(^|[;\t|,])( *"?' + _TABLE_LABELS + r'"?)([ \t]*(?:[;\t|]|,[^ \t\n])' + _BLOCK + r')',
         "{1}{2}<patient>",
         "Delimited table header (; tab | or , without a blank after it) with a patient column followed by "
         "another cell: the rest of the header and every following non-empty line (the data rows).",
         ("i", "m"), patient_value_group=3, required=(";", "\t", "|", ",")),
    Rule("csv_patient_header_last", "patient",
         r'((?:[;\t|] *|,)"?' + _TABLE_LABELS + r'"?)([ \t]*\n[^\n]+(?:\n[^\n]+)*)',
         "{1}<patient>",
         "Delimited table header whose last cell is a patient column, followed by data rows: every following "
         "non-empty line.",
         ("i",), patient_value_group=2, required=(";", "\t", "|", ",")),
    Rule("csv_person_header", "patient",
         _HEADER_CELLS + r'( *["' + _Q + r']?' + _TABLE_PERSON_WORDS + r'["' + _Q + r']?)([ \t]*(?:[;\t|]|,[^ \t\n])' + _BLOCK + r')',
         "{1}{2}<patient>",
         "Header line made of cells (; tab | or , without a blank after it, so prose 'Name, Adresse fehlen' stays; "
         "before the cell { } = only inside "
         "groups and ( ) [ ] only as balanced, not nested groups, so a timestamp, [INFO], label: or Dauer (h) may "
         "precede; the word may be quoted with \" or ') with a person "
         "column Name, Name 1, Full/Display Name, Vor- und Nachname, Mitarbeiter(in), Mitarbeiter:innen, "
         "Mitarbeitende, Employee, User Name, Benutzer, Benutzername, Benutzer(name), Nutzer(in), Person, "
         "Versicherte, Versicherter, Versicherte(r), Versicherte*r, Kunde, Kunden, Kunde(n), Kunde/Kundin, Kund:in, "
         "Kundenname, Arzt, Arzt/Ärztin, Ärzte, Ärzt:in, Zahn-/Fach-/Hausarzt, Patienten, Patientinnen, Patient:in, "
         "Pat., Behandler(in), Bearbeiter(in), Therapeut(in), Teilnehmer(in), Teilnehmende, Behandelnde, "
         "Ansprechpartner(in), Inhaber(in), Klient(in), Betreuer(in), Customer, Client, Doctor, Physician, Staff "
         "(gender forms -in, -innen, :in, *in, /in, _in, /-in, (in), (innen)) followed by another cell: the rest of "
         "the header and every following non-empty line.",
         ("i", "m"), patient_value_group=3, required=(";", "\t", "|", ",")),
    Rule("csv_person_header_last", "patient",
         r'^(' + _CELLS + r')( *["' + _Q + r']?' + _TABLE_PERSON_WORDS + r'["' + _Q + r']?)([ \t]*\n[^\n]+(?:\n[^\n]+)*)',
         "{1}{2}<patient>",
         "Header line made of cells whose last cell is a person column (same words and cells as "
         "csv_person_header, e.g. Nr;Name), followed by data rows: every following non-empty line.",
         ("i", "m"), patient_value_group=3, required=(";", "\t", "|", ",")),
    Rule("db_error_row", "patient",
         r'\b((?:Failing row contains|Fehlgeschlagene Zeile enthält)[ \t]*'
         r'|(?:Key|Schlüssel)[ \t]*»?\([^()\n]*\)[ \t]*=[ \t]*)(\([^\n]*)',
         "{1}<patient>",
         "PostgreSQL error DETAIL with row values (Failing row contains (...), Key (col)=(value), also German): "
         "the values to end of line, whatever the table.",
         ("i",), patient_value_group=2, required=("row contains", "zeile enthält", "key", "schlüssel")),
    Rule("sql_parameters", "patient",
         r'(\[parameters:[ \t]*|binding parameter[ \t]*(?:\[[0-9]+\][ \t]*as[ \t]*\[[A-Za-z_]*\][ \t]*-'
         r'|\([^()\n]*\)[ \t]*<-)[ \t]*)([^ \t\n][^\n]*)',
         "{1}<patient>",
         "Bound SQL parameters (SQLAlchemy [parameters: ...], Hibernate binding parameter [1] as [VARCHAR] - "
         "[...] and (1:VARCHAR) <- [...]): the values to end of line, whatever the statement.",
         ("i",), patient_value_group=2, required=("parameter",)),
    Rule("patient_object", "patient",
         _LEFT + r'(patient(?:in)?[A-Za-z0-9_]{0,64}[ \t]{0,8})([(\[{][ \t]*[A-Za-z_][A-Za-z0-9_]{0,64}[ \t]*=[^\n]*)',
         "{1}{2}<patient>",
         "toString of a patient object (Kotlin Patient(id=...), Java record Patient[id=...], Lombok "
         "PatientDto{id=...}, app_patient(...); at most 64 more word characters and 8 blanks before the bracket, so "
         "every start stays bounded): "
         "from the bracket to end of line.",
         ("i",), patient_value_group=3, required=("patient",)),
    Rule("birth_date_prose", "patient",
         r'((?:^|[^A-Za-z0-9])(?:geb\.?|geboren)[ \t]*(?:am[ \t]+)?)'
         r'([0-9]{1,2}\.[ \t]?[0-9]{1,2}\.[ \t]?[0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})',
         "{1}<patient>",
         "Birth date in prose: geb. 12.08.1964, geboren am 12.08.1964 (also ISO dates): the date.",
         ("i",), patient_value_group=2, required=("geb",)),
    Rule("birth_date_star", "patient",
         r'((?:\(|,|[Gg]eb\.|[A-Za-z])[ \t]?\*[ \t]?)([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{2,4})', "{1}<patient>",
         "Birth date as *12.08.1964 (one blank allowed on each side of the star) after (, a comma, Geb. or a letter "
         "(Max (* 12.08.1964), Muster, * 1.2.64, Geb. * 01.03.1980, Max Muster *01.03.1980): the date. Line-start "
         "bullets (* 17.11.2026), a star after a sentence dot (notes. * 17.11.2026) and ISO dates (*2026-11-17) stay.",
         patient_value_group=2, required=("*",)),
    Rule("patient_label", "patient",
         _LEFT + r"(" + _PATIENT_LABELS + r")" + _KV_SEP + _VALUE, "{1}{2}{3}<patient>",
         "Patient labels (patient_id, patient.name, Patient's Name, patientFirstName, birthDate, birthTime, "
         "date_of_birth, dob, Geburtsdatum, Geb.-Datum, Patienten-Nr., Pat.-Nr., Vers.-Nr., Fall-Nr., "
         "Versicherten-Nr., KVNR, KVID, insurance number, Name des Patienten, ...; any case, not glued to a letter "
         "or digit on the left) followed by =, :, >, ^ (key quote may be escaped; value may be up to three lines "
         "further down) or blanks: rest of the value line.",
         ("i",), patient_value_group=4, required=("pat", "birth", "date", "dob", "geb", "vers", "fall", "kv", "insurance")),
    Rule("person_label", "patient",
         _LEFT + r"(" + _PERSON_WORDS + r")" + _COLON_SEP + _VALUE, "{1}{2}{3}<patient>",
         "Patient, Patientin, Vorname, Nachname, Geburtsname, firstName/lastName/givenName/familyName/"
         "middle_name/surname followed by = or : (also as quoted, escaped JSON or dict key; value may be up to "
         "three lines further down): rest of the value line.",
         ("i",), patient_value_group=4, required=("pat", "name")),
    Rule("person_xml", "patient",
         r'(<' + _XML_NS + r'(?:vorname|nachname|geburtsname|patientin|given|family)' + _XML_TAG_END + r')'
         + _XML_TEXT,
         "{1}<patient>",
         "XML elements <Vorname>, <Nachname>, <Geburtsname>, <Patientin> and the HL7 CDA name parts <given>, "
         "<family> (namespace prefix and attributes allowed, text may start on the next line): element text up "
         "to <.",
         ("i",), patient_value_group=2),
    Rule("patient_xml", "patient",
         r'(<' + _XML_NS + r'patient' + _XML_TAG_END + r')' + _XML_TEXT_TRIMMED
         + r'([ \t]*(?:\n[ \t]*)?</' + _XML_NS + r'patient[ \t]*>)',
         "{1}<patient>{3}",
         "XML element <Patient>...</Patient> (any case, namespace prefix and attributes allowed): its text. The "
         "closing tag is required, so the token <patient> itself never opens an element.",
         ("i",), patient_value_group=2),
    # 6. long runs
    Rule("base64_run", "secret", r'(^|[^A-Za-z0-9_-])[A-Za-z0-9_-]*[A-Za-z0-9+/]{40,}[A-Za-z0-9+/_-]*', "{1}<secret>",
         "Standard base64 run (with + and /) of >= 40 chars together with the base64url "
         "characters (- _) glued to it on either side (token_<run> and <run>-tail become one <secret>); replaced "
         "only if it contains an uppercase letter, a lowercase letter and a digit. Starts after any character "
         "but A-Za-z0-9 - _ (also after / or +: a/b_<run> becomes a/<secret>); = padding stays (<secret>==), so a "
         "name of 40+ characters that fails the condition cannot swallow the = before its value; runs before "
         "base64url_run. A glued - or _ part counts for the condition, so a ticket key in a path (PZ-1234/...) can "
         "make a lower-case path of 40+ characters <secret>. "
         "Paths of 40+ characters without . - _ that mix upper case, lower case and digits are masked too.",
         condition="upper_lower_digit"),
    Rule("base64url_run", "secret", r'[A-Za-z0-9_-]{40,}', "<secret>",
         "base64url run of >= 40 chars; replaced only if it contains an uppercase letter, a lowercase letter "
         "and a digit (long identifiers survive).",
         condition="upper_lower_digit"),
    Rule("hex_run", "secret", r'[0-9A-Fa-f]{32,}', "<secret>",
         "Hex run of >= 32 chars (git SHAs, hashes). UUIDs with dashes survive."),
)

_PATIENT_RULES = tuple(r for r in RULES if r.patient_value_group)
MAX_PASSES = 4


# ANSI escape sequences: CSI (colours, cursor) and OSC terminated by BEL or ST. Removed in step 0, so a
# coloured label (ESC[36mpatient_nameESC[0m=...) reads like a plain one.
# Only complete, well-formed sequences: CSI with at most 64 parameter and 8 intermediate bytes, OSC on one
# line with at most 256 bytes. A longer or multi-line "sequence" stays, so it cannot swallow lines.
ANSI_ESCAPE = r'\x1b\[[0-9;:?]{0,64}[ -/]{0,8}[@-~]|\x1b\][^\x07\x1b\n\r]{0,256}(?:\x07|\x1b\\)'
_ANSI = re.compile(ANSI_ESCAPE)
# What is left of an escape sequence after that (a CSI with huge parameters, a lone ESC, the ESC of an
# overlong or multi-line OSC) becomes a blank, so it neither hides nor glues a label ("ESC[1;1;...mPatientName").
ANSI_REST = r'\x1b\[[0-9;:?]*[ -/]*[@-~]?|\x1b'
_ANSI_REST = re.compile(ANSI_REST)
# Gate view only: ESC and a CSI's head become a blank, the final byte stays.
ESC_HEAD = r'\x1b(?:\[[0-9;:?]*[ -/]*)?'
_ESC_HEAD = re.compile(ESC_HEAD)


def _normalize_lines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")


def normalize_report_text(text: str) -> str:
    """Step 0 of the protocol: complete ANSI escape sequences are removed (ANSI_ESCAPE), what is left
    of other ones becomes a blank (ANSI_REST), CRLF and lone CR become LF, U+00A0 becomes a space."""
    if "\x1b" in text:
        text = _ANSI_REST.sub(" ", _ANSI.sub("", text))
    return _normalize_lines(text)


def _one_pass(text: str, hits: Optional[set[str]] = None) -> str:
    for rule in RULES:
        text = rule.apply(text, hits)
    return text


def _sanitize(text: str, hits: Optional[set[str]]) -> str:
    text = normalize_report_text(text)
    for _ in range(MAX_PASSES):
        masked = _one_pass(text, hits)
        if masked == text:
            break
        text = masked
    return text


def sanitize_report_text(text: str) -> str:
    """Mask e-mails, IPs, secrets, user names in paths and patient fields.

    The rule list is repeated until the text no longer changes (at most MAX_PASSES passes):
    a token can open a word boundary that hid a field in the previous pass
    (``<hex>patient-id 4711`` -> ``<secret>patient-id 4711``).
    """
    return _sanitize(text, None)


def _raw_patient_hits(text: str, hits: set[str]) -> None:
    """Patient rules alone over the normalized raw text (no earlier rule may hide a value)."""
    for rule in _PATIENT_RULES:
        if rule.category in hits or not rule.can_match(text):
            continue
        for m in rule.regex.finditer(text):
            if (not rule.condition or _CONDITIONS[rule.condition](m)) and (
                m.group(rule.patient_value_group).rstrip(" \t") != PATIENT_TOKEN
            ):
                hits.add(rule.category)
                break


def sanitize_with_findings(text: str) -> tuple[str, list[str]]:
    """``(sanitize_report_text(text), find_patient_data(text))`` from a single sanitize run."""
    hits: set[str] = set()
    _raw_patient_hits(normalize_report_text(text), hits)
    if "\x1b" in text:
        # The server stores the raw text: whatever an escape sequence hides counts as well.
        _raw_patient_hits(_normalize_lines(_ANSI_REST.sub(" ", text)), hits)
        # ESC (with a CSI's "[", parameters and intermediates) as a blank, the final byte kept: it may be
        # the first letter of a label ("ESC[PatientName=", "ESC[0PatientID=" lose it in both views above).
        _raw_patient_hits(_normalize_lines(_ESC_HEAD.sub(" ", text)), hits)
    masked = _sanitize(text, hits)
    return masked, [c for c in PATIENT_CATEGORIES if c in hits]


def find_patient_data(text: str) -> list[str]:
    """Categories ``gdt``, ``dicom``, ``patient`` with unmasked patient data in ``text``.

    The union of (a) the patient rules alone over the normalized raw text (once with and, if the
    text has an ESC, once with every escape sequence and once with only ESC and a CSI head (ESC_HEAD, final byte kept) turned into a blank) and (b) the patient
    rules that replace a value other than ``<patient>`` during the full multi-pass sanitize.
    (a) catches values that an earlier rule would turn into another token
    (``token=0193101Mustermann`` -> ``token=<secret>``): the server stores the raw text, so they
    count. (b) catches fields that only become visible after a token opened a boundary.
    ``find_patient_data(sanitize_report_text(x)) == []`` holds for every x.
    """
    return sanitize_with_findings(text)[1]

