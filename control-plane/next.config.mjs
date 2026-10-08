/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  // Container contract (D-171): the runtime image ships only the traced
  // server and its dependencies (`.next/standalone`) instead of the whole
  // `node_modules` tree, which is what keeps the image near 100 MB rather
  // than 500 MB+. See docs/deployment/control-plane-container-spec.md.
  output: 'standalone',
  // The control plane is a read-only surface (D-171 §2.1): it holds no
  // credentials and performs no server-side writes. Outbound calls are made
  // only through explicit, allow-listed server actions added in later phases.
  poweredByHeader: false,
  // NOTE: the `eslint` key was removed in Next 16 (lint runs directly via
  // `npm run lint`, which lints `src` and `scripts` through eslint.config.mjs).
};

export default nextConfig;
