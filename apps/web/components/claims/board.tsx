"use client";

import type { Status } from "@fanilo/shared";
import { STATUSES } from "@fanilo/shared";
import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import Link from "next/link";
import { useState } from "react";
import { IconDotsThreeVertical } from "@/lib/icons";
import { formatDuration } from "@/lib/time";
import { Avatar, type ClaimView, STATUS_ICON, VerdictBadge } from "@/components/claims/verdict";
import { claimSteps, StepLine } from "@/components/flow/step-line";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

// A drop that ends over the card it started from must not also count as a click on it.
let lastDragEnd = 0;

type Props = {
  ws: string;
  claims: ClaimView[];
  now: Date;
  names: Map<string, string>;
  canMove: (claim: ClaimView) => boolean;
  onMove: (claim: ClaimView, status: Status) => void;
};

function CardBody({ claim, now, names }: { claim: ClaimView; now: Date; names: Map<string, string> }) {
  const assignee = claim.assigneeId ? names.get(claim.assigneeId) : null;
  return (
    <>
      <div className="flex items-baseline justify-between gap-2 pr-7 text-sm">
        <span className="text-sm font-medium tabular">{claim.ref}</span>
        {claim.firstSeen && (
          <span className="font-display tracking-wide text-muted-foreground tabular">
            {formatDuration(now.getTime() - claim.firstSeen.getTime())}
          </span>
        )}
      </div>
      <p className="mt-1 line-clamp-3 font-bold text-pretty">{claim.item.title}</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <VerdictBadge claim={claim} compact className="min-w-0 truncate" />
        <span className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground tabular">
          {claim.sources > 0 && <span>{t.claims.sources(claim.sources)}</span>}
          {assignee && <Avatar name={assignee} />}
        </span>
      </div>
      <StepLine variant="mini" states={claimSteps(claim)} className="mt-3" />
    </>
  );
}

function Card({
  ws,
  claim,
  now,
  names,
  movable,
  onMove,
}: {
  ws: string;
  claim: ClaimView;
  now: Date;
  names: Map<string, string>;
  movable: boolean;
  onMove: (status: Status) => void;
}) {
  const id = claim.item.id;
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id, disabled: !movable });
  return (
    <li
      ref={setNodeRef}
      {...(movable ? listeners : {})}
      {...(movable ? attributes : {})}
      aria-roledescription={movable ? t.claims.board.movable : undefined}
      aria-describedby={movable ? "board-hint" : undefined}
      title={movable ? undefined : t.claims.board.cannotMove}
      className={cn(
        "group/card relative rounded-md border border-border bg-card p-3 outline-none",
        "transition-[opacity,box-shadow] duration-150 focus-visible:ring-2 focus-visible:ring-ring",
        movable && "cursor-grab touch-none active:cursor-grabbing",
        isDragging && "opacity-35",
      )}
    >
      <Link
        href={`/w/${ws}/affirmations/${id}`}
        // The whole card opens the claim; dragging still works because dnd-kit waits for movement.
        className="absolute inset-0 rounded-md focus-visible:outline-none"
        aria-label={`${claim.ref} — ${claim.item.title}`}
        draggable={false}
        onClick={(e) => {
          if (Date.now() - lastDragEnd < 300) e.preventDefault();
        }}
      />
      <div className="pointer-events-none relative">
        <CardBody claim={claim} now={now} names={names} />
      </div>
      {movable && (
        <DropdownMenu>
          <DropdownMenuTrigger
            onPointerDown={(e) => e.stopPropagation()}
            className="absolute top-2 right-1.5 grid size-7 place-items-center rounded-sm text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`${t.claims.board.moveTo} ${claim.ref}`}
          >
            <IconDotsThreeVertical className="size-4" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel>{t.claims.board.moveTo}</DropdownMenuLabel>
            {STATUSES.filter((s) => s !== claim.status).map((s) => {
              const Icon = STATUS_ICON[s];
              return (
                <DropdownMenuItem key={s} onSelect={() => onMove(s)}>
                  <Icon className="size-4" aria-hidden />
                  {t.status[s]}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </li>
  );
}

function Column({ status, count, children }: { status: Status; count: number; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const Icon = STATUS_ICON[status];
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={`col-${status}`}
      className={cn(
        "flex w-[min(19rem,82vw)] shrink-0 snap-start flex-col rounded-lg border border-transparent bg-muted/70 transition-colors duration-150 lg:w-auto",
        isOver && "border-foreground/30 bg-accent",
      )}
    >
      <h2 id={`col-${status}`} className="flex items-center gap-2 px-3 pt-3 pb-2 text-sm font-semibold">
        <Icon className="size-4" aria-hidden />
        {t.status[status]}
        <span className="ml-auto font-display text-base font-medium text-muted-foreground tabular">{count}</span>
      </h2>
      <ol className="flex min-h-24 flex-1 flex-col gap-2 px-2 pb-2">
        {count === 0 ? (
          <li className="grid flex-1 place-items-center rounded-md border border-dashed border-border px-3 py-6 text-sm text-muted-foreground">
            {isOver ? t.claims.board.dropHere : t.claims.board.empty}
          </li>
        ) : (
          children
        )}
      </ol>
    </section>
  );
}

export function Board({ ws, claims, now, names, canMove, onMove }: Props) {
  const [active, setActive] = useState<ClaimView | null>(null);
  const sensors = useSensors(
    // A small distance keeps clicks opening the claim instead of starting a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 220, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );

  const byStatus = new Map<Status, ClaimView[]>(STATUSES.map((s) => [s, []]));
  for (const c of claims) byStatus.get(c.status)?.push(c);
  for (const list of byStatus.values()) {
    list.sort((a, b) => (b.firstSeen?.getTime() ?? 0) - (a.firstSeen?.getTime() ?? 0));
  }

  function onDragStart(e: DragStartEvent) {
    setActive(claims.find((c) => c.item.id === e.active.id) ?? null);
  }

  function onDragEnd(e: DragEndEvent) {
    setActive(null);
    lastDragEnd = Date.now();
    const claim = claims.find((c) => c.item.id === e.active.id);
    const to = e.over?.id as Status | undefined;
    if (claim && to && to !== claim.status) onMove(claim, to);
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActive(null)}
      accessibility={{
        screenReaderInstructions: { draggable: t.claims.board.dragHint },
      }}
    >
      <p id="board-hint" className="sr-only">
        {t.claims.board.dragHint}
      </p>
      <div
        aria-label={t.claims.board.label}
        className="flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:thin] lg:grid lg:grid-cols-4 lg:overflow-visible lg:px-0"
      >
        {STATUSES.map((s) => {
          const list = byStatus.get(s)!;
          return (
            <Column key={s} status={s} count={list.length}>
              {list.map((c) => (
                <Card
                  key={c.item.id}
                  ws={ws}
                  claim={c}
                  now={now}
                  names={names}
                  movable={canMove(c)}
                  onMove={(status) => onMove(c, status)}
                />
              ))}
            </Column>
          );
        })}
      </div>
      <DragOverlay dropAnimation={{ duration: 180, easing: "cubic-bezier(0.16, 1, 0.3, 1)" }}>
        {active && (
          <div className="w-[min(19rem,82vw)] rotate-[1.5deg] cursor-grabbing rounded-md border border-border bg-card p-3 shadow-[var(--shadow-float)] lg:w-72">
            <CardBody claim={active} now={now} names={names} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
