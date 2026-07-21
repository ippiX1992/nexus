import {randomUUID} from "node:crypto";
import {expect,test} from "@playwright/test";

const apiURL=process.env.E2E_API_URL??"http://127.0.0.1:8000/api/v1";
const password=process.env.E2E_PASSWORD??"E2E-only-password-99";

test("Attributes, Product Type assignment, specifications persistence, and negative cases",async({page})=>{
  const marker=`${Date.now()}-${randomUUID().slice(0,8)}`;
  const email=`catalog-attributes-owner-${marker}@example.com`;
  const viewerEmail=`catalog-attributes-viewer-${marker}@example.com`;
  const company=`Catalog Attributes Tenant ${marker}`;

  await page.goto("/register");
  await page.getByLabel("Nombre",{exact:true}).fill("Attributes Owner");
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

  await page.getByRole("link",{name:"Stores",exact:true}).click();
  await page.getByRole("link",{name:"Crear store"}).click();
  await page.getByLabel("Código").fill(`store-${marker}`);
  await page.getByLabel("Nombre").fill("Attributes Store");
  await page.getByLabel("Slug").fill(`store-${marker}`);
  await page.getByRole("button",{name:"Crear store"}).click();
  await page.waitForURL("**/platform/stores/**");
  await page.getByRole("button",{name:"Activar"}).click();
  await expect(page.getByText("active",{exact:true})).toBeVisible();

  await page.getByRole("link",{name:"Attribute Groups",exact:true}).click();
  const groupForm=page.locator("form").filter({hasText:"Crear Attribute Group"});
  await groupForm.getByLabel("Código").fill(`general-${marker}`);
  await groupForm.getByLabel("Nombre").fill(`General ${marker}`);
  await groupForm.getByRole("button",{name:"Crear Attribute Group"}).click();
  await expect(page.locator(".row").filter({hasText:`General ${marker}`})).toBeVisible();

  await page.getByRole("link",{name:"Attributes",exact:true}).click();
  const powerForm=page.locator("form").filter({hasText:"Crear Attribute"});
  await powerForm.getByRole("button",{name:"Crear Attribute"}).waitFor({state:"visible"});
  await page.waitForLoadState("networkidle");
  // The dev server (Turbopack) prefetches every CatalogNav link on first visit
  // to this route, which can trigger a full-page reload mid-fill and reset
  // uncontrolled inputs. Give any pending background compilation time to
  // settle before touching the form -- this is a dev-server quirk, not
  // something CI (production-like build) exhibits.
  await page.waitForTimeout(3000);
  await powerForm.locator('input[name="code"]').fill(`power-${marker}`);
  await powerForm.locator('input[name="name"]').fill(`Power ${marker}`);
  await powerForm.locator('select[name="data_type"]').selectOption("DECIMAL");
  await powerForm.locator('input[name="unit"]').fill("W");
  await powerForm.locator('input[name="is_required"]').check();
  await expect(powerForm.locator('input[name="code"]')).toHaveValue(`power-${marker}`);
  await expect(powerForm.locator('input[name="name"]')).toHaveValue(`Power ${marker}`);
  await powerForm.getByRole("button",{name:"Crear Attribute"}).click();
  await expect(page.locator(".tile").filter({hasText:`Power ${marker}`})).toBeVisible();

  await powerForm.locator('input[name="code"]').fill(`material-${marker}`);
  await powerForm.locator('input[name="name"]').fill(`Material ${marker}`);
  await powerForm.locator('select[name="data_type"]').selectOption("SELECT");
  await expect(powerForm.locator('input[name="code"]')).toHaveValue(`material-${marker}`);
  await powerForm.getByRole("button",{name:"Crear Attribute"}).click();
  const materialTile=page.locator(".tile").filter({hasText:`Material ${marker}`});
  await expect(materialTile).toBeVisible();
  await materialTile.getByRole("button",{name:"Ver valores"}).click();
  await materialTile.getByPlaceholder("código").fill("aluminium");
  await materialTile.getByPlaceholder("etiqueta").fill("Aluminium");
  await materialTile.getByRole("button",{name:"Agregar valor"}).click();
  await expect(materialTile.getByText("Aluminium (aluminium)")).toBeVisible();

  await page.getByRole("link",{name:"Product Types",exact:true}).click();
  const typeForm=page.locator("form").filter({hasText:"Crear Product Type"});
  await typeForm.getByLabel("Código").fill(`type-${marker}`);
  await typeForm.getByLabel("Nombre").fill(`E2E Attributes Type ${marker}`);
  await typeForm.getByLabel("Descripción").fill("Catalog Attributes E2E");
  await typeForm.getByRole("button",{name:"Crear Product Type"}).click();
  const typeTile=page.locator(".tile").filter({hasText:`E2E Attributes Type ${marker}`});
  await expect(typeTile).toBeVisible();
  await typeTile.getByRole("button",{name:"Ver Attributes"}).click();
  await typeTile.getByLabel("Agregar Attribute").selectOption({label:`Power ${marker}`});
  await expect(typeTile.getByText(`Power ${marker} · obligatorio`)).toBeVisible();
  await typeTile.getByLabel("Agregar Attribute").selectOption({label:`Material ${marker}`});
  await expect(typeTile.getByText(`Material ${marker}`)).toBeVisible();

  await page.getByRole("link",{name:"Products",exact:true}).click();
  await page.getByRole("link",{name:"Crear Product"}).click();
  await page.getByLabel("Product Type").selectOption({label:`E2E Attributes Type ${marker}`});
  await page.getByLabel("Código interno").fill(`product-${marker}`);
  await page.getByLabel("SKU default").fill(`SKU-${marker}`);
  await page.getByLabel("Nombre",{exact:true}).fill("E2E Attributes Product");
  await page.getByLabel("Slug").fill(`product-${marker}`);
  await page.getByLabel("Locale").fill("es-EC");
  await page.getByRole("button",{name:"Crear Product"}).click();
  await expect(page.getByText("Default Variant",{exact:true})).toBeVisible();

  const specForm=page.locator("form").filter({has:page.getByRole("button",{name:"Guardar especificaciones"})});
  await specForm.getByLabel(`Power ${marker} (W) *`).fill("500");
  await specForm.getByLabel(`Material ${marker}`).selectOption({label:"Aluminium"});
  await specForm.getByRole("button",{name:"Guardar especificaciones"}).click();
  await expect(page.locator("p.error[role='alert']")).toHaveCount(0);

  await page.reload();
  // PostgreSQL NUMERIC(20,6) preserves trailing zeros -- "500" round-trips as
  // "500.000000", not a formatting bug (see the equivalent Decimal comparison
  // in test_catalog_attributes_api.py).
  await expect(specForm.getByLabel(`Power ${marker} (W) *`)).toHaveValue("500.000000");

  const wrongTypeError=await page.evaluate(
    async({endpoint})=>{
      function headers(token?:string){
        const csrf=document.cookie.split("; ").find(value=>value.startsWith("csrf_token="))?.split("=")[1];
        return {
          "Content-Type":"application/json",
          ...(token?{"Authorization":`Bearer ${token}`}:{}),
          ...(csrf?{"X-CSRF-Token":decodeURIComponent(csrf)}:{}),
        };
      }
      async function call(path:string,init:RequestInit={}){
        return fetch(`${endpoint}${path}`,{...init,credentials:"include"});
      }
      const ownerToken=sessionStorage.getItem("access_token")!;
      const productsResponse=await call("/catalog/products?limit=50",{headers:headers(ownerToken)});
      const products=(await productsResponse.json()).items;
      const product=products[products.length-1];
      const detailResponse=await call(`/catalog/products/${product.id}`,{headers:headers(ownerToken)});
      const detail=await detailResponse.json();
      const attributesResponse=await call("/catalog/attributes?limit=50",{headers:headers(ownerToken)});
      const attributes=(await attributesResponse.json()).items;
      const power=attributes.find((item:{data_type:string})=>item.data_type==="DECIMAL");
      const material=attributes.find((item:{data_type:string})=>item.data_type==="SELECT");
      const wrongType=await call(`/catalog/products/${product.id}/attributes`,{
        method:"PUT",
        headers:{...headers(ownerToken),"If-Match":String(detail.product.version)},
        body:JSON.stringify({values:[{attribute_id:power.id,value:"not-a-number"}]}),
      });
      const invalidOption=await call(`/catalog/products/${product.id}/attributes`,{
        method:"PUT",
        headers:{...headers(ownerToken),"If-Match":String(detail.product.version)},
        body:JSON.stringify({values:[{attribute_id:material.id,value:"00000000-0000-0000-0000-000000000000"}]}),
      });
      return {wrongType:wrongType.status,invalidOption:invalidOption.status};
    },
    {endpoint:apiURL},
  );
  expect(wrongTypeError.wrongType).toBe(422);
  expect(wrongTypeError.invalidOption).toBe(422);

  const permissionEvidence=await page.evaluate(
    async({endpoint,viewerEmail,viewerPassword})=>{
      function headers(token?:string){
        const csrf=document.cookie.split("; ").find(value=>value.startsWith("csrf_token="))?.split("=")[1];
        return {
          "Content-Type":"application/json",
          ...(token?{"Authorization":`Bearer ${token}`}:{}),
          ...(csrf?{"X-CSRF-Token":decodeURIComponent(csrf)}:{}),
        };
      }
      async function call(path:string,init:RequestInit={}){
        return fetch(`${endpoint}${path}`,{...init,credentials:"include"});
      }
      const ownerToken=sessionStorage.getItem("access_token")!;
      const context=await (await call("/me/context",{headers:headers(ownerToken)})).json();
      const roles=await (await call("/roles",{headers:headers(ownerToken)})).json();
      const viewer=roles.find((role:{name:string})=>role.name==="viewer");
      const invitationResponse=await call("/members/invitations",{
        method:"POST",
        headers:headers(ownerToken),
        body:JSON.stringify({email:viewerEmail,role_ids:[viewer.id]}),
      });
      const invitation=await invitationResponse.json();
      await call("/members/invitations/accept",{
        method:"POST",
        headers:headers(),
        body:JSON.stringify({token:invitation.invitation_token,password:viewerPassword,full_name:"Attributes Viewer"}),
      });
      const loginResponse=await call("/auth/login",{
        method:"POST",
        headers:headers(),
        body:JSON.stringify({email:viewerEmail,password:viewerPassword}),
      });
      const login=await loginResponse.json();
      const selectedResponse=await call("/auth/select-tenant",{
        method:"POST",
        headers:headers(login.access_token),
        body:JSON.stringify({tenant_id:context.tenant_id}),
      });
      const selected=await selectedResponse.json();
      const forbiddenResponse=await call("/catalog/attributes",{
        method:"POST",
        headers:{...headers(selected.access_token),"Idempotency-Key":crypto.randomUUID()},
        body:JSON.stringify({code:"viewer-denied-attribute",name:"Viewer Denied",data_type:"TEXT"}),
      });
      return {forbidden:forbiddenResponse.status};
    },
    {endpoint:apiURL,viewerEmail,viewerPassword:password},
  );
  expect(permissionEvidence.forbidden).toBe(403);
});
