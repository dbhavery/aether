import type { NextConfig } from "next";

/**
 * Next.js config for Aether.
 *
 * `output: 'export'` emits a fully static bundle into `out/` during `next build`,
 * which pywebview loads as `file://.../out/index.html`. No server runtime is
 * allowed under this mode — every route must be statically reachable and must
 * avoid `fetch` in server components, route handlers, or middleware.
 *
 * `images.unoptimized` disables the optimizer because we have no image server.
 * `trailingSlash` makes `out/foo/index.html` resolve correctly under `file://`.
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  typescript: {
    // Strict checking is enforced via `npm run typecheck` in CI.
    // `next build` will still fail on type errors by default.
    ignoreBuildErrors: false,
  },
  eslint: {
    ignoreDuringBuilds: false,
  },
};

export default nextConfig;
