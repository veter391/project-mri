import NextLink from "next/link";
import type { ComponentProps } from "react";

/**
 * Link wrapper with prefetch disabled. In a static export there are no RSC
 * segment payloads to prefetch, so Next's default viewport prefetch fires 404s
 * for `__next.<route>.__PAGE__.txt`. Disabling prefetch keeps navigation working
 * (static HTML) while eliminating that request noise.
 */
export function Link(props: ComponentProps<typeof NextLink>) {
  return <NextLink prefetch={false} {...props} />;
}
