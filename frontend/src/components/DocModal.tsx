import { useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import { DocViewerContent, type DocTab } from './DocViewer';

interface DocModalProps {
  open: boolean;
  onClose: () => void;
  initialTab?: DocTab;
}

function getDownloadUrl(tab: DocTab): string {
  return tab === 'cheatsheet'
    ? '/help/CHEATSHEET-MITARBEITER.md'
    : '/help/HANDBUCH-MITARBEITER.md';
}

export function DocModal({ open, onClose, initialTab = 'cheatsheet' }: DocModalProps) {
  const [activeTab, setActiveTab] = useState<DocTab>(initialTab);
  const modalRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const triggerElementRef = useRef<Element | null>(null);

  // Focus management: save trigger, restore on close
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

  // Escape key
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Body scroll lock
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  // Focus trap (live query per keydown) + initial focus on close button
  useEffect(() => {
    if (!open || !modalRef.current) return;
    closeButtonRef.current?.focus();

    function handleTab(e: KeyboardEvent) {
      if (e.key !== 'Tab' || !modalRef.current) return;
      const focusable = Array.from(modalRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      ));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', handleTab);
    return () => document.removeEventListener('keydown', handleTab);
  }, [open]);

  if (!open) return null;

  const downloadUrl = getDownloadUrl(activeTab);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Dokumentation"
        className="relative z-10 bg-white rounded-xl shadow-2xl w-full max-w-2xl h-[80vh] flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <span className="font-semibold text-gray-800 text-sm">📖 Mitarbeiter-Handbuch</span>
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
            isAdmin={false}
            initialTab={initialTab}
            onTabChange={setActiveTab}
          />
        </div>
      </div>
    </div>
  );
}
