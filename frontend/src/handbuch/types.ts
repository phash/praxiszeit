export type HandbookId = 'mitarbeitende' | 'praxisleitung' | 'so-rechnet';
export type Persona = 'admin' | 'maria' | 'sarah' | 'thomas' | 'petra' | 'julia' | 'anon';
export type Inline = string;
export type LocatorSpec =
  | { role: string; name: string; exact?: boolean; within?: 'main' | 'dialog' | 'nav' }
  | { label: string; within?: 'main' | 'dialog' }
  | { text: string; within?: 'main' | 'dialog' }
  | { css: string };
export type PrepareStep =
  | { goto: string } | { click: LocatorSpec } | { fill: LocatorSpec; value: string }
  | { monthBack: number } | { waitFor: LocatorSpec } | { scrollTo: LocatorSpec };
export interface MarkerDef { n: number; id: string; locator: LocatorSpec }
export interface ShotDef {
  id: string; persona: Persona; viewport: 'desktop' | 'mobile'; route: string;
  prepare?: PrepareStep[]; crop?: 'full' | 'main' | 'dialog' | { around: string[]; pad: number };
  markers: MarkerDef[]; alt: string; settings?: Record<string, boolean | string | number>;
}
export interface Step { n?: number; text: Inline }
export type Block =
  | { kind: 'task'; id: string; title: string; intro?: Inline; shot?: string; steps: Step[] }
  | { kind: 'tip'; tone: 'info' | 'warn'; text: Inline }
  | { kind: 'comic'; scene: string; text: Inline }
  | { kind: 'diagram'; diagram: string; caption: Inline }
  | { kind: 'table'; head: string[]; rows: Inline[][] }
  | { kind: 'prose'; text: Inline };
export interface Chapter { id: string; title: string; requires?: string; blocks: Block[] }
export interface Handbook { id: HandbookId; title: string; lead: Inline; chapters: Chapter[]; shots: ShotDef[] }
export interface ManifestShot {
  file: string; width: number; height: number; pxWidth: number; pxHeight: number;
  crop: { x: number; y: number; w: number; h: number };
  markers: Record<string, { x: number; y: number; w: number; h: number }>;
}
export type Manifest = Record<string, ManifestShot>;
