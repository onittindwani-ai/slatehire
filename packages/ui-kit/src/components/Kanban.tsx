"use client";
import { DndContext, DragOverlay, pointerWithin, rectIntersection, type CollisionDetection, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { useState, type KeyboardEvent, type ReactNode } from "react";

/** The column under the pointer wins, and the card's own box is the fallback (keyboard drags have no pointer). */
const collide: CollisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

export interface KanbanColumn {
  id: string;
  title: string;
}

export interface KanbanItem {
  id: string;
  columnId: string;
}

export interface KanbanProps<T extends KanbanItem> {
  columns: KanbanColumn[];
  items: T[];
  renderCard: (item: T) => ReactNode;
  onMove: (itemId: string, toColumnId: string, fromColumnId: string) => void;
  /** Opens a card. Adds an Open button inside every card (shown on hover and when focus is inside) and makes Enter on the focused card call it. */
  onOpen?: (item: T) => void;
  /** Accessible name of each card. Defaults to "Card" plus the id. */
  cardLabel?: (item: T) => string;
  label?: string;
}

/**
 * The card is a labelled group, not a button, so it can hold real buttons and links without nesting interactive roles.
 * Mouse and touch drag from anywhere on the card (a 5 px move starts a drag, so a click on a button inside still works).
 * Keyboard: focus the card, Space lifts it, arrows move it, Space or Enter drops it, Escape cancels. Enter on a focused card opens it.
 */
function Card<T extends KanbanItem>({ item, render, onOpen, label }: { item: T; render: (i: T) => ReactNode; onOpen?: (i: T) => void; label: string }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: item.id,
    attributes: { role: "group", roleDescription: "draggable card", tabIndex: 0 },
  });
  function key(e: KeyboardEvent<HTMLDivElement>) {
    if (onOpen && e.key === "Enter" && e.target === e.currentTarget && !isDragging) {
      e.preventDefault();
      onOpen(item);
      return;
    }
    listeners?.onKeyDown?.(e);
  }
  return (
    <div ref={setNodeRef} className="sx-kanban__card" data-dragging={isDragging} aria-label={label} {...attributes} {...listeners} onKeyDown={key}>
      {render(item)}
      {onOpen ? (
        <button type="button" className="sx-kanban__open" aria-label={`Open ${label}`} onPointerDown={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()} onClick={() => onOpen(item)}>
          Open
        </button>
      ) : null}
    </div>
  );
}

function Column({ column, count, children }: { column: KanbanColumn; count: number; children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  return (
    <section ref={setNodeRef} className="sx-kanban__col" data-over={isOver} aria-label={column.title}>
      <div className="sx-kanban__head"><span>{column.title}</span><span className="sx-quiet sx-num">{count}</span></div>
      {children}
    </section>
  );
}

/** Drag cards between columns with mouse, touch or keyboard (space to lift, arrows, space to drop). Cards may hold buttons and links. The card lifts into an overlay and the old spot dims as the gap. */
export function Kanban<T extends KanbanItem>({ columns, items, renderCard, onMove, onOpen, cardLabel = (i) => `Card ${i.id}`, label = "Board" }: KanbanProps<T>) {
  const [dragId, setDragId] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }), useSensor(KeyboardSensor, { keyboardCodes: { start: ["Space"], cancel: ["Escape"], end: ["Space", "Enter"] } }));
  const dragged = items.find((i) => i.id === dragId);
  function end(e: DragEndEvent) {
    setDragId(null);
    const item = items.find((i) => i.id === String(e.active.id));
    const to = e.over ? String(e.over.id) : null;
    if (item && to && to !== item.columnId) onMove(item.id, to, item.columnId);
  }
  return (
    <DndContext sensors={sensors} collisionDetection={collide} onDragStart={(e: DragStartEvent) => setDragId(String(e.active.id))} onDragEnd={end} onDragCancel={() => setDragId(null)}>
      <div className="sx-kanban" role="group" aria-label={label}>
        {columns.map((c) => {
          const inCol = items.filter((i) => i.columnId === c.id);
          return (
            <Column key={c.id} column={c} count={inCol.length}>
              {inCol.map((i) => <Card key={i.id} item={i} render={renderCard} onOpen={onOpen} label={cardLabel(i)} />)}
            </Column>
          );
        })}
      </div>
      <DragOverlay dropAnimation={{ duration: 240, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }}>
        {dragged ? <div className="sx-kanban__card sx-kanban__overlay" aria-hidden="true" inert>{renderCard(dragged)}</div> : null}
      </DragOverlay>
    </DndContext>
  );
}
