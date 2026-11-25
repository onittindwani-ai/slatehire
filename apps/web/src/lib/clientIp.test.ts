import assert from "node:assert/strict";
import { test } from "node:test";
import { lastHop } from "./clientIp.ts";

test("only the last address of x-forwarded-for is trusted", () => {
  assert.equal(lastHop("203.0.113.9"), "203.0.113.9");
  assert.equal(lastHop("10.1.1.1, 198.51.100.7"), "198.51.100.7"); // the first entry was typed by the visitor
  assert.equal(lastHop(" a , b ,c "), "c");
  assert.equal(lastHop(""), "");
  assert.equal(lastHop(null), "");
});
