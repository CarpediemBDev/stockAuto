"use client";

import React, { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { refreshAuthSession } from '../lib/api';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { clearAuth, setInitialized, isInitialized } = useAuthStore();

  useEffect(() => {
    if (isInitialized) return;

    const initAuth = async () => {
      try {
        await refreshAuthSession();
      } catch {
        clearAuth();
      } finally {
        setInitialized(true);
      }
    };

    initAuth();
  }, [isInitialized, clearAuth, setInitialized]);

  // 인증 상태 확인 전에는 화면을 그리지 않거나 스켈레톤을 표시하여
  // 로그인 풀림 깜빡임 현상(Flickering)을 방지합니다.
  if (!isInitialized) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-white/50">
        <span className="animate-pulse">Loading Application...</span>
      </div>
    );
  }

  return <>{children}</>;
}
