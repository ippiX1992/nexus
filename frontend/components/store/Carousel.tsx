"use client";
import { useRef, type ReactNode } from "react";

// Horizontal product carousel with prev/next arrows (scrolls the track).
export function Carousel({ children }: { children: ReactNode }) {
  const track = useRef<HTMLDivElement>(null);
  const scroll = (direction: number) => track.current?.scrollBy({ left: direction * 620, behavior: "smooth" });
  return (
    <div className="sf-carousel">
      <button className="sf-carousel-arrow left" onClick={() => scroll(-1)} aria-label="Anterior">
        ‹
      </button>
      <div className="sf-carousel-track" ref={track}>
        {children}
      </div>
      <button className="sf-carousel-arrow right" onClick={() => scroll(1)} aria-label="Siguiente">
        ›
      </button>
    </div>
  );
}
