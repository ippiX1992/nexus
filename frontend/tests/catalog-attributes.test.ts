import {beforeEach,describe,expect,it,vi} from "vitest";
import {ApiError,saveToken} from "../lib/api";
import {
  catalogCommand,
  catalogCreate,
  catalogGet,
  catalogPage,
  catalogUpdate,
  technicalError,
  type Attribute,
  type AttributeGroup,
  type AttributeOption,
  type ProductAttributeValue,
  type ProductTypeAttribute,
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

describe("Catalog Attributes client",()=>{
  beforeEach(()=>{
    sessionStorage.clear();
    saveToken("catalog-attributes-token");
    vi.restoreAllMocks();
  });

  it("lists Attributes as a cursor page",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({items:[{id:"attr-1",code:"power",name:"Power",data_type:"DECIMAL",status:"active"}],has_more:false}),
    );

    const page=await catalogPage<Attribute>("/attributes");

    expect(page.items[0].data_type).toBe("DECIMAL");
    expect(fetchMock.mock.calls[0][0]).toContain("/catalog/attributes");
  });

  it("creates an Attribute with a generated Idempotency-Key",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"attr-1",code:"power",name:"Power",data_type:"DECIMAL",status:"active",version:1},201),
    );

    await catalogCreate<Attribute>("/attributes",{code:"power",name:"Power",data_type:"DECIMAL"});

    const request=fetchMock.mock.calls[0][1]!;
    const headers=request.headers as Headers;
    expect(request.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toMatch(/.+/);
    expect(JSON.parse(request.body as string).data_type).toBe("DECIMAL");
  });

  it("creates an Attribute Option scoped to its Attribute",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"opt-1",attribute_id:"attr-1",code:"aluminium",label:"Aluminium",status:"active"},201),
    );

    await catalogCreate<AttributeOption>("/attributes/attr-1/options",{code:"aluminium",label:"Aluminium"});

    expect(fetchMock.mock.calls[0][0]).toContain("/catalog/attributes/attr-1/options");
  });

  it("archives an Attribute using If-Match with its current version",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"attr-1",code:"power",name:"Power",data_type:"DECIMAL",status:"archived",version:2}),
    );

    await catalogCommand<Attribute>("/attributes/attr-1/archive",1);

    const headers=fetchMock.mock.calls[0][1]!.headers as Headers;
    expect(headers.get("If-Match")).toBe("1");
    expect(fetchMock.mock.calls[0][1]!.method).toBe("POST");
  });

  it("restores an archived Attribute using If-Match",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"attr-1",code:"power",name:"Power",data_type:"DECIMAL",status:"active",version:3}),
    );

    await catalogCommand<Attribute>("/attributes/attr-1/restore",2);

    const headers=fetchMock.mock.calls[0][1]!.headers as Headers;
    expect(headers.get("If-Match")).toBe("2");
  });

  it("creates an Attribute Group",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"group-1",code:"general",name:"General",status:"active"},201),
    );

    await catalogCreate<AttributeGroup>("/attribute-groups",{code:"general",name:"General"});

    expect(fetchMock.mock.calls[0][0]).toContain("/catalog/attribute-groups");
  });

  it("replaces Product Type Attributes with PUT and If-Match on the Product Type version",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json([{product_type_id:"type-1",attribute_id:"attr-1",position:0,required:true,version:1}]),
    );

    await catalogUpdate<ProductTypeAttribute[]>(
      "/product-types/type-1/attributes",
      {attributes:[{attribute_id:"attr-1",position:0,required:true}]},
      3,
      "PUT",
    );

    const request=fetchMock.mock.calls[0][1]!;
    const headers=request.headers as Headers;
    expect(request.method).toBe("PUT");
    expect(headers.get("If-Match")).toBe("3");
    expect(JSON.parse(request.body as string).attributes[0].required).toBe(true);
  });

  it("replaces Product specification values with PUT and If-Match on the Product version",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json([{product_id:"prod-1",attribute_id:"attr-1",value_decimal:"500",version:1}]),
    );

    await catalogUpdate<ProductAttributeValue[]>(
      "/products/prod-1/attributes",
      {values:[{attribute_id:"attr-1",value:"500"}]},
      5,
      "PUT",
    );

    const request=fetchMock.mock.calls[0][1]!;
    const headers=request.headers as Headers;
    expect(request.method).toBe("PUT");
    expect(headers.get("If-Match")).toBe("5");
  });

  it("reads a Product's MULTI_SELECT memberships via GET",async()=>{
    vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json([{product_id:"prod-1",attribute_id:"attr-2",attribute_option_id:"opt-1"}]),
    );

    const values=await catalogGet<{attribute_option_id:string}[]>("/products/prod-1/attribute-value-options");

    expect(values).toHaveLength(1);
    expect(values[0].attribute_option_id).toBe("opt-1");
  });

  it.each([
    [422,"DECIMAL value must be a valid number","type-correlation"],
    [422,"Missing a value for a required Attribute","required-correlation"],
    [409,"Quota exceeded for catalog.attribute_options.max_per_attribute","quota-correlation"],
  ])("surfaces Attributes errors with correlation evidence",async(status,detail,correlation)=>{
    vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({detail},status,{"X-Correlation-ID":correlation}),
    );

    let captured:unknown;
    try {
      await catalogCreate("/products/prod-1/attributes",{values:[{attribute_id:"attr-1",value:"bad"}]});
    } catch (error) {
      captured=error;
    }

    expect(captured).toBeInstanceOf(ApiError);
    expect((captured as ApiError).status).toBe(status);
    expect(technicalError(captured)).toContain(detail);
    expect(technicalError(captured)).toContain(correlation);
  });
});
