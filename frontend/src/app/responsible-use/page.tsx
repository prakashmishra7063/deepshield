import Link from "next/link";

export const metadata = { title: "Privacy & Responsible Use · DeepShield AI" };

const sections: [string, string[]][] = [
  [
    "What DeepShield does and doesn't do",
    [
      "DeepShield estimates whether media shows signs of manipulation or AI generation. Every result is a probabilistic estimate, not proof.",
      "A low-risk result does not guarantee authenticity. A high-risk result says nothing about who made the content or why.",
      "AI-generated content is not automatically labelled “fake”. Synthetic origin is reported separately from manipulation risk.",
      "When a detector or integration isn't configured, the result says so. DeepShield never shows simulated or placeholder detections.",
    ],
  ],
  [
    "Data we process",
    [
      "Files you upload and media fetched from URLs you submit, plus the analysis results and evidence derived from them.",
      "Original media is stored separately from derived evidence and deleted automatically after the retention window (24 hours by default, set by your administrator). You can delete any analysis at any time.",
      "Your account email, a salted password hash, alert preferences, investigation notes, and an audit log of security-relevant actions.",
      "We do not sell data, train models on your uploads, or share content with third parties. URL fetching contacts only the address you submitted (and media it references).",
    ],
  ],
  [
    "Responsible use",
    [
      "Only analyze content you are entitled to analyze. Do not use DeepShield to identify, track or surveil people.",
      "DeepShield does not perform face recognition against identity databases, and does not provide covert monitoring.",
      "Treat findings with care. Don't publicly accuse anyone based on an automated result. Get expert forensic review before legal, financial or reputational action.",
      "Never upload child sexual abuse material. If you encounter it, report it to NCMEC (US), the IWF (UK) or your national hotline, not to DeepShield.",
      "For non-consensual intimate imagery, including synthetic imagery, use StopNCII.org and the reporting tools of the platform hosting it.",
    ],
  ],
  [
    "Platform access",
    [
      "DeepShield uses official APIs and user-authorized access only. It does not bypass logins, CAPTCHAs, rate limits or private-account settings.",
      "Nothing is reported, deleted or flagged on any platform automatically. You decide what to do with a finding.",
    ],
  ],
  [
    "Known limitations & fairness",
    [
      "Accuracy varies with compression, resolution, lighting, device, language, accent and generation technique. New generators can evade detection.",
      "Models must be evaluated across demographic and capture-condition subgroups before they're enabled (see the evaluation pipeline). Until then, no likelihood percentage is shown.",
    ],
  ],
];

export default function ResponsibleUse() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <Link href="/" className="text-sm text-accent">
        ← DeepShield AI
      </Link>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Privacy &amp; Responsible Use</h1>
      <p className="mt-2 text-muted">See Beyond the Fake. Protect What&apos;s Real, responsibly.</p>
      {sections.map(([title, items]) => (
        <section key={title} className="mt-8">
          <h2 className="text-lg font-semibold">{title}</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed">
            {items.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </section>
      ))}
      <p className="mt-10 text-xs text-muted">
        This page is a product template. Operators must have it reviewed against the privacy and data-protection laws
        that apply to them (e.g. GDPR, CCPA, India&apos;s DPDP Act, and biometric-privacy laws) before going live.
      </p>
    </main>
  );
}
