import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  experimental: {
    allowedDevOrigins: ["127.0.0.1:3000", "localhost:3000"]
  }
};

export default nextConfig;
