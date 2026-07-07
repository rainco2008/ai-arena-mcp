const apiBase = process.env.CONTENTPILOT_API_URL || "http://127.0.0.1:8081";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/v1/:path*", destination: `${apiBase}/v1/:path*` },
      { source: "/api/health", destination: `${apiBase}/api/health` },
      { source: "/api/runtime/:path*", destination: `${apiBase}/api/runtime/:path*` },
      { source: "/api/test", destination: `${apiBase}/api/test` },
      { source: "/api/scrape", destination: `${apiBase}/api/scrape` },
      {
        source: "/api/content-factory/:path*",
        destination: `${apiBase}/api/content-factory/:path*`,
      },
    ];
  },
};

export default nextConfig;
