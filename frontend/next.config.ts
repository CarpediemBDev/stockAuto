import type { NextConfig } from "next";
import path from "path";

const backendApiOrigin = process.env.BACKEND_API_ORIGIN;
const distDir = process.env.NEXT_DIST_DIR || ".next";

// 번역 딕셔너리(locales/)가 frontend/ 바깥, 저장소 루트에 있다.
// Turbopack은 기본적으로 프로젝트 루트 밖 모듈을 해석하지 않으므로
// 워크스페이스 루트를 명시해 i18n.ts의 '../locales/*.json' 정적 import를 허용한다.
const workspaceRoot = path.resolve(process.cwd(), "..");

const nextConfig: NextConfig = {
  distDir,
  output: "standalone", // 🚀 현업 표준: 최소 파일 압축 추출 Standalone 모드 탑재
  turbopack: { root: workspaceRoot },
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

import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./i18n.ts');

export default withNextIntl(nextConfig);
