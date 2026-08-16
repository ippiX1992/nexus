"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

// Rotating promo banner (Amazon-style hero). Image-free: uses gradients + copy,
// each slide linking to a real category in the catalog.
const SLIDES = [
  { title: "Todo para tu Hogar", subtitle: "Electrodomésticos, cocina y más, con envío a todo el Ecuador", cta: "Ver Hogar", href: "/tienda?category=hogar", gradient: "linear-gradient(120deg,#0f1c3f,#2b4d8e 60%,#00a8b5)" },
  { title: "Tecnología al mejor precio", subtitle: "Audio, cámaras y accesorios que amarás", cta: "Ver Tecnología", href: "/tienda?category=tecnologia", gradient: "linear-gradient(120deg,#1a1030,#5b2b8e 55%,#c026d3)" },
  { title: "Cuidado Personal", subtitle: "Cortadoras, planchas y cuidado del cabello", cta: "Explorar", href: "/tienda?category=cuidado-personal", gradient: "linear-gradient(120deg,#07271f,#0f766e 55%,#f59e0b)" },
];

export function HeroBanner() {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setIndex((value) => (value + 1) % SLIDES.length), 5500);
    return () => clearInterval(timer);
  }, []);

  return (
    <section className="az-hero" aria-label="Promociones">
      {SLIDES.map((slide, position) => (
        <div key={slide.href} className={`az-hero-slide${position === index ? " active" : ""}`} style={{ background: slide.gradient }}>
          <div className="az-hero-copy">
            <h2>{slide.title}</h2>
            <p>{slide.subtitle}</p>
            <Link className="az-hero-cta" href={slide.href}>
              {slide.cta}
            </Link>
          </div>
        </div>
      ))}
      <div className="az-hero-dots">
        {SLIDES.map((slide, position) => (
          <button
            key={slide.href}
            className={position === index ? "active" : ""}
            onClick={() => setIndex(position)}
            aria-label={`Ir a promoción ${position + 1}`}
          />
        ))}
      </div>
    </section>
  );
}
