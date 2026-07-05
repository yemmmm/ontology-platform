// Lightweight stand-in icons for cases where lucide is unavailable or
// we want a small custom glyph in semantic components.
import type { SVGProps } from "react";

export function InfoCircledIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="1em"
      height="1em"
      viewBox="0 0 15 15"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <path
        d="M7.499 1.5a6 6 0 110 12 6 6 0 010-12zM7.5 4a.625.625 0 100 1.25.625.625 0 000-1.25zm.5 3.25a.5.5 0 00-1 0v3.5a.5.5 0 001 0v-3.5z"
        fill="currentColor"
      />
    </svg>
  );
}
