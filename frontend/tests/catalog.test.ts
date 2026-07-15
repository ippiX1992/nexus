import {beforeEach,describe,expect,it,vi} from "vitest";
import {ApiError,saveToken} from "../lib/api";
import {
  catalogCommand,
  catalogCreate,
  catalogGet,
  catalogPage,
  catalogUpdate,
  technicalError,
  type Category,
  type Product,
} from "../lib/catalog";

function json(
  value: unknown,
  status = 200,
  headers: Record<string,string> = {},
) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {"Content-Type":"application/json",...headers},
  });
}

describe("Catalog Foundation client",()=>{
  beforeEach(()=>{
    sessionStorage.clear();
    saveToken("catalog-token");
    vi.restoreAllMocks();
  });

  it("loads a cursor page without offset pagination",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({items:[{id:"p1",status:"draft"}],next_cursor:"opaque",has_more:true}),
    );

    const page=await catalogPage<Product>("/products?limit=25&cursor=opaque");

    expect(page.next_cursor).toBe("opaque");
    expect(page.has_more).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toContain(
      "/catalog/products?limit=25&cursor=opaque",
    );
  });

  it("creates a simple product with a generated idempotency key",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({product:{id:"p1"},variants:[{id:"v1",is_default:true}]},201),
    );

    await catalogCreate("/products",{
      product_type_id:"type-1",
      sku:"SKU-1",
      translation:{locale:"es-EC",name:"Product",slug:"product"},
    });

    const request=fetchMock.mock.calls[0][1]!;
    const headers=request.headers as Headers;
    expect(request.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toMatch(/.+/);
    expect(JSON.parse(request.body as string).sku).toBe("SKU-1");
  });

  it("uses If-Match for versioned updates and logical removal",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch")
      .mockResolvedValueOnce(json({id:"v1",version:4}))
      .mockResolvedValueOnce(json({id:"a1",status:"archived",version:3}));

    await catalogUpdate("/variants/v1",{sku:"SKU-2"},3);
    await catalogCommand("/products/p1/stores/s1",2,"DELETE");

    const updateHeaders=fetchMock.mock.calls[0][1]!.headers as Headers;
    const deleteHeaders=fetchMock.mock.calls[1][1]!.headers as Headers;
    expect(updateHeaders.get("If-Match")).toBe("3");
    expect(deleteHeaders.get("If-Match")).toBe("2");
    expect(fetchMock.mock.calls[1][1]!.method).toBe("DELETE");
  });

  it("builds a category tree and assigns a product to a store",async()=>{
    const categories:Category[]=[
      {
        id:"root",
        taxonomy_id:"tax",
        code:"root",
        name:"Root",
        slug:"root",
        position:0,
        status:"active",
        version:1,
      },
      {
        id:"child",
        taxonomy_id:"tax",
        parent_id:"root",
        code:"child",
        name:"Child",
        slug:"child",
        position:0,
        status:"active",
        version:1,
      },
    ];
    const fetchMock=vi.spyOn(globalThis,"fetch")
      .mockResolvedValueOnce(json(categories))
      .mockResolvedValueOnce(
        json({id:"assignment",store_id:"store",status:"draft",eligible:false}),
      );

    const tree=await catalogGet<Category[]>("/taxonomies/tax/categories");
    const child=tree.find(item=>item.parent_id==="root");
    expect(child?.name).toBe("Child");

    await catalogCreate(
      "/products/product/stores/store",
      {status:"draft"},
      "PUT",
    );
    const assignmentRequest=fetchMock.mock.calls[1][1]!;
    const headers=assignmentRequest.headers as Headers;
    expect(assignmentRequest.method).toBe("PUT");
    expect(headers.get("Idempotency-Key")).toMatch(/.+/);
  });

  it.each([
    [409,"SKU already reserved","sku-correlation"],
    [429,"Quota exceeded for catalog.products.max","quota-correlation"],
    [409,"Version conflict: expected 1, current 2","version-correlation"],
  ])("surfaces Catalog errors with correlation evidence",async(status,detail,correlation)=>{
    vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({detail},status,{"X-Correlation-ID":correlation}),
    );

    let captured:unknown;
    try {
      await catalogCreate("/products",{sku:"duplicate"});
    } catch (error) {
      captured=error;
    }

    expect(captured).toBeInstanceOf(ApiError);
    expect((captured as ApiError).status).toBe(status);
    expect(technicalError(captured)).toContain(detail);
    expect(technicalError(captured)).toContain(correlation);
  });
});
