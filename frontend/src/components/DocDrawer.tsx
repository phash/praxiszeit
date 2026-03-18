import { useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import { DocViewerContent, type DocTab } from './DocViewer';

interface DocDrawerProps {
  open: boolean;
  onClose: () => void;
  isAdmin: boolean;
  initialTab?: DocTab;
}

function getDownloadUrl(isAdmin: boolean, tab: DocTab): string {
  if (tab === 'cheatsheet') {
    return isAdmin ? '/help/CHEATSHEET-ADMIN.md' : '/help/CHEATSHEET-MITARBEITER.md';
  }
  return isAdmin ? '/help/HANDBUCH-ADMIN.md' : '/help/HANDBUCH-MITARBEITER.md';
}

export function DocDrawer({ open, onClose, isAdmin, initialTab = 'cheatsheet' }: DocDrawerProps) {
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Sync activeTab when initialTab changes (triggered by parent before open)
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // Escape key
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Focus management: save trigger element, trap focus inside drawer, restore on close
  const triggerElementRef = useRef<Element | null>(null);

  useEffect(() => {
    if (open) {
      triggerElementRef.current = document.activeElement;
    } else {
      if (triggerElementRef.current && triggerElementRef.current instanceof HTMLElement) {
        triggerElementRef.current.focus();
        triggerElementRef.current = null;
      }
    }
  }, [open]);

  useEffect(() => {
    if (!open || !drawerRef.current) return;
    const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    first?.focus();

    function handleTab(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', handleTab);
    return () => document.removeEventListener('keydown', handleTab);
  }, [open]);

  const downloadUrl = getDownloadUrl(isAdmin, activeTab);
  const title = isAdmin ? 'Admin-Handbuch' : 'Mitarbeiter-Handbuch';

  return (
    <>
      {/* Overlay */}
      <div
        className={`fixed inset-0 bg-black/40 z-40 transition-opacity duration-300 ${
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer — desktop: right side; mobile: bottom sheet */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Dokumentation"
        className={`
          fixed z-50 bg-white flex flex-col shadow-2xl transition-transform duration-300
          md:inset-y-0 md:right-0 md:w-[70%] md:max-w-2xl
          inset-x-0 bottom-0 h-[80vh] rounded-t-2xl
          md:rounded-none md:h-auto
          ${open
            ? 'md:translate-x-0 translate-y-0'
            : 'md:translate-x-full translate-y-full'
          }
        `}
      >
        {/* Mobile drag handle */}
        <div className="md:hidden w-10 h-1 bg-gray-300 rounded-full mx-auto mt-3 mb-1 flex-shrink-0" />

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <span className="font-semibold text-gray-800 text-sm">📖 {title}</span>
          <div className="flex items-center gap-2">
            <a
              href={downloadUrl}
              download
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <Download size={13} />
              <span>.md</span>
            </a>
            <button
              ref={closeButtonRef}
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              aria-label="Schließen"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <DocViewerContent
            key={initialTab}
            isAdmin={isAdmin}
            initialTab={initialTab}
            onTabChange={setActiveTab}
          />
        </div>
      </div>
    </>
  );
}
