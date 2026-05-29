/**
 * Small "BETA" pill, shown next to the PraxisZeit title while the backend
 * reports beta mode (/api/system/info → beta=true). During the beta phase no
 * license is required; the badge signals that state to users.
 */
export default function BetaBadge() {
  return (
    <span
      title="Beta-Version – während der Beta ist keine Lizenz erforderlich"
      className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-amber-400 text-amber-950 align-middle leading-none"
    >
      Beta
    </span>
  );
}
