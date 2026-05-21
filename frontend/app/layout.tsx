import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { NavBar } from "@/components/NavBar";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

import { EnvironmentBadge } from "@/components/EnvironmentBadge";

export const metadata: Metadata = {
  title: "StockAuto - 자동매매 대시보드",
  description: "글로벌 우량주 퀀트 시그널 스캐너 & 자동매매 시스템",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-black text-white relative">
        {/* 글로벌 상단 네비게이션 바 */}
        <NavBar />
        
        {/* 메인 컨텐츠 영역 */}
        <div className="flex-1 w-full">
          {children}
        </div>
        
        {/* 환경 식별 뱃지 (좌측 하단 띠) */}
        <EnvironmentBadge />

        {/* 토스트 알림 컨테이너 */}
        <Toaster richColors position="bottom-right" theme="dark" closeButton />
      </body>
    </html>
  );
}
