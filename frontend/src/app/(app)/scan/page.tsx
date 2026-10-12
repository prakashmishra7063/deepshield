import { PageHeader } from "@/components/AppShell";
import QuickScan from "@/components/QuickScan";

export default function ScanPage() {
  return (
    <>
      <PageHeader
        title="Scan content"
        subtitle="Upload a file or paste a URL. Analysis runs in the background, and you can leave this page at any time."
      />
      <QuickScan large />
      <div className="mt-6 grid gap-4 text-sm text-muted md:grid-cols-3">
        <p>
          <strong className="text-text">What we check.</strong> File metadata, C2PA Content Credentials, compression
          forensics, video keyframes and temporal consistency, audio spectra, and web-page impersonation patterns.
        </p>
        <p>
          <strong className="text-text">What we don&apos;t claim.</strong> Results are estimates. AI-generated
          doesn&apos;t mean malicious, and &quot;no indicators&quot; doesn&apos;t mean authentic.
        </p>
        <p>
          <strong className="text-text">Your data.</strong> Original files are kept apart from evidence images, never
          executed, and purged automatically after the retention window (24 hours by default).
        </p>
      </div>
    </>
  );
}
