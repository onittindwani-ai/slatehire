import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const config: NextConfig = {
  transpilePackages: ["@sendora/ui-kit"],
  reactStrictMode: true,
  poweredByHeader: false,
  // Only Docker builds ask for the standalone folder (NEXT_STANDALONE=1); a normal build works with `next start`.
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  outputFileTracingRoot: fileURLToPath(new URL("../../", import.meta.url)),
};

export default config;
