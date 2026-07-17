import {beforeEach,describe,expect,it} from "vitest";
import {vi} from "vitest";
import {ApiError,saveToken} from "../lib/api";
import {
  catalogCommand,
  catalogCreate,
  catalogGet,
  catalogPage,
  catalogUpdate,
  technicalError,
  type Option,
  type OptionValue,
  type ProductOption,
  type VariantOptionValue,
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

describe("Catalog Options client",()=>{
  beforeEach(()=>{
    sessionStorage.clear();
    saveToken("catalog-options-token");
    vi.restoreAllMocks();
  });

  it("lists Options as a cursor page",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({items:[{id:"opt-1",code:"color",name:"Color",input_type:"swatch",position:0,status:"active",version:1}],has_more:false}),
    );

    const page=await catalogPage<Option>("/options");

    expect(page.items[0].code).toBe("color");
    expect(fetchMock.mock.calls[0][0]).toContain("/catalog/options");
  });

  it("creates an Option with a generated Idempotency-Key",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"opt-1",code:"color",name:"Color",input_type:"swatch",position:0,status:"active",version:1},201),
    );

    await catalogCreate<Option>("/options",{code:"color",name:"Color",input_type:"swatch"});

    const request=fetchMock.mock.calls[0][1]!;
    const headers=request.headers as Headers;
    expect(request.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toMatch(/.+/);
    expect(JSON.parse(request.body as string).code).toBe("color");
  });

  it("creates an Option Value scoped to its Option",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"val-1",option_id:"opt-1",code:"red",value:"Rojo",position:0,status:"active",version:1},201),
    );

    await catalogCreate<OptionValue>("/options/opt-1/values",{code:"red",value:"Rojo",swatch_hex:"#FF0000"});

    expect(fetchMock.mock.calls[0][0]).toContain("/catalog/options/opt-1/values");
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string).swatch_hex).toBe("#FF0000");
  });

  it("archives an Option using If-Match with its current version",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"opt-1",code:"color",name:"Color",input_type:"swatch",position:0,status:"archived",version:2}),
    );

    await catalogCommand<Option>("/options/opt-1/archive",1);

    const headers=fetchMock.mock.calls[0][1]!.headers as Headers;
    expect(headers.get("If-Match")).toBe("1");
    expect(fetchMock.mock.calls[0][1]!.method).toBe("POST");
  });

  it("archives an Option Value using If-Match",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"val-1",option_id:"opt-1",code:"red",value:"Rojo",position:0,status:"archived",version:2}),
    );

    await catalogCommand<OptionValue>("/option-values/val-1/archive",1);

    const headers=fetchMock.mock.calls[0][1]!.headers as Headers;
    expect(headers.get("If-Match")).toBe("1");
  });

  it("replaces Product Options with PUT and If-Match on the Product version",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json([{product_id:"prod-1",option_id:"opt-1",required:true,position:0,version:1}]),
    );

    await catalogUpdate<ProductOption[]>(
      "/products/prod-1/options",
      {options:[{option_id:"opt-1",position:0}]},
      5,
      "PUT",
    );

    const request=fetchMock.mock.calls[0][1]!;
    const headers=request.headers as Headers;
    expect(request.method).toBe("PUT");
    expect(headers.get("If-Match")).toBe("5");
    expect(JSON.parse(request.body as string).options).toEqual([{option_id:"opt-1",position:0}]);
  });

  it("creates a Variant with a combination via option_value_ids",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({id:"var-1",product_id:"prod-1",sku:"SHIRT-RED-S",is_default:false,status:"active",combination_fingerprint:"abc123",version:1},201),
    );

    await catalogCreate("/products/prod-1/variants",{sku:"SHIRT-RED-S",option_value_ids:["val-red","val-s"]});

    const body=JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.option_value_ids).toEqual(["val-red","val-s"]);
  });

  it("reads a Variant's combination via GET /variants/{id}/options",async()=>{
    vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json([{variant_id:"var-1",product_id:"prod-1",option_id:"opt-1",option_value_id:"val-red"}]),
    );

    const combination=await catalogGet<VariantOptionValue[]>("/variants/var-1/options");

    expect(combination).toHaveLength(1);
    expect(combination[0].option_value_id).toBe("val-red");
  });

  it.each([
    [409,"This combination already exists for another Variant of this Product","combination-correlation"],
    [409,"Quota exceeded for catalog.product_options.max_per_product","options-quota-correlation"],
  ])("surfaces Options errors with correlation evidence",async(status,detail,correlation)=>{
    vi.spyOn(globalThis,"fetch").mockResolvedValue(
      json({detail},status,{"X-Correlation-ID":correlation}),
    );

    let captured:unknown;
    try {
      await catalogCreate("/products/prod-1/variants",{sku:"DUP",option_value_ids:["val-red"]});
    } catch (error) {
      captured=error;
    }

    expect(captured).toBeInstanceOf(ApiError);
    expect((captured as ApiError).status).toBe(status);
    expect(technicalError(captured)).toContain(detail);
    expect(technicalError(captured)).toContain(correlation);
  });
});
