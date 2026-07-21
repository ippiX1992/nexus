import {randomUUID} from "node:crypto";
import {expect,test} from "@playwright/test";

const apiURL=process.env.E2E_API_URL??"http://127.0.0.1:8000/api/v1";
const password=process.env.E2E_PASSWORD??"E2E-only-password-99";

test("Catalog Foundation owner flow and viewer isolation",async({page})=>{
  const marker=`${Date.now()}-${randomUUID().slice(0,8)}`;
  const email=`catalog-owner-${marker}@example.com`;
  const viewerEmail=`catalog-viewer-${marker}@example.com`;
  const company=`Catalog Tenant ${marker}`;

  await page.goto("/register");
  await page.getByLabel("Nombre",{exact:true}).fill("Catalog Owner");
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
  await page.getByLabel("Nombre").fill("Catalog Store");
  await page.getByLabel("Slug").fill(`store-${marker}`);
  await page.getByRole("button",{name:"Crear store"}).click();
  await page.waitForURL("**/platform/stores/**");
  await page.getByRole("button",{name:"Activar"}).click();
  await expect(page.getByText("active",{exact:true})).toBeVisible();

  await page.getByRole("link",{name:"Products",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Products"})).toBeVisible();
  await page.getByRole("link",{name:"Product Types",exact:true}).click();
  const typeForm=page.locator("form").filter({hasText:"Crear Product Type"});
  await typeForm.getByLabel("Código").fill(`type-${marker}`);
  await typeForm.getByLabel("Nombre").fill("E2E Product Type");
  await typeForm.getByLabel("Descripción").fill("Catalog Foundation E2E");
  await typeForm.getByRole("button",{name:"Crear Product Type"}).click();
  await expect(page.locator(".row").filter({hasText:"E2E Product Type"})).toBeVisible();

  await page.getByRole("link",{name:"Brands",exact:true}).click();
  const brandForm=page.locator("form").filter({hasText:"Crear Brand"});
  await brandForm.getByLabel("Código").fill(`brand-${marker}`);
  await brandForm.getByLabel("Nombre").fill("E2E Brand");
  await brandForm.getByLabel("Slug").fill(`brand-${marker}`);
  await brandForm.getByRole("button",{name:"Crear Brand"}).click();
  await expect(page.locator(".row").filter({hasText:"E2E Brand"})).toBeVisible();

  await page.getByRole("link",{name:"Products",exact:true}).click();
  await page.getByRole("link",{name:"Crear Product"}).click();
  await page.getByLabel("Product Type").selectOption({label:"E2E Product Type"});
  await page.getByLabel("Brand").selectOption({label:"E2E Brand"});
  await page.getByLabel("Código interno").fill(`product-${marker}`);
  await page.getByLabel("SKU default").fill(`SKU-${marker}`);
  await page.getByLabel("Nombre",{exact:true}).fill("E2E Catalog Product");
  await page.getByLabel("Slug").fill(`product-${marker}`);
  await page.getByLabel("Locale").fill("es-EC");
  await page.getByRole("button",{name:"Crear Product"}).click();
  await page.waitForURL("**/catalog/products/**");
  await expect(page.getByText("Default Variant",{exact:true})).toBeVisible();
  await expect(page.getByLabel(`SKU SKU-${marker}`)).toHaveValue(`SKU-${marker}`);
  await page.getByRole("button",{name:"Activar"}).click();
  await expect(page.getByText(/active · v\d+ · activo no significa publicado/)).toBeVisible();

  await page.getByRole("link",{name:"Taxonomies",exact:true}).click();
  const taxonomyForm=page.locator("form").filter({hasText:"Crear Taxonomy"});
  await taxonomyForm.getByLabel("Código").fill(`taxonomy-${marker}`);
  await taxonomyForm.getByLabel("Nombre").fill("E2E Taxonomy");
  await taxonomyForm.getByRole("button",{name:"Crear Taxonomy"}).click();
  await expect(page.getByLabel("Taxonomy")).toHaveValue(/.+/);

  const categoryForm=page.locator("form").filter({hasText:"Crear Category"});
  await categoryForm.getByLabel("Código").fill(`category-${marker}`);
  await categoryForm.getByLabel("Nombre").fill("E2E Category");
  await categoryForm.getByLabel("Slug").fill(`category-${marker}`);
  await categoryForm.getByRole("button",{name:"Crear Category"}).click();
  await expect(page.locator(".row").filter({hasText:"E2E Category"})).toBeVisible();

  await page.getByRole("link",{name:"Products",exact:true}).click();
  await page.getByRole("link",{name:"E2E Catalog Product",exact:true}).click();
  await page.getByLabel("Agregar Category").selectOption({label:"E2E Category"});
  await expect(page.getByText(/E2E Category · primary/)).toBeVisible();
  await page.getByLabel("Store assignment").selectOption({label:"Catalog Store"});
  await page.getByRole("button",{name:"Asignar Store"}).click();
  await expect(page.getByText(/draft · no eligible/)).toBeVisible();
  await expect(page.getByText("E2E Catalog Product",{exact:true})).toBeVisible();

  const permissionEvidence=await page.evaluate(
    async({endpoint,viewerEmail,viewerPassword})=>{
      function headers(token?:string){
        const csrf=document.cookie
          .split("; ")
          .find(value=>value.startsWith("csrf_token="))
          ?.split("=")[1];
        return {
          "Content-Type":"application/json",
          ...(token?{"Authorization":`Bearer ${token}`}:{}),
          ...(csrf?{"X-CSRF-Token":decodeURIComponent(csrf)}:{}),
        };
      }
      async function call(path:string,init:RequestInit={}){
        return fetch(`${endpoint}${path}`,{
          ...init,
          credentials:"include",
        });
      }

      const ownerToken=sessionStorage.getItem("access_token")!;
      const context=await (
        await call("/me/context",{headers:headers(ownerToken)})
      ).json();
      const roles=await (
        await call("/roles",{headers:headers(ownerToken)})
      ).json();
      const viewer=roles.find((role:{name:string})=>role.name==="viewer");
      const invitationResponse=await call("/members/invitations",{
        method:"POST",
        headers:headers(ownerToken),
        body:JSON.stringify({email:viewerEmail,role_ids:[viewer.id]}),
      });
      const invitation=await invitationResponse.json();
      const acceptResponse=await call("/members/invitations/accept",{
        method:"POST",
        headers:headers(),
        body:JSON.stringify({
          token:invitation.invitation_token,
          password:viewerPassword,
          full_name:"Catalog Viewer",
        }),
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
      const forbiddenResponse=await call("/catalog/product-types",{
        method:"POST",
        headers:{
          ...headers(selected.access_token),
          "Idempotency-Key":crypto.randomUUID(),
        },
        body:JSON.stringify({code:"viewer-denied",name:"Viewer Denied"}),
      });
      return {
        invitation:invitationResponse.status,
        accepted:acceptResponse.status,
        selected:selectedResponse.status,
        forbidden:forbiddenResponse.status,
      };
    },
    {endpoint:apiURL,viewerEmail,viewerPassword:password},
  );
  expect(permissionEvidence.invitation).toBe(201);
  expect(permissionEvidence.accepted).toBe(200);
  expect(permissionEvidence.selected).toBe(200);
  expect(permissionEvidence.forbidden).toBe(403);
});
