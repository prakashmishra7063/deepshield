# Privacy policy & responsible-use guidance (template)

> This is a product template, not legal advice. Have it reviewed against the laws that apply to your
> deployment (e.g. GDPR/UK GDPR, CCPA/CPRA, India's DPDP Act 2023, and biometric-privacy statutes such as
> Illinois BIPA) before launch. The in-app version is at `/responsible-use`.

## 1. What the service does

DeepShield AI estimates whether images, video, audio or web pages show signs of manipulation, AI generation or
impersonation. **Results are probabilistic estimates, not proof.** A low-risk result doesn't guarantee authenticity.
A high-risk result says nothing about who created the content or why. AI-generated content is reported as
*synthetic origin* and is never labelled "fake" on that basis alone.

## 2. Data processed

| Data | Purpose | Retention |
|---|---|---|
| Uploaded files and media fetched from submitted URLs | Analysis | Originals purged after `DS_RETENTION_HOURS` (default 24h), or on deletion |
| Derived evidence (heatmaps, keyframes, spectrograms) and results | Showing and exporting findings | Until the user deletes the analysis |
| Account email, password hash (scrypt), preferences | Authentication, alerts | Life of the account |
| Cases and notes | Investigation tracking | Until deleted by the user |
| Audit log (actions, IP address, timestamps) | Security | Operator-defined (recommend 12 months) |

DeepShield does not sell data, train models on user uploads, or share content with third parties. URL scans contact
only the submitted address and the media that page references. The browser extension acts only when the user clicks.

## 3. Biometric data

The MVP performs **no** face or voice enrollment, no face recognition and no identity matching. The planned Phase 4
identity-protection features must:
* require explicit, informed, revocable consent from the person whose face or voice is enrolled, with verification
  that the enrolling user *is* that person or is legally authorized to act for them
* store reference templates separately, encrypted, with deletion on request
* compare only against content the user submits or authorized watchlists. No open-ended search or surveillance

## 4. Responsible use

Users agree to:
* analyze only content they are entitled to analyze
* not use DeepShield to identify, track, profile or harass people
* not publicly accuse anyone based solely on an automated result, and to get expert review before legal,
  financial or reputational action
* never upload child sexual abuse material. Report it to NCMEC (US), IWF (UK) or a national INHOPE hotline
* report non-consensual intimate imagery, including synthetic imagery, through StopNCII.org and the hosting platform

Operators should:
* respond to abuse reports and suspend accounts that violate these terms
* add hash-matching against known-CSAM lists (e.g. via a trusted provider) before opening uploads to the public
* restrict access to minors per local law

## 5. Fairness and accuracy

Detection accuracy varies with compression, resolution, device, lighting, skin tone, language, accent and generation
technique, and new generators can evade detection. Before a model is enabled, operators must evaluate it with
`backend/evaluation/evaluate.py` on an independent dataset annotated with subgroup attributes. They must publish
the false-positive and false-negative rates and investigate subgroup gaps. Until a model is calibrated, no
likelihood percentage is shown.

## 6. Platform terms

DeepShield uses official APIs and user-authorized access only. It doesn't bypass logins, CAPTCHAs, rate limits or
private-account restrictions, and it never reports, deletes or flags content on any platform automatically.

## 7. User rights

Users can delete any analysis (which deletes stored media and evidence), revoke API tokens, and request account
deletion and data export from the operator. Contact: *[operator contact]*.
