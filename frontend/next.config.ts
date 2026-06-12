import type { NextConfig } from "next";

const backendApiOrigin = process.env.BACKEND_API_ORIGIN;
const distDir = process.env.NEXT_DIST_DIR || ".next";

const nextConfig: NextConfig = {
  distDir,
  allowedDevOrigins: ["localhost", "127.0.0.1"],
  output: "standalone", // 🚀 현업 표준: 최소 파일 압축 추출 Standalone 모드 탑재
  async rewrites() {
    if (!backendApiOrigin) {
      return [];
    }

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendApiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
