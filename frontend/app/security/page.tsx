"use client";
import { type FormEvent, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Button } from "@/components/admin/Button";
import { Field, FormSection } from "@/components/admin/FormSection";
import { api } from "@/lib/api";

const inputCls = "w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-text focus:border-brand focus:outline-none";

export default function Page() {
  const [uri, setUri] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [error, setError] = useState("");

  async function setup() {
    try {
      setUri((await api("/auth/2fa/setup", { method: "POST" })).provisioning_uri);
    } catch (x) {
      setError((x as Error).message);
    }
  }
  async function enable(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      setCodes((await api("/auth/2fa/enable", { method: "POST", body: JSON.stringify({ code: f.get("code") }) })).recovery_codes);
    } catch (z) {
      setError((z as Error).message);
    }
  }

  return (
    <AdminShell title="Seguridad" description="Protege tu cuenta con verificación en dos pasos (2FA).">
      <div className="max-w-2xl">
        <FormSection title="Verificación en dos pasos" description="Usa una app autenticadora (Google Authenticator, Authy…).">
          {!uri ? (
            <Button variant="primary" onClick={setup}>
              Configurar app autenticadora
            </Button>
          ) : (
            <>
              <p className="rounded-lg border border-line bg-bg p-3 font-mono text-xs break-all text-muted">{uri}</p>
              <form onSubmit={enable} className="grid max-w-xs gap-2">
                <Field label="Código de confirmación">
                  <input name="code" required className={inputCls} />
                </Field>
                <Button variant="primary" type="submit">
                  Activar 2FA
                </Button>
              </form>
            </>
          )}
          {codes.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
              <strong className="text-sm text-amber-200">Guarda estos códigos ahora; se muestran una sola vez</strong>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {codes.map((c) => (
                  <span key={c} className="rounded-md bg-black/20 px-2 py-0.5 font-mono text-xs text-amber-100">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}
        </FormSection>
      </div>
      {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    </AdminShell>
  );
}
