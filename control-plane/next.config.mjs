/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  // The control plane is a read-only surface (D-171 §2.1): it holds no
  // credentials and performs no server-side writes. Outbound calls are made
  // only through explicit, allow-listed server actions added in later phases.
  poweredByHeader: false,
  // NOTE: the `eslint` key was removed in Next 16 (lint runs directly via
  // `npm run lint`, which lints `src` and `scripts` through eslint.config.mjs).
};

export default nextConfig;
