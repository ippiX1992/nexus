import {randomUUID} from "node:crypto";
import {expect,test} from "@playwright/test";

const apiURL=process.env.E2E_API_URL??"http://127.0.0.1:8000/api/v1";
const password=process.env.E2E_PASSWORD??"E2E-only-password-99";

test("Options, Variant combinations, duplicate rejection and insufficient permission",async({page})=>{
  const marker=`${Date.now()}-${randomUUID().slice(0,8)}`;
  const email=`catalog-options-owner-${marker}@example.com`;
  const viewerEmail=`catalog-options-viewer-${marker}@example.com`;
  const company=`Catalog Options Tenant ${marker}`;

  await page.goto("/register");
  await page.getByLabel("Nombre",{exact:true}).fill("Options Owner");
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

  await page.getByRole("link",{name:"Platform",exact:true}).click();
  await page.getByRole("link",{name:"Crear store"}).click();
  await page.getByLabel("Código").fill(`store-${marker}`);
  await page.getByLabel("Nombre").fill("Options Store");
  await page.getByLabel("Slug").fill(`store-${marker}`);
  await page.getByRole("button",{name:"Crear store"}).click();
  await page.waitForURL("**/platform/stores/**");
  await page.getByRole("button",{name:"Activar"}).click();
  await expect(page.getByText("active",{exact:true})).toBeVisible();

  await page.getByRole("link",{name:"Catalog",exact:true}).click();
  await page.getByRole("link",{name:"Product Types",exact:true}).click();
  const typeForm=page.locator("form").filter({hasText:"Crear Product Type"});
  await typeForm.getByLabel("Código").fill(`type-${marker}`);
  await typeForm.getByLabel("Nombre").fill("E2E Options Product Type");
  await typeForm.getByLabel("Descripción").fill("Catalog Options E2E");
  await typeForm.getByRole("button",{name:"Crear Product Type"}).click();
  await expect(page.locator(".row").filter({hasText:"E2E Options Product Type"})).toBeVisible();

  await page.getByRole("link",{name:"Products",exact:true}).click();
  await page.getByRole("link",{name:"Crear Product"}).click();
  await page.getByLabel("Product Type").selectOption({label:"E2E Options Product Type"});
  await page.getByLabel("Código interno").fill(`product-${marker}`);
  await page.getByLabel("SKU default").fill(`SKU-${marker}`);
  await page.getByLabel("Nombre",{exact:true}).fill("E2E Options Product");
  await page.getByLabel("Slug").fill(`product-${marker}`);
  await page.getByLabel("Locale").fill("es-EC");
  await page.getByRole("button",{name:"Crear Product"}).click();
  await expect(page.getByText("Default Variant",{exact:true})).toBeVisible();
  await page.waitForURL(/\/catalog\/products\/[0-9a-f-]{36}$/);
  const productURL=page.url();

  await page.getByRole("link",{name:"Options",exact:true}).click();
  const optionForm=page.locator("form").filter({hasText:"Crear Option"});
  await optionForm.getByLabel("Código").fill(`color-${marker}`);
  await optionForm.getByLabel("Nombre").fill(`Color ${marker}`);
  await optionForm.getByRole("button",{name:"Crear Option"}).click();
  const optionTile=page.locator(".tile").filter({hasText:`Color ${marker}`});
  await expect(optionTile).toBeVisible();
  await optionTile.getByRole("button",{name:"Ver valores"}).click();

  await optionTile.getByPlaceholder("código").fill("rojo");
  await optionTile.getByPlaceholder("valor").fill("Rojo");
  await optionTile.getByRole("button",{name:"Agregar valor"}).click();
  await expect(optionTile.getByText("Rojo (rojo)")).toBeVisible();

  await optionTile.getByPlaceholder("código").fill("negro");
  await optionTile.getByPlaceholder("valor").fill("Negro");
  await optionTile.getByRole("button",{name:"Agregar valor"}).click();
  await expect(optionTile.getByText("Negro (negro)")).toBeVisible();

  await page.goto(productURL);
  await page.getByLabel("Agregar Option").selectOption({label:`Color ${marker}`});
  await expect(page.getByText(`Color ${marker} · requerida`)).toBeVisible();

  const variantForm=page.locator("form").filter({hasText:"Crear Variant"});
  await variantForm.getByLabel("Nuevo SKU").fill(`SKU-RED-${marker}`);
  await variantForm.getByLabel(`Color ${marker}`).selectOption({label:"Rojo"});
  await variantForm.getByRole("button",{name:"Crear Variant"}).click();
  await expect(page.getByLabel(`SKU SKU-RED-${marker}`)).toHaveValue(`SKU-RED-${marker}`);
  await expect(page.getByText(new RegExp(`Color ${marker}: Rojo`))).toBeVisible();

  const duplicateEvidence=await page.evaluate(
    async({endpoint,productId,skuValue})=>{
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
      const optionsResponse=await call("/catalog/options",{headers:headers(ownerToken)});
      const options=(await optionsResponse.json()).items;
      const option=options[options.length-1];
      const valuesResponse=await call(`/catalog/options/${option.id}/values`,{headers:headers(ownerToken)});
      const values=await valuesResponse.json();
      const red=values.find((value:{value:string})=>value.value==="Rojo");
      const duplicate=await call(`/catalog/products/${productId}/variants`,{
        method:"POST",
        headers:{...headers(ownerToken),"Idempotency-Key":crypto.randomUUID()},
        body:JSON.stringify({sku:skuValue,option_value_ids:[red.id]}),
      });
      return {status:duplicate.status,body:await duplicate.json()};
    },
    {endpoint:apiURL,productId:productURL.split("/").pop(),skuValue:`SKU-RED-DUP-${marker}`},
  );
  expect(duplicateEvidence.status).toBe(409);

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
        body:JSON.stringify({token:invitation.invitation_token,password:viewerPassword,full_name:"Options Viewer"}),
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
      const forbiddenResponse=await call("/catalog/options",{
        method:"POST",
        headers:{...headers(selected.access_token),"Idempotency-Key":crypto.randomUUID()},
        body:JSON.stringify({code:"viewer-denied-option",name:"Viewer Denied Option"}),
      });
      return {forbidden:forbiddenResponse.status};
    },
    {endpoint:apiURL,viewerEmail,viewerPassword:password},
  );
  expect(permissionEvidence.forbidden).toBe(403);
});
