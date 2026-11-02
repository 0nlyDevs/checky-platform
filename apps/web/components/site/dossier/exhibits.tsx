"use client";

import { useRef, useState } from "react";
import { CardSheet, PostSheet, QuotesSheet } from "@/components/site/fragments";
import { t } from "@/lib/i18n/fr";

const SHEETS = { card: CardSheet, post: PostSheet, quotes: QuotesSheet } as const;
type Id = keyof typeof SHEETS;

/** What leaves the file at 7: folder tabs change the exhibit on the tray, as the product makes it. */
export function Exhibits() {
  const x = t.site.exhibits;
  const [current, setCurrent] = useState<Id>("card");
  const [swap, setSwap] = useState(false);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const item = x.items.find((i) => i.id === current) ?? x.items[0];
  const Sheet = SHEETS[current];

  function pick(id: Id) {
    if (id === current) return;
    setSwap(true);
    setTimeout(() => {
      setCurrent(id);
      setSwap(false);
    }, 200);
  }
  function keys(e: React.KeyboardEvent, i: number) {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = (i + d + x.items.length) % x.items.length;
    tabs.current[n]?.focus();
    pick(x.items[n].id as Id);
  }

  return (
    <>
      <div className="dossier-tabs" role="tablist" aria-label={x.label}>
        {x.items.map((it, i) => (
          <button
            key={it.id}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${it.id}`}
            aria-selected={current === it.id}
            aria-controls="exhibit"
            tabIndex={current === it.id ? 0 : -1}
            onClick={() => pick(it.id as Id)}
            onKeyDown={(e) => keys(e, i)}
          >
            {it.name}
          </button>
        ))}
      </div>
      <div className="dossier-tray" role="tabpanel" id="exhibit" aria-labelledby={`tab-${current}`}>
        <div>
          <h3>{item.name}</h3>
          <p>{item.text}</p>
        </div>
        <div className="dossier-exhibit" data-swap={swap}>
          <Sheet />
        </div>
      </div>
    </>
  );
}
