import { Link } from 'react-router-dom';
import { Info } from 'lucide-react';

/** Spec 14/P20: ein Hinweis aus GET /dashboard (Text kommt fertig vom Server —
 * EINE Quelle für Wortlaut, Beschriftung des Grundtyps und „neu: …"). */
export interface ScheduleChangeNotice {
  created_at: string;
  effective_from: string;
  kind: 'change' | 'reset' | 'delete';
  text: string;
}

export default function ScheduleChangeNotices({ notices }: { notices?: ScheduleChangeNotice[] | null }) {
  if (!notices || notices.length === 0) return null;
  return (
    <section aria-labelledby="schedule-notices-title" className="bg-blue-50 border border-blue-200 rounded-2xl p-4 mb-6">
      <div className="flex items-start gap-3">
        <Info className="text-blue-600 shrink-0 mt-0.5" size={20} aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <h3 id="schedule-notices-title" className="text-sm font-semibold text-blue-900">
            Hinweis zu Ihrer Arbeitszeit
          </h3>
          <ul className="mt-1 space-y-1">
            {notices.map((n) => (
              <li key={`${n.created_at}-${n.kind}-${n.effective_from}`} className="text-sm text-blue-900 break-words">
                {n.text}
              </li>
            ))}
          </ul>
          <Link to="/profile" className="inline-block mt-2 text-sm font-medium text-blue-800 underline hover:no-underline">
            Arbeitszeit im Profil ansehen →
          </Link>
        </div>
      </div>
    </section>
  );
}
