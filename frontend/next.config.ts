import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Keep Turbopack scoped to the frontend app when the repository contains
    // multiple lockfiles. Without this, Next.js may infer the workspace root as
    // the repository root and expand the build/cache boundary unnecessarily.
    root: process.cwd(),
  },
};

export default nextConfig;
