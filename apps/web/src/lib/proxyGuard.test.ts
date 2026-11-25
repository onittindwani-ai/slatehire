import assert from "node:assert/strict";
import { test } from "node:test";
import { bodyAllowed, readLimited, safePath } from "./proxyGuard.ts";

test("ordinary paths pass and the private ones never do", () => {
  assert.equal(safePath(["applications", "12"]), "applications/12");
  assert.equal(safePath(["applicants", "file"]), "applicants/file");
  assert.equal(safePath(["auth", "me"]), "auth/me");
  for (const bad of [["auth", "login"], ["Auth", "login"], ["auth", "login", "x"], ["webhooks", "application"], ["tools", "x"]]) assert.equal(safePath(bad), null, bad.join("/"));
});

test("dot segments and encoded tricks are refused", () => {
  for (const bad of [[".", "auth", "login"], ["..", "health"], ["applications", ".."], ["a/b"], ["a\\b"], ["%2e"], ["%2e%2e"], ["applications", "1%2f2"], ["a\u0000b"], [""], []]) {
    assert.equal(safePath(bad), null, JSON.stringify(bad));
  }
});

test("a declared length over the limit is refused before reading", () => {
  assert.equal(bodyAllowed(null, 10), true);
  assert.equal(bodyAllowed("10", 10), true);
  assert.equal(bodyAllowed("11", 10), false);
  assert.equal(bodyAllowed("abc", 10), false);
  assert.equal(bodyAllowed("-5", 10), false);
});

test("a body is cut off at the limit even when it did not say how long it is", async () => {
  const big = new Request("http://x.test/", { method: "POST", body: "x".repeat(50) });
  big.headers.delete("content-length");
  assert.equal(await readLimited(big, 10), null);
  const small = new Request("http://x.test/", { method: "POST", body: "hello" });
  const got = await readLimited(small, 10);
  assert.equal(new TextDecoder().decode(got!), "hello");
});
