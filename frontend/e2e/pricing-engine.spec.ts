import {randomUUID} from "node:crypto";
import {expect,test} from "@playwright/test";

const apiURL=process.env.E2E_API_URL??"http://127.0.0.1:8000/api/v1";
const password=process.env.E2E_PASSWORD??"E2E-only-password-99";

test("Price Lists, variant prices, Channel assignment, override precedence, and history",async({page})=>{
  const marker=`${Date.now()}-${randomUUID().slice(0,8)}`;
  const email=`pricing-owner-${marker}@example.com`;
  const company=`Pricing Tenant ${marker}`;

  await page.goto("/register");
  await page.getByLabel("Nombre",{exact:true}).fill("Pricing Owner");
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
  await expect(page.getByText(company,{exact:true})).toBeVisible();
  await Promise.all([
    page.waitForURL("**/dashboard"),
    page.getByRole("button",{name:"Entrar"}).click(),
  ]);

  // Create Store + Channel via Platform, and a Product (default Variant) via
  // Catalog directly through the API -- the UI flows for both are already
  // covered by module-1.spec.ts and catalog-foundation.spec.ts, so this test
  // only drives the UI for what M4.0 actually adds.
  const seed=await page.evaluate(async({endpoint})=>{
    function headers(token:string){
      const csrf=document.cookie.split("; ").find(value=>value.startsWith("csrf_token="))?.split("=")[1];
      return {"Content-Type":"application/json","Authorization":`Bearer ${token}`,...(csrf?{"X-CSRF-Token":decodeURIComponent(csrf)}:{})};
    }
    const token=sessionStorage.getItem("access_token")!;
    async function call(path:string,init:RequestInit={}){return fetch(`${endpoint}${path}`,{...init,credentials:"include"})}
    const store=await (await call("/stores",{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({code:"pricing-store",name:"Pricing Store",slug:"pricing-store",default_locale:"es-EC",default_currency:"USD",timezone:"America/Guayaquil"})})).json();
    await call(`/stores/${store.id}/activate`,{method:"POST",headers:headers(token)});
    const channel=await (await call(`/stores/${store.id}/channels`,{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({code:"web",name:"Web",channel_type:"web"})})).json();
    const productType=await (await call("/catalog/product-types",{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({code:"pricing-type",name:"Pricing Type"})})).json();
    const productResponse=await call("/catalog/products",{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({product_type_id:productType.id,code:"pricing-product",sku:"PRC-E2E-1",translation:{locale:"es-EC",name:"Pricing Product",short_description:"S",long_description:"L",slug:"pricing-product"}})});
    const detail=await productResponse.json();
    return {storeId:store.id,channelId:channel.id,variantId:detail.variants[0].id};
  },{endpoint:apiURL});

  // The Sidebar's group labels ("Commerce", "Catalog", ...) are plain text,
  // not links -- every item is always visible, no group needs to be
  // expanded first (see components/admin/Sidebar.tsx).
  await page.getByRole("link",{name:"Price Lists",exact:true}).click();
  const listForm=page.locator("form").filter({hasText:"Crear Price List"});
  await listForm.getByLabel("Código").fill(`retail-${marker}`);
  await listForm.getByLabel("Nombre").fill(`Retail ${marker}`);
  await listForm.getByLabel("Moneda (ISO 4217)").fill("USD");
  await listForm.getByRole("button",{name:"Crear Price List"}).click();
  const listRow=page.locator(".row").filter({hasText:`Retail ${marker}`});
  await expect(listRow).toBeVisible();

  await listRow.getByRole("link",{name:"Ver precios"}).click();
  await page.waitForURL("**/commerce/price-lists/**");
  const entryForm=page.locator("form").filter({hasText:"Definir precio de un Variant"});
  await entryForm.locator('input[name="variant_id"]').fill(seed.variantId);
  await entryForm.locator('input[name="unit_amount"]').fill("80.00");
  await entryForm.locator('input[name="compare_at_amount"]').fill("99.00");
  await entryForm.getByRole("button",{name:"Guardar precio"}).click();
  await expect(page.getByText(seed.variantId)).toBeVisible();
  await expect(page.getByText(/Base 80\.0000/)).toBeVisible();

  const assignForm=page.locator("form").filter({hasText:"Asignar esta Price List a un scope"});
  await assignForm.locator('select[name="store_id"]').selectOption(seed.storeId);
  await assignForm.locator('select[name="scope_type"]').selectOption("channel");
  await assignForm.locator('select[name="scope_id"]').selectOption(seed.channelId);
  await assignForm.locator('input[name="priority"]').fill("5");
  await assignForm.getByRole("button",{name:"Crear asignación"}).click();
  await expect(page.getByText("channel").first()).toBeVisible();

  const resolvedByAssignment=await page.evaluate(async({endpoint,variantId,channelId})=>{
    const token=sessionStorage.getItem("access_token")!;
    const response=await fetch(`${endpoint}/pricing/resolve?variant_id=${variantId}&channel_id=${channelId}`,{headers:{"Authorization":`Bearer ${token}`},credentials:"include"});
    return response.json();
  },{endpoint:apiURL,variantId:seed.variantId,channelId:seed.channelId});
  expect(resolvedByAssignment.source).toBe("assignment");
  expect(resolvedByAssignment.unit_amount).toBe("80.0000");

  await page.getByRole("link",{name:"Reglas de precio",exact:true}).click();
  const overrideForm=page.locator("form").filter({hasText:"Crear override"});
  await overrideForm.locator('input[name="variant_id"]').fill(seed.variantId);
  await overrideForm.locator('select[name="store_id"]').selectOption(seed.storeId);
  await overrideForm.locator('select[name="scope_type"]').selectOption("channel");
  await overrideForm.locator('select[name="scope_id"]').selectOption(seed.channelId);
  await overrideForm.locator('input[name="unit_amount"]').fill("49.99");
  await overrideForm.locator('input[name="currency_code"]').fill("USD");
  await overrideForm.locator('input[name="reason"]').fill("Flash sale");
  await overrideForm.getByRole("button",{name:"Crear override"}).click();
  await expect(page.getByText(/49\.9900 USD/)).toBeVisible();

  const resolvedByOverride=await page.evaluate(async({endpoint,variantId,channelId})=>{
    const token=sessionStorage.getItem("access_token")!;
    const response=await fetch(`${endpoint}/pricing/resolve?variant_id=${variantId}&channel_id=${channelId}`,{headers:{"Authorization":`Bearer ${token}`},credentials:"include"});
    return response.json();
  },{endpoint:apiURL,variantId:seed.variantId,channelId:seed.channelId});
  expect(resolvedByOverride.source).toBe("override");
  expect(resolvedByOverride.unit_amount).toBe("49.9900");

  await page.getByRole("link",{name:"Historial de precios",exact:true}).click();
  await page.getByPlaceholder("Filtrar por ID de Variant").fill(seed.variantId);
  await page.getByRole("button",{name:"Filtrar"}).click();
  await expect(page.getByText("unit_amount").first()).toBeVisible();
  await expect(page.getByText(/— → 80\.0000/)).toBeVisible();
});
