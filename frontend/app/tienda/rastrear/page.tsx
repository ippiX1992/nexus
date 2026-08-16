"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export default function TrackLookupPage() {
  const router = useRouter();
  const [number, setNumber] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = number.trim();
    if (trimmed) router.push(`/tienda/pedido/${encodeURIComponent(trimmed)}`);
  }

  return (
    <div className="sf-pad">
      <Link className="sf-back" href="/tienda">
        ← Volver a la tienda
      </Link>
      <div className="sf-track-box">
        <h1>Rastrea tu pedido</h1>
        <p className="sf-muted">Ingresa tu número de pedido (por ejemplo, CH-20260816-XXXXXX).</p>
        <form className="sf-track-form" onSubmit={submit}>
          <input value={number} onChange={(event) => setNumber(event.target.value)} placeholder="Número de pedido" aria-label="Número de pedido" />
          <button type="submit">Ver seguimiento</button>
        </form>
      </div>
    </div>
  );
}
