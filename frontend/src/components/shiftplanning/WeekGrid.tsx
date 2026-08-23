import { useDraggable, useDroppable } from '@dnd-kit/core';
import { AlertTriangle, Plus, Users } from 'lucide-react';
import { HOUR_PX, computeWeekLayout, visibleWeekdays, type SlotBox, type WeekLayout } from './weekGridUtils';
import { WEEKDAY_LABELS_LONG, type ShiftSlot } from '../../api/shiftPlanning';

interface WeekGridProps {
  slots: ShiftSlot[];
  editable?: boolean;
  onSlotClick?: (slot: ShiftSlot) => void;
  onEmptyClick?: (weekday: number) => void;
  // #321: when set, render only this one weekday full-width (Tagesansicht).
  singleDay?: number;
  // #371: configured planner weekdays (0=Mo … 6=So). Undefined → Mo–Fr default.
  weekdays?: number[];
}

function SlotBody({ slot }: { slot: ShiftSlot }) {
  const names = slot.assignments.map((a) => a.user_name).join(', ');
  return (
    <>
      <div className="flex items-start justify-between gap-1">
        {/* #443: kein truncate mehr — der Name bricht um. Bei mehreren parallelen
            Slots wird die Spur schmal, vertikal ist aber Platz. */}
        <span className="font-semibold break-words">{slot.workstation_name}</span>
        {slot.understaffed && <AlertTriangle size={12} className="shrink-0 mt-0.5" aria-label="Unterbesetzt" />}
      </div>
      <div className="opacity-90">
        {slot.start_time}–{slot.end_time}
      </div>
      <div className="flex items-start gap-1 opacity-90">
        <Users size={11} className="shrink-0 mt-0.5" />
        <span className="break-words">{names || (slot.min_staff > 0 ? `0/${slot.min_staff}` : '—')}</span>
      </div>
      {/* #443-Fix-Runde 1: » statt ↳ — muss zum Marker im PDF-Export passen
          (shift_plan_export_service._cell_paragraph); ↳ ist dort im
          Standard-PDF-Zeichensatz nicht darstellbar. */}
      {slot.note && (
        <div className="opacity-80 italic break-words">» {slot.note}</div>
      )}
    </>
  );
}

function blockStyle(slot: ShiftSlot, box: SlotBox): React.CSSProperties {
  const color = slot.color || '#2563eb';
  // left/right 2px gutter inside the lane so adjacent lanes stay visually separated
  return {
    top: box.top,
    // #443: minHeight statt height — der Block wächst mit seinem Inhalt, statt
    // ihn abzuschneiden. Die zeitproportionale Höhe bleibt die Untergrenze.
    minHeight: box.height,
    left: `calc(${box.leftPct}% + 2px)`,
    width: `calc(${box.widthPct}% - 4px)`,
    backgroundColor: `${color}1a`, // ~10% alpha
    borderLeft: `3px solid ${color}`,
    // #443: sagt an, dass die Blockhöhe hier nicht mehr die Uhrzeit meint.
    borderBottom: box.grown ? `1px dashed ${color}` : undefined,
    // #305 M2d: dashed amber outline when ≥1 assigned person is not trained.
    outline: slot.unqualified ? '1px dashed #d97706' : undefined,
    outlineOffset: slot.unqualified ? '-2px' : undefined,
  };
}

function DraggableBlock({ slot, box, onClick }: { slot: ShiftSlot; box: SlotBox; onClick?: (s: ShiftSlot) => void }) {
  const { attributes, listeners, setNodeRef: dragRef, transform, isDragging } = useDraggable({
    id: `block-${slot.id}`,
    data: { type: 'block', slot },
  });
  const { setNodeRef: dropRef, isOver } = useDroppable({
    id: `slot-${slot.id}`,
    data: { type: 'slot', slot },
  });

  const setRefs = (el: HTMLElement | null) => {
    dragRef(el);
    dropRef(el);
  };

  return (
    <div
      ref={setRefs}
      style={{
        ...blockStyle(slot, box),
        transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
        opacity: isDragging ? 0.6 : 1,
        boxShadow: isOver ? '0 0 0 2px #2563eb inset' : undefined,
        zIndex: isDragging ? 20 : 1,
      }}
      className="absolute rounded-md p-1 text-[11px] leading-tight text-gray-800 cursor-grab touch-none"
      title={box.grown ? 'Anzeige reicht über das Zeitfenster hinaus' : undefined}
      {...listeners}
      {...attributes}
      onClick={() => onClick?.(slot)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick?.(slot);
        }
      }}
    >
      <SlotBody slot={slot} />
    </div>
  );
}

function StaticBlock({ slot, box }: { slot: ShiftSlot; box: SlotBox }) {
  return (
    <div
      style={blockStyle(slot, box)}
      className="absolute rounded-md p-1 text-[11px] leading-tight text-gray-800"
      title={box.grown ? 'Anzeige reicht über das Zeitfenster hinaus' : undefined}
    >
      <SlotBody slot={slot} />
    </div>
  );
}

function DayColumn({
  weekday,
  slots,
  layout,
  editable,
  onSlotClick,
  onEmptyClick,
}: {
  weekday: number;
  slots: ShiftSlot[];
  layout: WeekLayout;
  editable: boolean;
  onSlotClick?: (s: ShiftSlot) => void;
  onEmptyClick?: (weekday: number) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `day-${weekday}`, data: { type: 'day', weekday } });
  const inner = (
    <div
      className={`relative overflow-visible ${isOver && editable ? 'bg-primary/5' : ''}`}
      style={{ height: layout.height }}
      onClick={(e) => {
        if (editable && onEmptyClick && e.target === e.currentTarget) onEmptyClick(weekday);
      }}
    >
      {/* hour gridlines */}
      {layout.hourMarks.slice(1).map((_, i) => (
        <div
          key={i}
          className="absolute left-0 right-0 border-t border-gray-100"
          style={{ top: (i + 1) * HOUR_PX }}
        />
      ))}
      {slots.map((slot) =>
        editable ? (
          <DraggableBlock key={slot.id} slot={slot} box={layout.boxes[slot.id]} onClick={onSlotClick} />
        ) : (
          <StaticBlock key={slot.id} slot={slot} box={layout.boxes[slot.id]} />
        ),
      )}
    </div>
  );
  return editable ? <div ref={setNodeRef}>{inner}</div> : inner;
}

export default function WeekGrid({ slots, editable = false, onSlotClick, onEmptyClick, singleDay, weekdays }: WeekGridProps) {
  // #321: Tagesansicht renders just one weekday; week view the configured days (#371).
  const days = visibleWeekdays(singleDay, weekdays);

  // #371: only slots on visible weekdays drive the layout — a legacy slot on a
  // hidden weekday must not stretch the grid's time axis for the visible days.
  const visibleSlots = slots.filter((s) => days.includes(s.weekday));
  const layout = computeWeekLayout(visibleSlots);
  const byDay = (wd: number) =>
    visibleSlots.filter((s) => s.weekday === wd).sort((a, b) => a.start_time.localeCompare(b.start_time));

  return (
    <div className="overflow-x-auto">
      <div
        className={singleDay !== undefined ? 'grid' : 'min-w-[760px] grid'}
        style={{ gridTemplateColumns: `48px repeat(${days.length}, 1fr)` }}
      >
        {/* header row */}
        <div className="h-8" />
        {days.map((wd) => (
          <div
            key={wd}
            className="h-8 flex items-center justify-between px-2 text-xs font-semibold text-gray-600 border-b border-gray-200"
          >
            <span className="truncate">{WEEKDAY_LABELS_LONG[wd]}</span>
            {editable && onEmptyClick && (
              <button
                type="button"
                onClick={() => onEmptyClick(wd)}
                aria-label={`Slot am ${WEEKDAY_LABELS_LONG[wd]} hinzufügen`}
                className="text-gray-400 hover:text-primary"
              >
                <Plus size={14} />
              </button>
            )}
          </div>
        ))}

        {/* time axis */}
        <div className="relative" style={{ height: layout.height }}>
          {layout.hourMarks.map((h, i) => (
            <div
              key={h}
              className="absolute right-1 -translate-y-1/2 text-[10px] text-gray-400"
              style={{ top: i * HOUR_PX }}
            >
              {String(h).padStart(2, '0')}:00
            </div>
          ))}
        </div>

        {/* day columns */}
        {days.map((wd) => (
          <div key={wd} className="border-l border-gray-100">
            <DayColumn
              weekday={wd}
              slots={byDay(wd)}
              layout={layout}
              editable={editable}
              onSlotClick={onSlotClick}
              onEmptyClick={onEmptyClick}
            />
          </div>
        ))}
      </div>
      {editable && (
        <p className="mt-2 text-xs text-gray-400">
          Tipp: Slots per Drag &amp; Drop verschieben, Mitarbeiter aus der Liste auf einen Slot ziehen, oder einen Slot
          anklicken zum Bearbeiten. Beim Ziehen wird in 15-Minuten-Schritten gerundet. Parallele Slots werden
          nebeneinander dargestellt.
        </p>
      )}
    </div>
  );
}
