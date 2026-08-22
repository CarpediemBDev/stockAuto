"use client";

import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { surfaceStyles } from "@/lib/theme";
import { X } from "lucide-react";

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl" | "2xl" | "4xl" | "5xl" | "full";
  className?: string;
  showCloseButton?: boolean;
}

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  maxWidth = "4xl",
  className,
  showCloseButton = true,
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    // ESC 키로 모달 닫기
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    // 모달 오픈 시 배경 스크롤 차단
    const originalStyle = window.getComputedStyle(document.body).overflow;
    document.body.style.overflow = "hidden";

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalStyle;
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const maxWidthStyles = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-lg",
    xl: "max-w-xl",
    "2xl": "max-w-2xl",
    "4xl": "max-w-4xl",
    "5xl": "max-w-5xl",
    full: "max-w-[95vw]",
  };

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      className={surfaceStyles.modalOverlay}
    >
      <div
        className={cn(
          // 모달 표면 스타일의 SSOT는 lib/theme.ts의 surfaceStyles다. 폭만 여기서 합성한다.
          surfaceStyles.modalContent,
          maxWidthStyles[maxWidth],
          className
        )}
      >
        {/* 헤더 영역 (타이틀 또는 닫기 버튼이 있을 때) */}
        {(title || showCloseButton) && (
          <div className="flex items-center justify-between pb-4 border-b border-zinc-800/80 mb-4 shrink-0">
            <div>
              {typeof title === "string" ? (
                <h3 className="text-lg font-bold text-white tracking-tight">{title}</h3>
              ) : (
                title
              )}
              {description && (
                <p className="text-xs text-zinc-400 mt-1 font-medium">{description}</p>
              )}
            </div>
            {showCloseButton && (
              <button
                onClick={onClose}
                aria-label="Close modal"
                className="w-8 h-8 rounded-full bg-zinc-800/60 hover:bg-zinc-700 text-zinc-400 hover:text-white flex items-center justify-center transition-all duration-200 active:scale-95 cursor-pointer"
              >
                <X size={16} />
              </button>
            )}
          </div>
        )}

        {/* 바디 영역 (스크롤 가능) */}
        <div className="overflow-y-auto custom-scrollbar flex-1 pr-1">
          {children}
        </div>
      </div>
    </div>
  );
}
