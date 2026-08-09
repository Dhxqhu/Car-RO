import { ScaffoldNote } from "@/components/ScaffoldNote";
import { Button } from "@/components/ui/button";

export function ScanCodesPage() {
  return (
    <div className="space-y-4">
      <ScaffoldNote>
        Codes page will call <code className="text-fg">GET /obd/codes</code> and offer clear + save
        into Documents/Saved Codes — same path Car-RO already pulls from.
      </ScaffoldNote>
      <div className="flex flex-wrap gap-2">
        <Button disabled>Read codes</Button>
        <Button variant="ghost" disabled>
          Clear codes
        </Button>
        <Button variant="ghost" disabled>
          Save report
        </Button>
      </div>
      <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted">
        No live DTC list yet.
      </div>
    </div>
  );
}
