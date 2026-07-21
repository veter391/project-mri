import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { CodePanel, Prompt, Comment } from "@/components/ui/code-panel";
import { DocH2, DocP, DocList, DocLi, IC, DocNote } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Self-hosting — Run MRI on Your Own Machine",
  description:
    "Run the full MRI dashboard and backend locally. Loopback is frictionless; exposing to a network fails closed without auth by design. Your code never leaves your machine.",
  alternates: { canonical: "/docs/self-hosting" },
};

export default function SelfHostingPage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · self-hosting"
        title="Self-host in four commands."
        lede="MRI is self-hosted by default — the whole experience runs on your own machine. Install, initialize, serve, scan. No account, no telemetry, no cloud dependency."
      />
      <Section>
        <Container narrow>
          <DocH2>The walkthrough</DocH2>
          <CodePanel
            title="quickstart.sh"
            copyText={`pipx install ${SITE.pkg}\nmri init\nmri serve\nmri scan .`}
            className="mt-4"
          >
            <Comment># 1 · install</Comment>
            {"\n"}
            <Prompt />pipx install {SITE.pkg}
            {"\n\n"}
            <Comment># 2 · create your admin user + local database (idempotent)</Comment>
            {"\n"}
            <Prompt />mri init
            {"\n\n"}
            <Comment># 3 · serve on loopback, then open the dashboard</Comment>
            {"\n"}
            <Prompt />mri serve
            {"\n"}
            <Comment># → http://localhost:{SITE.port}/dashboard/</Comment>
            {"\n\n"}
            <Comment># 4 · scan your code</Comment>
            {"\n"}
            <Prompt />mri scan .
          </CodePanel>

          <DocH2>The local-first guarantee</DocH2>
          <DocList>
            <DocLi>Your code never leaves your machine — no SaaS, no account, no phone-home.</DocLi>
            <DocLi>Zero telemetry, proven by a build-failing egress test, not merely asserted.</DocLi>
            <DocLi>Session content is off by default; only metadata is stored unless you opt in.</DocLi>
          </DocList>

          <DocH2>Exposing it on a network</DocH2>
          <DocP>
            <IC>mri serve</IC> binds to <IC>127.0.0.1:{SITE.port}</IC> by default,
            where no auth is needed. To reach it from another host, bind to all
            interfaces behind a reverse proxy — but configure auth first.
          </DocP>
          <DocNote tone="warn">
            <strong>Fail-closed by design (ADR-013).</strong> Binding to a
            non-loopback interface without configured auth makes the server refuse
            to start, rather than serving in the open. Set an API key or create a
            dashboard user with <IC>mri init</IC> first. Only{" "}
            <IC>MRI_ALLOW_INSECURE=1</IC> overrides this — do not use it on an
            untrusted network.
          </DocNote>
          <CodePanel
            title="expose.sh"
            copyText="MRI_HOST=0.0.0.0 mri serve"
            className="mt-4"
          >
            <Comment># requires auth configured, or it refuses to start</Comment>
            {"\n"}
            <Prompt />MRI_HOST=0.0.0.0 mri serve
          </CodePanel>

          <div className="mt-8">
            <ButtonLink href={`${SITE.github}/blob/main/docs/INSTALL.md`} variant="secondary">
              Full install matrix
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
