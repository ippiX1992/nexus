import {randomUUID} from "node:crypto";
import {expect,test} from "@playwright/test";

const apiURL=process.env.E2E_API_URL??"http://127.0.0.1:8000/api/v1";
const password=process.env.E2E_PASSWORD??"E2E-only-password-99";

test("registro, contexto, seguridad, sesiones, autorización y logout",async({page})=>{
  const email=`playwright-${Date.now()}-${randomUUID()}@example.com`;
  const company=`Playwright Tenant ${Date.now()}`;

  await page.goto("/register");
  await expect(page.getByRole("heading",{name:"Crea tu empresa"})).toBeVisible();
  await page.getByLabel("Nombre",{exact:true}).fill("Playwright User");
  await page.getByLabel("Correo",{exact:true}).fill(email);
  await page.getByLabel("Contraseña",{exact:true}).fill(password);
  await page.getByLabel("Empresa",{exact:true}).fill(company);
  await Promise.all([
    page.waitForURL("**/"),
    page.getByRole("button",{name:"Crear espacio"}).click(),
  ]);

  await page.getByLabel("Correo",{exact:true}).fill(email);
  await page.getByLabel("Contraseña",{exact:true}).fill(password);
  await Promise.all([
    page.waitForURL("**/select-tenant"),
    page.getByRole("button",{name:"Iniciar sesión"}).click(),
  ]);

  await expect(page.getByRole("heading",{name:"Selecciona una empresa"})).toBeVisible();
  await expect(page.getByText(company,{exact:true})).toBeVisible();

  const forbiddenStatus=await page.evaluate(async({endpoint,tenantId})=>{
    const token=sessionStorage.getItem("access_token");
    const response=await fetch(`${endpoint}/auth/select-tenant`,{
      method:"POST",
      headers:{"Authorization":`Bearer ${token}`,"Content-Type":"application/json"},
      body:JSON.stringify({tenant_id:tenantId}),
      credentials:"include",
    });
    return response.status;
  },{endpoint:apiURL,tenantId:"00000000-0000-4000-8000-000000000001"});
  expect(forbiddenStatus).toBe(403);

  await Promise.all([
    page.waitForURL("**/dashboard"),
    page.getByRole("button",{name:"Entrar"}).click(),
  ]);
  await expect(page.getByRole("heading",{name:"Centro de identidad"})).toBeVisible();
  await expect(page.getByText("owner",{exact:true})).toBeVisible();

  await page.getByRole("link",{name:"Platform"}).click();
  await expect(page.getByRole("heading",{name:"Stores"})).toBeVisible();
  await page.getByRole("link",{name:"Crear store"}).click();
  await page.getByLabel("Código").fill("main");
  await page.getByLabel("Nombre").fill("Main Store");
  await page.getByLabel("Slug").fill("main-store");
  await page.getByRole("button",{name:"Crear store"}).click();
  await page.waitForURL("**/platform/stores/**");
  await expect(page.getByText("draft",{exact:true})).toBeVisible();

  await page.getByRole("link",{name:"Sites",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Sites",exact:true})).toBeVisible();
  await page.getByLabel("Código").fill("web");
  await page.getByLabel("Nombre").fill("Website");
  await page.getByLabel("Slug").fill("website");
  await page.getByRole("button",{name:"Crear"}).click();
  await expect(page.getByText(/web · draft/)).toBeVisible();

  await page.getByRole("link",{name:"Channels",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Sales Channels",exact:true})).toBeVisible();
  await page.getByLabel("Código").fill("web");
  await page.getByLabel("Nombre").fill("Web Channel");
  await page.getByRole("button",{name:"Crear"}).click();
  await expect(page.getByText(/web · draft/)).toBeVisible();

  await page.getByRole("link",{name:"Environments",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Environments",exact:true})).toBeVisible();
  await page.getByLabel("Código").fill("preview");
  await page.getByLabel("Nombre").fill("Preview");
  await page.getByRole("button",{name:"Crear"}).click();
  await expect(page.getByText(/preview · active/)).toBeVisible();

  await page.getByRole("link",{name:"Markets",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Markets",exact:true})).toBeVisible();
  await page.getByLabel("Código").fill("ecuador");
  await page.getByLabel("Nombre").fill("Ecuador");
  await page.getByRole("button",{name:"Crear"}).click();
  await expect(page.getByText(/ecuador · draft/)).toBeVisible();

  await page.getByRole("link",{name:"Uso y cuotas",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Uso y cuotas",exact:true})).toBeVisible();
  await expect(page.getByText("stores.max",{exact:true})).toBeVisible();

  await page.getByRole("link",{name:"Operations"}).click();
  await expect(page.getByRole("heading",{name:"Operations"})).toBeVisible();

  await page.getByRole("link",{name:"Seguridad"}).click();
  await expect(page.getByRole("heading",{name:"Seguridad"})).toBeVisible();
  await page.getByRole("link",{name:"Sesiones"}).click();
  await expect(page.getByRole("heading",{name:"Sesiones activas"})).toBeVisible();
  await expect(page.getByText("Esta sesión",{exact:true})).toBeVisible();

  const logoutResponse=page.waitForResponse(response=>response.url().endsWith("/auth/logout")&&response.request().method()==="POST");
  await page.getByRole("button",{name:"Cerrar sesión"}).click();
  expect((await logoutResponse).status()).toBe(204);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading",{name:"Bienvenido a Nexus"})).toBeVisible();
});
