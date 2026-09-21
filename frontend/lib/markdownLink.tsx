import type { AnchorHTMLAttributes, ReactNode } from "react";

// A ReactMarkdown `a` renderer with the given classes applied directly on the
// element. Bypassing the typography plugin's `prose-a:` modifier here is
// deliberate: those modifiers and a wrapping `[&_*]:text-inherit` utility
// (used to make body text inherit its bubble's color) resolve to the same
// specificity in the same Tailwind layer, so which one wins is effectively
// undefined — in practice it silently lost, and links rendered in the
// inherited body color instead of their intended one. A class applied right
// on the element here has nothing of equal precedence left to compete with.
export function markdownLinkComponent(className: string) {
  return function MarkdownLink({ href, children }: AnchorHTMLAttributes<HTMLAnchorElement> & { children?: ReactNode }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
      </a>
    );
  };
}
