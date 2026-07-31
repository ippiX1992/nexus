import {randomUUID} from "node:crypto";
import {expect,test} from "@playwright/test";

const apiURL=process.env.E2E_API_URL??"http://127.0.0.1:8000/api/v1";
const password=process.env.E2E_PASSWORD??"E2E-only-password-99";

test("Warehouse, location, receive stock, fulfillment scope, reserve, and availability drop",async({page})=>{
  const marker=`${Date.now()}-${randomUUID().slice(0,8)}`;
  const email=`inventory-owner-${marker}@example.com`;
  const company=`Inventory Tenant ${marker}`;

  await page.goto("/register");
  await page.getByLabel("Nombre",{exact:true}).fill("Inventory Owner");
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

  // Seed Store + Channel + a Product (default Variant) via the API -- those
  // UI flows are covered by other specs; this test drives only what M4.1 adds.
  const seed=await page.evaluate(async({endpoint})=>{
    function headers(token:string){
      const csrf=document.cookie.split("; ").find(value=>value.startsWith("csrf_token="))?.split("=")[1];
      return {"Content-Type":"application/json","Authorization":`Bearer ${token}`,...(csrf?{"X-CSRF-Token":decodeURIComponent(csrf)}:{})};
    }
    const token=sessionStorage.getItem("access_token")!;
    async function call(path:string,init:RequestInit={}){return fetch(`${endpoint}${path}`,{...init,credentials:"include"})}
    const store=await (await call("/stores",{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({code:"inv-store",name:"Inv Store",slug:"inv-store",default_locale:"es-EC",default_currency:"USD",timezone:"America/Guayaquil"})})).json();
    await call(`/stores/${store.id}/activate`,{method:"POST",headers:headers(token)});
    const channel=await (await call(`/stores/${store.id}/channels`,{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({code:"web",name:"Web",channel_type:"web"})})).json();
    const productType=await (await call("/catalog/product-types",{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({code:"inv-type",name:"Inv Type"})})).json();
    const productResponse=await call("/catalog/products",{method:"POST",headers:{...headers(token),"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({product_type_id:productType.id,code:"inv-product",sku:"INV-E2E-1",translation:{locale:"es-EC",name:"Inv Product",short_description:"S",long_description:"L",slug:"inv-product"}})});
    const detail=await productResponse.json();
    return {storeId:store.id,channelId:channel.id,variantId:detail.variants[0].id};
  },{endpoint:apiURL});

  // Create a Warehouse via the UI.
  await page.getByRole("link",{name:"Warehouses",exact:true}).click();
  const whForm=page.locator("form").filter({hasText:"Crear Warehouse"});
  await whForm.getByLabel("Código").fill(`wh-${marker}`);
  await whForm.getByLabel("Nombre").fill(`Warehouse ${marker}`);
  await whForm.getByRole("button",{name:"Crear Warehouse"}).click();
  const whRow=page.locator(".row").filter({hasText:`Warehouse ${marker}`});
  await expect(whRow).toBeVisible();

  // Open the warehouse detail, add a Location and a Channel fulfillment scope.
  await whRow.getByRole("link",{name:"Locations & scopes"}).click();
  await page.waitForURL("**/commerce/warehouses/**");
  const locForm=page.locator("form").filter({hasText:"Crear Location"});
  await locForm.getByLabel("Código").fill("a1");
  await locForm.getByLabel("Nombre").fill("Aisle 1");
  await locForm.getByRole("button",{name:"Crear Location"}).click();
  await expect(page.locator(".row").filter({hasText:"Aisle 1"})).toBeVisible();

  const scopeForm=page.locator("form").filter({hasText:"Asignar este warehouse a un scope"});
  await scopeForm.locator('select[name="store_id"]').selectOption(seed.storeId);
  await scopeForm.locator('select[name="scope_type"]').selectOption("channel");
  await scopeForm.locator('select[name="scope_id"]').selectOption(seed.channelId);
  await scopeForm.locator('input[name="priority"]').fill("5");
  await scopeForm.getByRole("button",{name:"Crear scope"}).click();
  await expect(page.getByText("channel").first()).toBeVisible();

  // Receive stock through the Inventario page.
  await page.getByRole("link",{name:"Inventario",exact:true}).click();
  const moveForm=page.locator("form").filter({hasText:"Movimiento de stock"});
  await moveForm.locator('select[name="kind"]').selectOption("receive");
  await moveForm.locator('select[name="location_id"]').selectOption({index:1});
  await moveForm.locator('input[name="variant_id"]').fill(seed.variantId);
  await moveForm.locator('input[name="amount"]').fill("10");
  await moveForm.getByRole("button",{name:"Aplicar movimiento"}).click();
  await expect(page.getByText(/on_hand 10 · reservado 0 · disponible 10/)).toBeVisible();

  // Reserve 4 through the channel via the API (reservation engine), then
  // confirm available dropped to 6 in the UI.
  const reserved=await page.evaluate(async({endpoint,variantId,channelId})=>{
    const token=sessionStorage.getItem("access_token")!;
    const response=await fetch(`${endpoint}/inventory/reservations`,{
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":`Bearer ${token}`,"Idempotency-Key":crypto.randomUUID()},
      credentials:"include",
      body:JSON.stringify({variant_id:variantId,quantity:4,scope_type:"channel",scope_id:channelId}),
    });
    return {status:response.status,body:await response.json()};
  },{endpoint:apiURL,variantId:seed.variantId,channelId:seed.channelId});
  expect(reserved.status).toBe(201);
  expect(reserved.body.items.reduce((sum:number,item:{quantity:number})=>sum+item.quantity,0)).toBe(4);

  await page.reload();
  await expect(page.getByText(/on_hand 10 · reservado 4 · disponible 6/)).toBeVisible();

  // The append-only ledger shows the receipt.
  await expect(page.getByText("receipt").first()).toBeVisible();

  // Allocation preview via API confirms the engine can still place 6 more.
  const plan=await page.evaluate(async({endpoint,variantId,channelId})=>{
    const token=sessionStorage.getItem("access_token")!;
    const response=await fetch(`${endpoint}/inventory/allocate?variant_id=${variantId}&quantity=6&scope_type=channel&scope_id=${channelId}`,{headers:{"Authorization":`Bearer ${token}`},credentials:"include"});
    return response.json();
  },{endpoint:apiURL,variantId:seed.variantId,channelId:seed.channelId});
  expect(plan.fully_allocated).toBe(true);
  expect(plan.allocated).toBe(6);
});
