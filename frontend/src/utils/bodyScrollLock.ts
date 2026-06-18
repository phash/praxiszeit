// Ref-gezählter body-scroll-lock.
//
// Mehrere gleichzeitig offene Overlays (OnboardingModal, DocDrawer, DocModal)
// dürfen sich nicht gegenseitig den Scroll-Lock aufheben: Setzt jedes Overlay
// beim Schließen `document.body.style.overflow = ''`, scrollt der Body wieder,
// obwohl ein anderes Overlay noch offen ist. Stattdessen zählen wir die aktiven
// Locks — `overflow` wird erst beim ersten Lock gesetzt und erst beim letzten
// Unlock wieder freigegeben (auf den vorherigen Wert).
let lockCount = 0;
let previousOverflow = '';

export function lockBodyScroll(): void {
  if (lockCount === 0) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  lockCount += 1;
}

export function unlockBodyScroll(): void {
  lockCount = Math.max(0, lockCount - 1);
  if (lockCount === 0) {
    document.body.style.overflow = previousOverflow;
  }
}
