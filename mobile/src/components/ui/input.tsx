import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({
  className,
  autoComplete = "off",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-11 w-full rounded-xl border border-border bg-surface px-3 text-base text-fg placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35",
        className,
      )}
      autoComplete={autoComplete}
      {...props}
    />
  );
}
