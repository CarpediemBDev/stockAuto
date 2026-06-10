"use client";

import React, { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api/v1';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setAuth, clearAuth, setInitialized, isInitialized } = useAuthStore();

  useEffect(() => {
    if (isInitialized) return;

    const initAuth = async () => {
      try {
        const localRefreshToken = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null;
        if (!localRefreshToken) {
          clearAuth();
          return;
        }

        const response = await axios.post(`${API_BASE}/auth/refresh`, {
          refresh_token: localRefreshToken
        });
        const newToken = response.data.data ? response.data.data.access_token : response.data.access_token;
        const newUsername = response.data.data ? response.data.data.username : response.data.username;
        const newRefreshToken = response.data.data ? response.data.data.refresh_token : response.data.refresh_token;
        setAuth(newToken, newUsername, newRefreshToken || localRefreshToken);
      } catch {
        clearAuth();
      } finally {
        setInitialized(true);
      }
    };

    initAuth();
  }, [isInitialized, setAuth, clearAuth, setInitialized]);

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
