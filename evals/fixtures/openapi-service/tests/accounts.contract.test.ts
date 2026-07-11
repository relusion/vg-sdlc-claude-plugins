import { describe, expect, it } from "vitest";
import { canLogin, serializeAccount } from "../src/routes/accounts";

describe("account contract", () => {
  it("returns only documented status values", () => {
    expect(serializeAccount({
      id: "acct_1",
      email: "user@example.com",
      status: "disabled",
    }).status).toBe("disabled");
  });

  it("blocks login for disabled accounts", () => {
    expect(canLogin("disabled")).toBe(false);
  });
});
