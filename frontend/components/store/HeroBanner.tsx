"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

// Split promo hero: bold copy + CTA on the left, a real high-res product photo
// on the right resting on a soft white spotlight so the white-background render
// blends onto the gradient. Each slide links to a real category or promotion.
type Slide = {
  eyebrow: string;
  title: string;
  subtitle: string;
  cta: string;
  href: string;
  gradient: string;
  image: string;
  badge?: string;
};

const SLIDES: Slide[] = [
  {
    eyebrow: "Hogar",
    title: "Todo para tu Hogar",
    subtitle: "Electrodomésticos, cocina y organización con envío a todo el Ecuador.",
    cta: "Ver Hogar",
    href: "/tienda?category=hogar",
    gradient: "linear-gradient(115deg,#0b1733 0%,#22458c 55%,#0aa2b0 100%)",
    image: "https://clickhome.ec/3263-thickbox_default/aspiradora-black-decker-1800w-3lt-bolsa-de-tela-rojo.jpg",
  },
  {
    eyebrow: "Tecnología",
    title: "Tecnología al mejor precio",
    subtitle: "Audio, cámaras y accesorios con hasta 12 meses de garantía.",
    cta: "Ver Tecnología",
    href: "/tienda?category=tecnologia",
    gradient: "linear-gradient(115deg,#170e2e 0%,#5a2a8c 55%,#c026d3 100%)",
    image: "https://clickhome.ec/497-thickbox_default/audifonos-sony-inalambrico-diadema-30mm-20.jpg",
  },
  {
    eyebrow: "Oferta del día",
    badge: "-10% HOY",
    title: "Usa el código CLICKHOME10",
    subtitle: "Descuento al finalizar tu compra · Envío gratis en pedidos estándar.",
    cta: "Comprar ahora",
    href: "/tienda?category=electromenores",
    gradient: "linear-gradient(115deg,#3a0d16 0%,#c0102f 55%,#f7a83c 100%)",
    image: "https://clickhome.ec/1048-thickbox_default/cafetera-cuisinart-expreso-acero-inoxidable.jpg",
  },
  {
    eyebrow: "Cuidado Personal",
    title: "Luce increíble cada día",
    subtitle: "Secadores, planchas y cortadoras para tu rutina diaria.",
    cta: "Explorar",
    href: "/tienda?category=cuidado-personal",
    gradient: "linear-gradient(115deg,#052018 0%,#0f766e 55%,#f6b73c 100%)",
    image: "https://clickhome.ec/1192-thickbox_default/secador-de-cabello-remington-thermcare-1900w-2-vel-3-ajustes-negro.jpg",
  },
];

export function HeroBanner() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  // Best practice: rotate on load, but stop auto-advancing once the shopper
  // takes control with the arrows or dots.
  useEffect(() => {
    if (paused) return;
    const timer = setInterval(() => setIndex((value) => (value + 1) % SLIDES.length), 5500);
    return () => clearInterval(timer);
  }, [paused]);

  const go = (next: number) => {
    setPaused(true);
    setIndex((next + SLIDES.length) % SLIDES.length);
  };

  return (
    <section className="az-hero" aria-label="Promociones" aria-roledescription="carrusel">
      {SLIDES.map((slide, position) => (
        <div
          key={slide.href}
          className={`az-hero-slide${position === index ? " active" : ""}`}
          style={{ background: slide.gradient }}
          aria-hidden={position === index ? undefined : true}
        >
          <div className="az-hero-inner">
            <div className="az-hero-copy">
              {slide.badge ? <span className="az-hero-badge">{slide.badge}</span> : <span className="az-hero-eyebrow">{slide.eyebrow}</span>}
              <h2>{slide.title}</h2>
              <p>{slide.subtitle}</p>
              <Link className="az-hero-cta" href={slide.href}>
                {slide.cta}
                <span aria-hidden="true">→</span>
              </Link>
            </div>
            <div className="az-hero-media" aria-hidden="true">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={slide.image} alt="" loading={position === 0 ? "eager" : "lazy"} />
            </div>
          </div>
        </div>
      ))}
      <button className="az-hero-arrow left" onClick={() => go(index - 1)} aria-label="Anterior">
        ‹
      </button>
      <button className="az-hero-arrow right" onClick={() => go(index + 1)} aria-label="Siguiente">
        ›
      </button>
      <div className="az-hero-dots">
        {SLIDES.map((slide, position) => (
          <button
            key={slide.href}
            className={position === index ? "active" : ""}
            onClick={() => go(position)}
            aria-label={`Ir a promoción ${position + 1}`}
            aria-current={position === index ? "true" : undefined}
          />
        ))}
      </div>
    </section>
  );
}
