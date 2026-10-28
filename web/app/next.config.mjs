const apiUrl = process.env.API_URL ?? "http://127.0.0.1:4000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // A separate folder lets a dev server (for example the e2e tests) run next to a production build.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Compression would buffer the server-sent event stream of a running job.
  compress: false,
  // A PDF export renders a whole report; the default proxy timeout is 30 seconds.
  experimental: { proxyTimeout: 180_000 },
  // The browser only ever talks to this origin; Next forwards /api to Express,
  // which listens on 127.0.0.1 only.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
