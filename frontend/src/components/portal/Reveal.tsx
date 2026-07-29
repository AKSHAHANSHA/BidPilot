import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Reveals its children when they first scroll into view.
 *
 * One IntersectionObserver per element rather than a scroll listener: the browser does the
 * intersection maths off the main thread, and there is no work at all while the page is idle.
 * The observer disconnects after firing — these are entrances, not a state that toggles back
 * when the user scrolls up, which would make a long page feel like it was blinking.
 *
 * If the API is unavailable or the effect never runs, the element is left visible. A decorative
 * entrance must never be the reason content cannot be read.
 */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  /** Stagger, in milliseconds. Keep small — a long cascade reads as slow, not considered. */
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          setVisible(true);
          observer.disconnect();
        }
      },
      // A negative bottom margin holds the entrance back until the element is properly on
      // screen, so it is not already finished by the time the reader looks at it.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`portal-reveal ${visible ? "is-visible" : ""} ${className}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}
