import { C, DiagramSvg, Swatch, fmt } from './common';
import { CLOSURE_DAYS, CLOSURE_OVERTIME_DAYS, CLOSURE_OVERTIME_HOURS, DAY_TARGET } from './values';

const ALT =
  'Betriebsferien von Montag bis Freitag bei 3 Tagen Resturlaub, wenn die Einstellung „Überzählige Betriebsferien als Überstundenabbau“ eingeschaltet ist: ' +
  'Die Tage werden nach Datum der Reihe nach verbucht. Montag bis Mittwoch zählen als Urlaub, Donnerstag und Freitag als Überstundenausgleich, weil kein ganzer Urlaubstag mehr übrig ist.';

export function ClosureSplit() {
  const cells = CLOSURE_DAYS.map((d, i) => ({ ...d, x: 12 + i * 116 }));
  return (
    <DiagramSvg w={600} h={366} label={ALT}>
      <text x={12} y={26} fontSize={18} fontWeight={700} fill={C.text}>Betriebsferien Mo–Fr, nach Datum</text>
      <text x={12} y={52} fontSize={17} fill={C.muted}>Resturlaub vor dem Tag (Tage)</text>
      {cells.map((c) => {
        const vac = c.type === 'VACATION';
        return (
          <g key={c.label}>
            <text x={c.x + 54} y={84} fontSize={19} fontWeight={700} textAnchor="middle" fill={C.text}>{c.restBefore}</text>
            <rect x={c.x} y={96} width={108} height={72} rx={8} fill={vac ? C.blueSoft : C.amberSoft} stroke={vac ? C.blue : C.amber} strokeWidth={2} />
            <text x={c.x + 54} y={122} fontSize={18} fontWeight={700} textAnchor="middle" fill={C.text}>{c.label}</text>
            <text x={c.x + 54} y={150} fontSize={17} textAnchor="middle" fill={C.text}>{vac ? 'Urlaub' : 'Ausgleich'}</text>
          </g>
        );
      })}
      <text x={12} y={202} fontSize={17} fill={C.text}>Urlaub, solange mindestens 1 ganzer Tag übrig ist.</text>
      <text x={12} y={228} fontSize={17} fill={C.text}>
        Danach Überstundenausgleich: Überstundenkonto sinkt
      </text>
      <text x={12} y={252} fontSize={17} fill={C.text}>
        um {fmt(CLOSURE_OVERTIME_HOURS)} h ({CLOSURE_OVERTIME_DAYS} × {fmt(DAY_TARGET)} h).
      </text>
      <Swatch x={12} y={296} color={C.blue} />
      <text x={36} y={296} fontSize={17} fill={C.text}>Urlaub (zählt gegen das Budget)</text>
      <Swatch x={12} y={320} color={C.amber} />
      <text x={36} y={320} fontSize={17} fill={C.text}>Überstundenausgleich (Soll bleibt, Ist 0 h)</text>
      <text x={12} y={352} fontSize={17} fill={C.text}>Nur mit „Überzählige Betriebsferien als Überstundenabbau“.</text>
    </DiagramSvg>
  );
}
