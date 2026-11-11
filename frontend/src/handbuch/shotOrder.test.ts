import { describe, expect, it } from 'vitest';
import { ALL_SHOTS } from './content/index';
import { orderShots, readsAuditLog } from './shotOrder';
import type { ShotDef } from './types';

const shot = (id: string, route: string, settings?: ShotDef['settings']): ShotDef =>
  ({ id, persona: 'admin', viewport: 'desktop', route, markers: [], alt: id, settings });

describe('orderShots (R36)', () => {
  it('puts audit-log shots before everything else, keeping the relative order', () => {
    const out = orderShots([
      shot('a', '/a'), shot('s', '/admin/settings', { shift_planning_enabled: true }),
      shot('p1', '/admin/audit-log'), shot('b', '/b'), shot('p2', '/admin/audit-log?x=1'),
    ]);
    expect(out.map((d) => d.id)).toEqual(['p1', 'p2', 'a', 's', 'b']);
  });

  it('keeps every shot exactly once', () => {
    const out = orderShots(ALL_SHOTS);
    expect(out).toHaveLength(ALL_SHOTS.length);
    expect(new Set(out.map((d) => d.id)).size).toBe(ALL_SHOTS.length);
  });

  it('in the real content no settings-changing shot precedes an audit-log shot', () => {
    const out = orderShots(ALL_SHOTS);
    const firstSettings = out.findIndex((d) => d.settings && Object.keys(d.settings).length > 0);
    const lastAudit = out.map(readsAuditLog).lastIndexOf(true);
    expect(lastAudit).toBeGreaterThanOrEqual(0);
    expect(firstSettings).toBeGreaterThan(lastAudit);
  });
});
