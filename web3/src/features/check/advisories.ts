/**
 * Published advisories in the scam-pattern corpus, quoted from
 * nlp_rag/corpus/anchors/seed_anchors.yaml (title and source agency only).
 * Shown as "patterns it recognises", never as endorsements by these agencies.
 */
export const ADVISORIES: { title: string; agency: string }[] = [
  { title: 'Digital arrest by fake law enforcement', agency: 'PIB · Ministry of Home Affairs' },
  { title: 'AI-driven impersonation of relatives', agency: 'PIB · Ministry of Home Affairs' },
  { title: 'Cloning of voice identity for financial fraud', agency: 'PIB · Ministry of Home Affairs' },
  { title: 'Frauds in the name of KYC updation', agency: 'Reserve Bank of India' },
  { title: 'Electricity KYC update scam', agency: 'Department of Telecommunications' },
  { title: 'Threats of connection disconnection', agency: 'Department of Telecommunications' },
  { title: 'Frauds in the name of Indian Customs', agency: 'CBIC' },
  { title: 'Calls impersonating TRAI', agency: 'TRAI' },
  { title: 'Fictitious lottery and prize offers', agency: 'Reserve Bank of India' },
  { title: 'Tampered QR codes', agency: 'I4C · Ministry of Home Affairs' },
];
