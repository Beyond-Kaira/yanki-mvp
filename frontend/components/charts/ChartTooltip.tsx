"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { createPortal } from "react-dom";

interface ChartTooltipProps {
  // The evidence sentence — always the same fact shown visually, spelled out.
  content: string;
  children: ReactNode;
  // Applied to the OUTER wrapper, not a nested span, so a percentage-width
  // child (a stacked-share segment) resolves against the real flex row
  // instead of against an auto-sized wrapper two levels up.
  style?: CSSProperties;
  className?: string;
}

// Reachable by hover AND keyboard focus (brandkit v2 §7: nothing here may
// depend on a mouse). Wraps a chart cell/bar; the tooltip text is also always
// present for a screen reader via aria-describedby, whether or not it is
// visible.
export default function ChartTooltip({
  content,
  children,
  style,
  className,
}: ChartTooltipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const anchorRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);
  const id = useId();

  useLayoutEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const anchor = anchorRef.current?.getBoundingClientRect();
      const tooltip = tooltipRef.current?.getBoundingClientRect();
      if (!anchor || !tooltip) return;

      const margin = 8;
      const left = Math.max(
        margin,
        Math.min(
          anchor.left + anchor.width / 2 - tooltip.width / 2,
          window.innerWidth - tooltip.width - margin,
        ),
      );
      const above = anchor.top - tooltip.height - margin;
      const top =
        above >= margin
          ? above
          : Math.max(
              margin,
              Math.min(
                anchor.bottom + margin,
                window.innerHeight - tooltip.height - margin,
              ),
            );
      setPosition({ left, top });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, content]);

  return (
    <span
      ref={anchorRef}
      className={`relative inline-flex ${className ?? ""}`}
      style={style}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span
        aria-describedby={id}
        tabIndex={0}
        className="flex w-full outline-none"
      >
        {children}
      </span>
      <span id={id} className="sr-only">
        {content}
      </span>
      {open &&
        createPortal(
          <span
            ref={tooltipRef}
            role="tooltip"
            aria-hidden="true"
            className="pointer-events-none fixed z-50 w-max max-w-[16rem] rounded-md bg-ink px-2.5 py-1.5 text-xs text-ink-foreground shadow-sm"
            style={{
              left: position?.left ?? 0,
              top: position?.top ?? 0,
              visibility: position ? "visible" : "hidden",
            }}
          >
            {content}
          </span>,
          document.body,
        )}
    </span>
  );
}
