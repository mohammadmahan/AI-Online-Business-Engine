/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV !== 'production';
const contentSecurityPolicy = [
  "default-src 'self'",
  // Next.js hydration uses inline bootstrap scripts. 'unsafe-eval' is limited
  // to the development compiler; production keeps it out of the policy.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  // The image picker fetches its own compressed data: preview before upload.
  "connect-src 'self' ws: wss: data:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join('; ');

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
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: contentSecurityPolicy },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=()',
          },
        ],
      },
    ];
  },
  // The supported forwarded dev host is loopback-only. Next's default
  // cross-origin guard blocks HMR/dev-resource requests from 127.0.0.1 as
  // "cross-origin" when the container is reached through a forwarded port,
  // which also prevents client hydration. Allow only that hostname for
  // development; production behaviour and bundle contents are unaffected.
  allowedDevOrigins: ['127.0.0.1'],
  // Server Actions are the only write path; their body limit is explicit
  // rather than inherited (the packing-slip and product payloads are small).
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
};

export default nextConfig;
