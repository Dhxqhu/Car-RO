import { cn } from "@/lib/utils";

/** Marks unfinished OBD workspace surfaces during the framework phase. */
export function ScaffoldNote({
  className,
  children = "Framework scaffold — live bus I/O lands when we wire ElmSession into the engine.",
}: {
  className?: string;
  children?: string;
}) {
  return (
    <p
      className={cn(
        "rounded-lg border border-dashed border-border bg-surface/60 px-3 py-2 text-sm text-muted",
        className,
      )}
    >
      {children}
    </p>
  );
}
