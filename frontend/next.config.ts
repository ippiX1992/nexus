import type { NextConfig } from "next";

// Preview/dev proxy: the browser always calls the SAME origin it loaded the
// page from (relative /api/v1), and Next forwards those calls to the FastAPI
// backend. This makes the app reachable via localhost, 127.0.0.1, a LAN IP, or
// a tunnel without baking an absolute API host into the client bundle. The
// backend origin is taken from BACKEND_ORIGIN (defaults to the local preview).
const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.86.64", "100.97.212.89"],
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendOrigin}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
