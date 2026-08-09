import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";

export function ScanLivePage() {
  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Multi-PID live stream (table + optional sparkline) will reuse obdscan’s PID catalog and
        custom profiles.
      </ScaffoldNote>
      <div className="flex flex-wrap gap-2">
        <Button disabled>Start stream</Button>
        <Button variant="ghost" disabled>
          Configure PIDs
        </Button>
      </div>
      <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
        Live gauges placeholder.
      </div>
    </div>
  );
}
