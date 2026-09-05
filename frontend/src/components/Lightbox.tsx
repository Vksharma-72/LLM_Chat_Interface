import { useEffect } from "react";

interface LightboxProps {
  images: { id: string; url: string; filename: string }[];
  index: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

export default function Lightbox({ images, index, onClose, onNavigate }: LightboxProps) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      } else if (event.key === "ArrowRight" && index < images.length - 1) {
        onNavigate(index + 1);
      } else if (event.key === "ArrowLeft" && index > 0) {
        onNavigate(index - 1);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [images.length, index, onClose, onNavigate]);

  const current = images[index];
  if (!current) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90 px-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Image viewer: ${current.filename}`}
    >
      <img
        src={current.url}
        alt={current.filename}
        className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
        onClick={(event) => event.stopPropagation()}
      />
      <button
        type="button"
        onClick={onClose}
        aria-label="Close image viewer"
        className="absolute right-4 top-4 rounded-md bg-white/10 px-3 py-1.5 text-white hover:bg-white/20"
      >
        ✕
      </button>
      {images.length > 1 && (
        <>
          {index > 0 && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onNavigate(index - 1);
              }}
              aria-label="Previous image"
              className="absolute left-4 rounded-full bg-white/10 px-3 py-2 text-white hover:bg-white/20"
            >
              ←
            </button>
          )}
          {index < images.length - 1 && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onNavigate(index + 1);
              }}
              aria-label="Next image"
              className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 px-3 py-2 text-white hover:bg-white/20"
            >
              →
            </button>
          )}
          <span className="absolute bottom-4 text-sm text-white/70">
            {index + 1} / {images.length}
          </span>
        </>
      )}
    </div>
  );
}
