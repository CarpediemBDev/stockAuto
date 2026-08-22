"use client";

import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { surfaceStyles } from "@/lib/theme";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, leftIcon, rightIcon, disabled, ...props }, ref) => {
    return (
      <div className="w-full relative">
        {leftIcon && (
          <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none flex items-center justify-center">
            {leftIcon}
          </div>
        )}
        <input
          ref={ref}
          disabled={disabled}
          className={cn(
            // 입력 표면 스타일의 SSOT는 lib/theme.ts의 surfaceStyles.input이다.
            // 좌우 패딩은 아이콘 유무에 따라 달라지므로 surfaceStyles에 넣지 않고 여기서 합성한다.
            surfaceStyles.input,
            "disabled:opacity-50 disabled:cursor-not-allowed",
            // px-4와 pl-10을 함께 넘기면 twMerge가 뒤에 온 px-4로 pl-10을 덮어써
            // 아이콘 위로 텍스트가 겹친다. 좌/우 패딩을 분리해서 충돌을 없앤다.
            leftIcon ? "pl-10" : "pl-4",
            rightIcon ? "pr-10" : "pr-4",
            error && "border-rose-500 focus:ring-rose-500 focus:border-rose-500",
            className
          )}
          {...props}
        />
        {rightIcon && (
          <div className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none flex items-center justify-center">
            {rightIcon}
          </div>
        )}
        {error && <p className="mt-1 text-xs text-rose-400">{error}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
