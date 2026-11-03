import type { ReactNode } from "react";

type Tag = "h1" | "h2" | "h3" | "p";

export function Lines({ as: Tag = "h2", lines, className = "" }: { as?: Tag; lines: ReactNode[]; className?: string }) {
  return (
    <Tag className={`lines ${className}`} data-lines>
      {lines.map((l, i) => (
        <span className="line" key={i}>
          <span>{l}</span>
        </span>
      ))}
    </Tag>
  );
}
