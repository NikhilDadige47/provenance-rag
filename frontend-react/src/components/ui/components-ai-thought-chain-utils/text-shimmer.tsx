import React from "react";
import { cn } from "@/lib/utils";

interface ShimmerTextProps {
  text: string;
  className?: string;
}

export function ShimmerText({ text, className }: ShimmerTextProps) {
  return (
    <span
      className={cn(
        "inline-block bg-[linear-gradient(110deg,#93c5fd,45%,#1d4ed8,55%,#93c5fd)] [background-size:200%_100%] bg-clip-text text-transparent animate-shimmer",
        className,
      )}
    >
      {text}
    </span>
  );
}
