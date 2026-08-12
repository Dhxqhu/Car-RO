import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-[100px] w-full rounded-xl border border-border bg-surface px-3 py-2 text-base text-fg placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35",
        className,
      )}
      {...props}
    />
  );
}
