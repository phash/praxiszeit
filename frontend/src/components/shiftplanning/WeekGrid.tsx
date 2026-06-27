import { useDraggable, useDroppable } from '@dnd-kit/core';
import { AlertTriangle, Plus, Users } from 'lucide-react';
import { HOUR_PX, computeWeekLayout, type SlotBox, type WeekLayout } from './weekGridUtils';
import { WEEKDAY_LABELS_LONG, type ShiftSlot } from '../../api/shiftPlanning';

interface WeekGridProps {
  slots: ShiftSlot[];
  editable?: boolean;
  onSlotClick?: (slot: ShiftSlot) => void;
  onEmptyClick?: (weekday: number) => void;
  // #321: when set, render only this one weekday full-width (Tagesansicht).
  singleDay?: number;
}

function SlotBody({ slot }: { slot: ShiftSlot }) {
  const names = slot.assignments.map((a) => a.user_name).join(', ');
  return (
    <>
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold truncate">{slot.workstation_name}</span>
        {slot.understaffed && <AlertTriangle size={12} className="shrink-0" aria-label="Unterbesetzt" />}
      </div>
      <div className="opacity-90">
        {slot.start_time}–{slot.end_time}
      </div>
      <div className="flex items-center gap-1 opacity-90 truncate">
        <Users size={11} className="shrink-0" />
        <span className="truncate">{names || (slot.min_staff > 0 ? `0/${slot.min_staff}` : '—')}</span>
      </div>
    </>
  );
}

function blockStyle(slot: ShiftSlot, box: SlotBox): React.CSSProperties {
  const color = slot.color || '#2563eb';
  // left/right 2px gutter inside the lane so adjacent lanes stay visually separated
  return {
    top: box.top,
    height: box.height,
    left: `calc(${box.leftPct}% + 2px)`,
    width: `calc(${box.widthPct}% - 4px)`,
    backgroundColor: `${color}1a`, // ~10% alpha
    borderLeft: `3px solid ${color}`,
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
      className="absolute rounded-md p-1 text-[11px] leading-tight text-gray-800 cursor-grab overflow-hidden touch-none"
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
      className="absolute rounded-md p-1 text-[11px] leading-tight text-gray-800 overflow-hidden"
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
      className={`relative overflow-hidden ${isOver && editable ? 'bg-primary/5' : ''}`}
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

export default function WeekGrid({ slots, editable = false, onSlotClick, onEmptyClick, singleDay }: WeekGridProps) {
  const layout = computeWeekLayout(slots);
  const byDay = (wd: number) =>
    slots.filter((s) => s.weekday === wd).sort((a, b) => a.start_time.localeCompare(b.start_time));

  // #321: Tagesansicht renders just one weekday; week view all seven.
  const days = singleDay !== undefined ? [singleDay] : [0, 1, 2, 3, 4, 5, 6];

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
