import { useEffect, type MouseEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { HelpCircle } from 'lucide-react';
import { useAuthStore } from '../stores/authStore';
import HandbookPage from '../handbuch/components/HandbookPage';
import { HANDBOOKS } from '../handbuch/content';
import { COMIC_SCENES } from '../handbuch/comics/scenes';
import { DIAGRAMS } from '../handbuch/diagrams';
import manifest from '../handbuch/manifest.json';
import type { HandbookId, Manifest } from '../handbuch/types';
import '../handbuch/handbuch.css';

const ADMIN_BOOKS: HandbookId[] = ['praxisleitung', 'mitarbeitende', 'so-rechnet'];
const EMPLOYEE_BOOKS: HandbookId[] = ['mitarbeitende', 'so-rechnet'];

function defaultBook(isAdmin: boolean): HandbookId {
  return isAdmin ? 'praxisleitung' : 'mitarbeitende';
}

export default function Help() {
  const { user } = useAuthStore();
  const { book } = useParams<{ book?: string }>();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'admin';
  const allowed = isAdmin ? ADMIN_BOOKS : EMPLOYEE_BOOKS;
  const valid = !!book && (allowed as string[]).includes(book);
  const current = (valid ? book : defaultBook(isAdmin)) as HandbookId;

  // Die App scrollt in <main>, nicht im Dokument: Ankersprung per scrollIntoView
  // (beim Laden, Buchwechsel und Klick auf einen #-Link).
  useEffect(() => {
    if (!valid) return;
    if (!hash) {
      // Buchwechsel ohne Anker: <main> an den Anfang (sonst bleibt die Scrollposition des alten Buchs).
      document.querySelector('main')?.scrollTo?.({ top: 0 });
      return;
    }
    const el = document.getElementById(decodeURIComponent(hash.slice(1)));
    el?.scrollIntoView();
  }, [hash, valid, current]);

  // Interne Handbuchlinks (handbuch:… -> /help/<buch>#…) per Router statt Seitenneuladen.
  const onInternalLink = (href: string, e: MouseEvent<HTMLAnchorElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(href);
  };

  if (!valid) {
    return <Navigate to={`/help/${defaultBook(isAdmin)}${hash}`} replace />;
  }

  return (
    // Unter lg überdeckt die feste Kopfzeile (pt-16 in <main>) den Sprungpunkt: Abstand erhöhen.
    <div className="[&_[id]]:scroll-mt-20 lg:[&_[id]]:scroll-mt-5">
      <div className="mb-4 flex items-center space-x-3">
        <HelpCircle size={28} className="text-primary" />
        <h1 className="text-2xl font-bold text-gray-900">Hilfe &amp; Dokumentation</h1>
      </div>
      <nav aria-label="Handbücher" className="mb-6 flex flex-wrap gap-x-6 border-b border-gray-200">
        {allowed.map((id) => (
          <Link
            key={id}
            to={`/help/${id}`}
            aria-current={id === current ? 'page' : undefined}
            className={`border-b-2 px-1 pb-3 text-sm font-medium transition-colors ${
              id === current
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {HANDBOOKS[id].title}
          </Link>
        ))}
      </nav>
      <HandbookPage
        key={current}
        handbook={HANDBOOKS[current]}
        manifest={manifest as Manifest}
        imgBase="/help/img"
        linkBase="/help"
        variant="wide"
        comics={COMIC_SCENES}
        diagrams={DIAGRAMS}
        onInternalLink={onInternalLink}
      />
    </div>
  );
}
