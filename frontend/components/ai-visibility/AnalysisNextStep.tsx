"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { IconChevron } from "@/components/shell/icons";

export default function AnalysisNextStep({
  id,
  eyebrow,
  title,
  description,
  href,
  linkLabel,
  nextStepLabel,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description: ReactNode;
  href: string;
  linkLabel: string;
  nextStepLabel: string;
}) {
  const cardRef = useRef<HTMLElement>(null);
  const linkRef = useRef<HTMLAnchorElement>(null);
  const [showSticker, setShowSticker] = useState(false);

  useEffect(() => {
    const card = cardRef.current;
    if (!card || typeof IntersectionObserver === "undefined") return;

    // AppShell scrolls its main element rather than the browser window.
    const observer = new IntersectionObserver(
      ([entry]) => {
        setShowSticker(
          !entry.isIntersecting &&
            entry.boundingClientRect.top > (entry.rootBounds?.top ?? 0),
        );
      },
      { root: card.closest("main") },
    );
    observer.observe(card);
    return () => observer.disconnect();
  }, []);

  function jumpToNextStep() {
    // Move keyboard focus to the destination before the sticker disappears.
    linkRef.current?.focus({ preventScroll: true });
    cardRef.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "end",
    });
  }

  return (
    <>
      <section
        ref={cardRef}
        id={id}
        aria-labelledby={`${id}-heading`}
        className="flex scroll-mb-8 flex-col gap-4 rounded-2xl border border-primary/20 bg-primary-soft/60 p-5 shadow-sm sm:p-6 lg:flex-row lg:items-end lg:justify-between lg:gap-6"
      >
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary-strong">
            {eyebrow}
          </p>
          <h2
            id={`${id}-heading`}
            className="mt-1 text-lg font-semibold tracking-tight text-surface-foreground sm:text-xl"
          >
            {title}
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-surface-subtle">
            {description}
          </p>
        </div>
        <Link
          ref={linkRef}
          href={href}
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 self-start rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 lg:self-auto"
        >
          {linkLabel}
          <IconChevron className="h-4 w-4" />
        </Link>
      </section>

      {showSticker ? (
        <button
          type="button"
          onClick={jumpToNextStep}
          aria-controls={id}
          aria-label={`Jump to ${nextStepLabel} at the bottom of the page`}
          className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 z-10 inline-flex max-w-[calc(100vw-2rem)] items-center gap-4 rounded-2xl border border-primary/20 bg-surface px-4 py-3 text-left shadow-lg hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 sm:bottom-6 sm:right-6"
        >
          <span>
            <span className="block text-xs text-surface-subtle">Next step</span>
            <span className="block text-sm font-semibold text-surface-foreground">
              {nextStepLabel}
            </span>
          </span>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-strong">
            <IconChevron className="h-4 w-4 rotate-90" />
          </span>
        </button>
      ) : null}
    </>
  );
}
