"use client";

import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?:
    | "default"
    | "profit"
    | "loss"
    | "warning"
    | "info"
    | "neutral"
    | "outline";
  size?: "sm" | "md";
  dot?: boolean;
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  (
    {
      className,
      variant = "default",
      size = "md",
      dot = false,
      children,
      ...props
    },
    ref
  ) => {
    const variantStyles = {
      default: "bg-indigo-500/15 text-indigo-400 border-indigo-500/30",
      profit: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      loss: "bg-rose-500/10 text-rose-400 border-rose-500/20",
      warning: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      info: "bg-blue-500/10 text-blue-400 border-blue-500/20",
      neutral: "bg-zinc-800 text-zinc-400 border-zinc-700/50",
      outline: "bg-transparent text-slate-300 border-zinc-700",
    };

    const dotColors = {
      default: "bg-indigo-400",
      profit: "bg-emerald-400",
      loss: "bg-rose-400",
      warning: "bg-amber-400",
      info: "bg-blue-400",
      neutral: "bg-zinc-400",
      outline: "bg-slate-400",
    };

    const sizeStyles = {
      sm: "px-1.5 py-0.5 text-[10px]",
      md: "px-2.5 py-1 text-xs",
    };

    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center gap-1.5 font-bold rounded-lg border tracking-wide select-none whitespace-nowrap",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {dot && (
          <span
            className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotColors[variant])}
          />
        )}
        {children}
      </span>
    );
  }
);

Badge.displayName = "Badge";
