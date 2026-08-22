"use client";

import React from "react";
import { cn } from "@/lib/utils";

export interface SegmentOption<T extends string = string> {
  value: T;
  label: React.ReactNode;
}

export interface SegmentedControlProps<T extends string = string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  size?: "sm" | "md";
}

export function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
  className,
  size = "md",
}: SegmentedControlProps<T>) {
  const sizeStyles = {
    sm: "p-0.5 text-xs",
    md: "p-1 text-xs",
  };

  const itemSizeStyles = {
    sm: "px-2.5 py-1",
    md: "px-3 py-1.5",
  };

  return (
    <div
      className={cn(
        "flex bg-surface-card-subtle border border-zinc-800 rounded-xl shadow-inner select-none",
        sizeStyles[size],
        className
      )}
    >
      {options.map((option) => {
        const isSelected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-lg font-bold transition-all duration-200 cursor-pointer flex items-center justify-center gap-1.5",
              itemSizeStyles[size],
              isSelected
                ? "bg-zinc-800 text-white shadow-md border border-zinc-700/50"
                : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
