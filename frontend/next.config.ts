import type { NextConfig } from "next";
import path from "path";
import os from "os";

const nextConfig: NextConfig = {
  experimental: {
    // D 드라이브 느린 파일시스템 경고 해결: 개발 캐시를 로컬 임시 디렉토리로 이동
    cacheDir: path.join(os.tmpdir(), "stockauto-next-cache"),
  },
};

export default nextConfig;
