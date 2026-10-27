const apiUrl = process.env.API_URL ?? "http://127.0.0.1:4000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Compression would buffer the server-sent event stream of a running job.
  compress: false,
  // The browser only ever talks to this origin; Next forwards /api to Express,
  // which listens on 127.0.0.1 only.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
