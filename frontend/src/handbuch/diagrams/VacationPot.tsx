import { C, DiagramSvg, Swatch, fmt } from './common';
import { VAC_BUDGET, VAC_CARRYOVER, VAC_ENTITLEMENT, VAC_REMAINING, VAC_USED } from './values';

const ALT =
  'Urlaubskonto in Tagen: Das Budget besteht aus 30 Tagen Anspruch und 2 Tagen Übertrag, zusammen 32 Tage. ' +
  'Davon sind 4 Tage verbraucht, 28 Tage bleiben als Rest.';

const W = 544;
const px = (d: number) => (d / VAC_BUDGET) * W;
const days = (n: number) => `${fmt(n, 0)} ${n === 1 ? 'Tag' : 'Tage'}`;

export function VacationPot() {
  const x0 = 28;
  return (
    <DiagramSvg w={600} h={330} label={ALT}>
      <text x={x0} y={28} fontSize={18} fontWeight={700} fill={C.text}>Budget</text>
      <rect x={x0} y={38} width={px(VAC_ENTITLEMENT)} height={40} rx={6} fill={C.blue} />
      <rect x={x0 + px(VAC_ENTITLEMENT)} y={38} width={px(VAC_CARRYOVER)} height={40} rx={6} fill={C.violet} />
      <text x={x0 + px(VAC_ENTITLEMENT) / 2} y={64} fontSize={18} fontWeight={700} textAnchor="middle" fill="#FFFFFF">{VAC_ENTITLEMENT}</text>
      <text x={x0 + px(VAC_ENTITLEMENT) + px(VAC_CARRYOVER) / 2} y={64} fontSize={18} fontWeight={700} textAnchor="middle" fill="#FFFFFF">{VAC_CARRYOVER}</text>
      <text x={x0} y={104} fontSize={17} fill={C.text}>Budget = {VAC_ENTITLEMENT} + {VAC_CARRYOVER} = {days(VAC_BUDGET)}</text>

      <text x={x0} y={150} fontSize={18} fontWeight={700} fill={C.text}>Verbrauch und Rest</text>
      <rect x={x0} y={160} width={px(VAC_USED)} height={40} rx={6} fill={C.amber} />
      <rect x={x0 + px(VAC_USED)} y={160} width={px(VAC_REMAINING)} height={40} rx={6} fill={C.green} />
      <text x={x0 + px(VAC_USED) / 2} y={186} fontSize={18} fontWeight={700} textAnchor="middle" fill="#FFFFFF">{VAC_USED}</text>
      <text x={x0 + px(VAC_USED) + px(VAC_REMAINING) / 2} y={186} fontSize={18} fontWeight={700} textAnchor="middle" fill="#FFFFFF">{VAC_REMAINING}</text>
      <text x={x0} y={226} fontSize={17} fill={C.text}>Rest = {VAC_BUDGET} − {VAC_USED} = {days(VAC_REMAINING)}</text>

      <Swatch x={x0} y={268} color={C.blue} />
      <text x={x0 + 24} y={268} fontSize={17} fill={C.text}>Anspruch</text>
      <Swatch x={x0 + 150} y={268} color={C.violet} />
      <text x={x0 + 174} y={268} fontSize={17} fill={C.text}>Übertrag</text>
      <Swatch x={x0} y={298} color={C.amber} />
      <text x={x0 + 24} y={298} fontSize={17} fill={C.text}>Verbraucht</text>
      <Swatch x={x0 + 150} y={298} color={C.green} />
      <text x={x0 + 174} y={298} fontSize={17} fill={C.text}>Rest</text>
    </DiagramSvg>
  );
}
