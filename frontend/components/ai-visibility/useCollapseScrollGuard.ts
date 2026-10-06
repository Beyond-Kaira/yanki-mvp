'use client'

import { useCallback, useEffect, useRef } from 'react'

/** Keep a bottom-scrolled viewport in place while a history card gets shorter. */
export function useCollapseScrollGuard(visible: boolean) {
  const sectionRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const preserving = useRef(false)

  const preserveScroll = useCallback(() => {
    const section = sectionRef.current
    const main = section?.closest('main')
    if (!section || !main || main.scrollTop === 0) return
    // Freeze before the animation can reduce scrollHeight. Without this floor,
    // the browser clamps scrollTop on every frame at the bottom of the page.
    section.style.minHeight = `${section.getBoundingClientRect().height}px`
    preserving.current = true
  }, [])

  useEffect(() => {
    const section = sectionRef.current
    const content = contentRef.current
    const main = section?.closest('main')
    if (!section || !content || !main) return

    function releaseUnusedSpace() {
      if (!preserving.current) return
      const naturalHeight = content!.getBoundingClientRect().height
      const gap = section!.getBoundingClientRect().height - naturalHeight
      const naturalScrollHeight = main!.scrollHeight - gap
      const needed = Math.max(0, main!.scrollTop + main!.clientHeight - naturalScrollHeight)
      if (needed > 0) {
        section!.style.minHeight = `${Math.ceil(naturalHeight + needed)}px`
      } else {
        section!.style.removeProperty('min-height')
        preserving.current = false
      }
    }

    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(releaseUnusedSpace)
    observer?.observe(content)
    content.addEventListener('transitionend', releaseUnusedSpace)
    main.addEventListener('scroll', releaseUnusedSpace, { passive: true })
    return () => {
      observer?.disconnect()
      content.removeEventListener('transitionend', releaseUnusedSpace)
      main.removeEventListener('scroll', releaseUnusedSpace)
      section.style.removeProperty('min-height')
      preserving.current = false
    }
  }, [visible])

  return { sectionRef, contentRef, preserveScroll }
}
