import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Served as plain static files by Nginx (no Node process on the 4GB VPS).
  output: "export",
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
