import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["@xlfoundry/auth-sdk-web"],
};

export default nextConfig;
