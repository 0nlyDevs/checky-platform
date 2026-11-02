import { IconImage, IconMagnifyingGlass, IconSparkle } from "@/lib/icons";
import { cn } from "@/lib/utils";

export type TraceState = "none" | "inconclusive" | "detected";

const LOOK: Record<TraceState, { box: string; Icon: typeof IconImage }> = {
  none: { box: "border border-rule bg-image-1", Icon: IconImage },
  inconclusive: { box: "border-2 border-dashed border-image-strong bg-image-2", Icon: IconMagnifyingGlass },
  detected: { box: "border-2 border-image-strong bg-image-3", Icon: IconSparkle },
};

/**
 * What the examination of an image (or a video file) found about AI generation. A teal scale, never
 * a verdict colour: an AI trace is a clue for the journalist, not a conclusion. Text stays foreground.
 */
export function ImageTrace({ state, children, className }: { state: TraceState; children: React.ReactNode; className?: string }) {
  const { box, Icon } = LOOK[state];
  return (
    <p className={cn("flex items-start gap-2 rounded-md px-3 py-2 text-foreground", box, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span className="min-w-0">{children}</span>
    </p>
  );
}
