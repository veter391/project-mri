import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge about our custom theme tokens. Without this it cannot tell
// that `text-body-sm` is a font-size and `text-void` is a text-color, treats them
// as the same `text-*` group, and silently drops one when both appear — which
// broke, e.g., the primary button's `text-void` (fell back to body color on amber).
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "display",
            "h1",
            "h2",
            "h3",
            "body-lg",
            "body",
            "body-sm",
            "caption",
            "mono-lg",
            "mono",
            "mono-sm",
          ],
        },
      ],
      "text-color": [
        {
          text: [
            "void",
            "surface",
            "raised",
            "inset",
            "hairline",
            "hairline-strong",
            "accent",
            "accent-dim",
            "primary",
            "secondary",
            "mute",
            "dim",
            "risk-critical",
            "risk-high",
            "risk-medium",
            "risk-low",
            "risk-none",
            "author-human",
            "author-ai",
            "author-mixed",
          ],
        },
      ],
    },
  },
});

/** Merge conditional class names, resolving Tailwind conflicts last-wins. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
