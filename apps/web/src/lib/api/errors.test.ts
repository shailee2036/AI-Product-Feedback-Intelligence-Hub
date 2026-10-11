import { describe, expect, it } from "vitest";

import { describeReason } from "@/lib/eligibility";

import { ApiError, parseErrorDetail } from "./errors";

describe("parseErrorDetail", () => {
  it("reads string details", () => {
    expect(parseErrorDetail(409, { detail: "Already registered." })).toEqual({
      message: "Already registered.",
      reasons: [],
    });
  });

  it("reads eligibility rejections with reasons", () => {
    const body = {
      detail: { message: "Repository is not eligible.", reasons: ["archived", 7, "license_missing"] },
    };
    expect(parseErrorDetail(422, body)).toEqual({
      message: "Repository is not eligible.",
      reasons: ["archived", "license_missing"],
    });
  });

  it("reads FastAPI validation errors", () => {
    const body = { detail: [{ loc: ["body", "repository"], msg: "Field required" }] };
    expect(parseErrorDetail(422, body).message).toBe("Field required");
  });

  it.each([
    [500, undefined, "The service is temporarily unavailable."],
    [418, "not json", "Request failed (418)."],
    [400, { detail: { reasons: "nope" } }, "Request failed (400)."],
  ])("falls back for status %i", (status, body, message) => {
    expect(parseErrorDetail(status, body)).toEqual({ message, reasons: [] });
  });

  it("exposes status and detail on ApiError", () => {
    const error = new ApiError(404, { message: "Missing", reasons: [] });
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe("Missing");
    expect(error.status).toBe(404);
  });
});

describe("describeReason", () => {
  it("translates known reason codes", () => {
    expect(describeReason("not_organization_owned")).toContain("organization");
  });

  it("keeps unknown codes visible", () => {
    expect(describeReason("something_new")).toBe("Not eligible (something_new).");
  });
});
