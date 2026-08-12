import { useEffect, useRef, useState } from "react";
import { Camera, SwitchCamera, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CameraSheet({
  onCapture,
  onClose,
}: {
  onCapture: (file: File) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState("");
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function start() {
      setError("");
      setReady(false);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This phone cannot open the camera here. Use Library instead.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: facing },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play().catch(() => undefined);
        }
        setReady(true);
      } catch (e) {
        const name = e instanceof DOMException ? e.name : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
          setError("Camera permission was denied. Allow camera for Car-RO in iPhone Settings → Car-RO.");
        } else if (location.protocol !== "https:" && location.hostname !== "localhost") {
          setError("Camera needs HTTPS. Open the Tailscale https://…:8443 app, then try again.");
        } else {
          setError(e instanceof Error ? e.message : "Could not open camera");
        }
      }
    }
    void start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [facing]);

  function shoot() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        onCapture(new File([blob], `camera-${stamp}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.85,
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black">
      <div className="flex shrink-0 items-center justify-between px-3 py-2 pt-[max(0.5rem,env(safe-area-inset-top))] text-white">
        <button type="button" className="flex h-10 w-10 items-center justify-center" onClick={onClose} aria-label="Close camera">
          <X size={22} />
        </button>
        <p className="text-sm font-medium">Camera</p>
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center"
          onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
          aria-label="Flip camera"
        >
          <SwitchCamera size={20} />
        </button>
      </div>
      <div className="relative min-h-0 flex-1">
        <video
          ref={videoRef}
          className="h-full w-full object-cover"
          playsInline
          muted
          autoPlay
        />
        {error ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80 p-6 text-center text-sm text-white">
            {error}
          </div>
        ) : null}
      </div>
      <div className="flex shrink-0 justify-center pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-4">
        <Button
          type="button"
          disabled={!ready || !!error}
          className="h-16 w-16 rounded-full bg-white text-black disabled:opacity-40"
          onClick={shoot}
          aria-label="Take photo"
        >
          <Camera size={26} />
        </Button>
      </div>
    </div>
  );
}
