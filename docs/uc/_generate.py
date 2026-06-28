#!/usr/bin/env python3
"""Generiert docs/uc/index.html aus dem UC-Review-JSON.

Das JSON ist das Ergebnis des UC-Review-Workflows: ein Objekt mit
{result: {ucs[], findingsActionable[], findingsLow[], counts{}}}.
Aufruf:  python3 docs/uc/_generate.py <uc-review.json> [out.html]
"""
import json, html, sys, datetime, collections, os

SRC = sys.argv[1] if len(sys.argv) > 1 else "uc-review.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

d = json.load(open(SRC))
r = d.get("result", d)
ucs = r.get("ucs", [])
counts = r.get("counts", {})
findings = r.get("findingsActionable", [])
findings_low = r.get("findingsLow", [])

def e(x):
    return html.escape(str(x if x is not None else ""))

# kurze Bereichs-Labels (area-Strings sind lang; auf den Teil vor "(" kürzen)
def short_area(a):
    return a.split("(")[0].strip() if a else "Sonstige"

by_area = collections.OrderedDict()
for u in ucs:
    by_area.setdefault(short_area(u.get("area", "")), []).append(u)

actors = sorted({u.get("actor", "") for u in ucs if u.get("actor")})
areas = list(by_area.keys())
gen_date = datetime.date.today().isoformat()

def badge(ok, yes, no):
    cls = "ok" if ok else "warn"
    return f'<span class="badge {cls}">{yes if ok else no}</span>'

# --- Findings-HTML ---
sev_order = {"critical": 0, "high": 1, "medium": 2}
findings_sorted = sorted(findings, key=lambda f: sev_order.get(f.get("severity"), 9))
findings_rows = ""
for f in findings_sorted:
    sev = f.get("severity", "")
    findings_rows += f'''<tr class="f-{e(sev)}">
      <td><span class="sev sev-{e(sev)}">{e(sev.upper())}</span></td>
      <td>{e(f.get("kind",""))}</td>
      <td><code>{e(f.get("uc_id",""))}</code></td>
      <td><strong>{e(f.get("title",""))}</strong><div class="muted">{e(f.get("problem","")[:400])}</div><div class="fix">→ {e(f.get("fix","")[:300])}</div></td>
    </tr>'''

# --- UC-Karten ---
sections = ""
for area, items in by_area.items():
    cards = ""
    for u in sorted(items, key=lambda x: x.get("id", "")):
        doc = badge(u.get("documented"), "dokumentiert", "nicht dokumentiert")
        impl = badge(u.get("implemented_correctly"), "korrekt", "Abweichung")
        cards += f'''<div class="uc" data-actor="{e(u.get("actor",""))}" data-area="{e(area)}" data-doc="{'1' if u.get('documented') else '0'}" data-impl="{'1' if u.get('implemented_correctly') else '0'}" data-text="{e((u.get('id','')+' '+u.get('title','')+' '+u.get('main_flow','')+' '+u.get('endpoints','')).lower())}">
          <div class="uc-head">
            <code class="uc-id">{e(u.get("id",""))}</code>
            <span class="uc-title">{e(u.get("title",""))}</span>
            <span class="actor actor-{e(u.get('actor','').lower())}">{e(u.get("actor",""))}</span>
            {doc} {impl}
          </div>
          <div class="uc-body">
            <div class="row"><span class="k">Auslöser</span><span class="v">{e(u.get("trigger",""))}</span></div>
            <div class="row"><span class="k">Ablauf</span><span class="v">{e(u.get("main_flow",""))}</span></div>
            <div class="row"><span class="k">Endpoints</span><span class="v"><code>{e(u.get("endpoints",""))}</code></span></div>
            <div class="row"><span class="k">UI</span><span class="v">{e(u.get("ui",""))}</span></div>
            <div class="row"><span class="k">Doku</span><span class="v">{e(u.get("doc_location",""))}</span></div>
            <div class="row"><span class="k">Regeln</span><span class="v">{e(u.get("rules",""))}</span></div>
          </div>
        </div>'''
    sections += f'''<section class="area" data-area="{e(area)}">
      <h2>{e(area)} <span class="count">{len(items)}</span></h2>
      {cards}
    </section>'''

actor_opts = "".join(f'<option value="{e(a)}">{e(a)}</option>' for a in actors)
area_opts = "".join(f'<option value="{e(a)}">{e(a)}</option>' for a in areas)

htmldoc = f'''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PraxisZeit — Use-Case-Verzeichnis</title>
<style>
:root{{--p:#2563eb;--bg:#f8fafc;--card:#fff;--bd:#e2e8f0;--mut:#64748b;--ok:#16a34a;--warn:#dc2626;}}
*{{box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:#0f172a;line-height:1.45}}
header{{background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:24px 32px}}
header h1{{margin:0 0 4px;font-size:24px}}
header .sub{{opacity:.9;font-size:14px}}
.stats{{display:flex;gap:14px;flex-wrap:wrap;margin-top:16px}}
.stat{{background:rgba(255,255,255,.15);border-radius:10px;padding:10px 16px;min-width:90px}}
.stat b{{display:block;font-size:22px}}
.stat span{{font-size:12px;opacity:.9}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px 32px}}
.toolbar{{position:sticky;top:0;background:var(--bg);padding:14px 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center;z-index:10;border-bottom:1px solid var(--bd)}}
.toolbar input,.toolbar select{{padding:8px 10px;border:1px solid var(--bd);border-radius:8px;font-size:14px}}
.toolbar input[type=search]{{flex:1;min-width:220px}}
label.chk{{font-size:13px;color:var(--mut);display:flex;align-items:center;gap:5px}}
section.area h2{{font-size:18px;border-left:4px solid var(--p);padding-left:10px;margin:28px 0 12px}}
section.area h2 .count{{background:var(--bd);color:var(--mut);border-radius:10px;padding:1px 9px;font-size:13px;font-weight:600;margin-left:8px}}
.uc{{background:var(--card);border:1px solid var(--bd);border-radius:12px;margin-bottom:12px;overflow:hidden}}
.uc-head{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 16px;cursor:pointer;background:#fafcff}}
.uc-id{{background:#eef2ff;color:#3730a3;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700}}
.uc-title{{font-weight:600;flex:1;min-width:200px}}
.uc-body{{padding:4px 16px 14px;display:none}}
.uc.open .uc-body{{display:block}}
.row{{display:flex;gap:12px;padding:4px 0;border-top:1px solid #f1f5f9;font-size:14px}}
.row .k{{flex:0 0 90px;color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.03em;padding-top:2px}}
.row .v{{flex:1}}
code{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;background:#f1f5f9;padding:1px 5px;border-radius:4px}}
.badge{{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}}
.badge.ok{{background:#dcfce7;color:#166534}}
.badge.warn{{background:#fee2e2;color:#991b1b}}
.actor{{font-size:11px;padding:2px 8px;border-radius:10px;background:#e2e8f0;color:#334155;font-weight:600}}
.actor-admin{{background:#fef3c7;color:#92400e}} .actor-mitarbeiter{{background:#dbeafe;color:#1e40af}}
.actor-system{{background:#ede9fe;color:#5b21b6}} .actor-superadmin{{background:#fae8ff;color:#86198f}} .actor-interessent{{background:#ccfbf1;color:#115e59}}
details.findings{{background:#fff;border:1px solid var(--bd);border-radius:12px;margin:18px 0;padding:8px 16px}}
details.findings summary{{font-weight:700;cursor:pointer;padding:6px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td{{border-top:1px solid var(--bd);padding:8px 6px;vertical-align:top}}
.sev{{font-size:10px;font-weight:700;padding:2px 7px;border-radius:6px}}
.sev-high{{background:#fee2e2;color:#991b1b}} .sev-critical{{background:#7f1d1d;color:#fff}} .sev-medium{{background:#fef3c7;color:#92400e}}
.muted{{color:var(--mut);font-size:12px;margin-top:3px}} .fix{{color:#166534;font-size:12px;margin-top:3px}}
.hidden{{display:none!important}}
footer{{color:var(--mut);font-size:12px;text-align:center;padding:24px}}
</style>
</head>
<body>
<header>
  <h1>PraxisZeit — Use-Case-Verzeichnis</h1>
  <div class="sub">Automatisch aus dem Code inventarisiert &amp; geprüft · Stand {gen_date}</div>
  <div class="stats">
    <div class="stat"><b>{counts.get("ucs",len(ucs))}</b><span>Use-Cases</span></div>
    <div class="stat"><b>{len(areas)}</b><span>Bereiche</span></div>
    <div class="stat"><b>{counts.get("documented","?")}</b><span>dokumentiert</span></div>
    <div class="stat"><b>{counts.get("undocumented","?")}</b><span>nicht dokumentiert</span></div>
    <div class="stat"><b>{counts.get("impl_issues","?")}</b><span>Impl.-Abweichungen</span></div>
    <div class="stat"><b>{len(findings)}</b><span>Findings ≥ medium</span></div>
  </div>
</header>
<div class="wrap">
  <div class="toolbar">
    <input type="search" id="q" placeholder="Suche (ID, Titel, Endpoint, Ablauf)…">
    <select id="fActor"><option value="">Alle Akteure</option>{actor_opts}</select>
    <select id="fArea"><option value="">Alle Bereiche</option>{area_opts}</select>
    <label class="chk"><input type="checkbox" id="fUndoc"> nur undokumentierte</label>
    <label class="chk"><input type="checkbox" id="fImpl"> nur Impl.-Abweichungen</label>
  </div>

  <details class="findings" open>
    <summary>Offene Findings ≥ medium ({len(findings)}) · low: {len(findings_low)}</summary>
    <table><tbody>{findings_rows}</tbody></table>
  </details>

  {sections}
</div>
<footer>PraxisZeit UC-Inventar · {counts.get("ucs",len(ucs))} Use-Cases · generiert aus dem UC-Review-Workflow</footer>
<script>
const q=document.getElementById('q'),fa=document.getElementById('fActor'),far=document.getElementById('fArea'),fu=document.getElementById('fUndoc'),fi=document.getElementById('fImpl');
function apply(){{
  const t=q.value.trim().toLowerCase(),a=fa.value,ar=far.value,u=fu.checked,im=fi.checked;
  document.querySelectorAll('.uc').forEach(c=>{{
    let ok=true;
    if(t&&!c.dataset.text.includes(t))ok=false;
    if(a&&c.dataset.actor!==a)ok=false;
    if(ar&&c.dataset.area!==ar)ok=false;
    if(u&&c.dataset.doc!=='0')ok=false;
    if(im&&c.dataset.impl!=='0')ok=false;
    c.classList.toggle('hidden',!ok);
    if(ok&&(t||u||im))c.classList.add('open');
  }});
  document.querySelectorAll('section.area').forEach(s=>{{
    const vis=[...s.querySelectorAll('.uc')].some(c=>!c.classList.contains('hidden'));
    s.classList.toggle('hidden',!vis);
  }});
}}
[q,fa,far,fu,fi].forEach(el=>el.addEventListener('input',apply));
document.querySelectorAll('.uc-head').forEach(h=>h.addEventListener('click',()=>h.parentNode.classList.toggle('open')));
</script>
</body></html>'''

open(OUT, "w").write(htmldoc)
print(f"geschrieben: {OUT} ({len(htmldoc)} bytes, {len(ucs)} UCs, {len(areas)} Bereiche)")
