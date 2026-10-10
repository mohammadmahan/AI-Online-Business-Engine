/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  /**
   * D-172 Phase 2 — the merchant admin holds NO credential of its own: the
   * canonical connection string is read from the environment at request time
   * and the surface fails closed when it is absent (D-045/D-124, D-171 §2.2).
   * `output: 'standalone'` keeps the eventual container contract identical to
   * the control plane's (docs/deployment/control-plane-container-spec.md).
   */
  output: 'standalone',
  poweredByHeader: false,
  // Server Actions are the only write path; their body limit is explicit
  // rather than inherited (the packing-slip and product payloads are small).
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
};

export default nextConfig;
