"use client";

import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { surfaceStyles } from "@/lib/theme";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "highlight" | "interactive";
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = "default", ...props }, ref) => {
    // 표면 스타일 문자열의 SSOT는 lib/theme.ts의 surfaceStyles다. 여기서 다시 적지 않는다.
    const variantStyles = {
      default: surfaceStyles.card,
      subtle: surfaceStyles.cardSubtle,
      highlight: surfaceStyles.cardHighlight,
      interactive: cn(
        surfaceStyles.card,
        "hover:border-zinc-700 hover:scale-[1.01] transition-all duration-300"
      ),
    };

    return (
      <div
        ref={ref}
        className={cn(variantStyles[variant], "relative overflow-hidden", className)}
        {...props}
      />
    );
  }
);

Card.displayName = "Card";

export const CardHeader = forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("p-5 pb-3 flex flex-col space-y-1.5", className)}
    {...props}
  />
));

CardHeader.displayName = "CardHeader";

export const CardTitle = forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      "text-lg font-bold text-white tracking-tight leading-none flex items-center gap-2",
      className
    )}
    {...props}
  />
));

CardTitle.displayName = "CardTitle";

export const CardDescription = forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-xs text-zinc-400 font-medium", className)}
    {...props}
  />
));

CardDescription.displayName = "CardDescription";

export const CardContent = forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-5 pt-0", className)} {...props} />
));

CardContent.displayName = "CardContent";

export const CardFooter = forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("p-5 pt-0 flex items-center justify-between border-t border-zinc-800/60 mt-4", className)}
    {...props}
  />
));

CardFooter.displayName = "CardFooter";
