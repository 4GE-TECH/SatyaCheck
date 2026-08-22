import { useState, useRef } from "react";
import { GlassButton } from "@/components/ui/glass-button";
import { CheckCircle2 } from "lucide-react";

interface EnrolledMember {
  id: string;
  name: string;
  relation: string;
  phone: string;
  enrolledDate: string;
  secretQuestion: string;
}

const INITIAL_MEMBERS: EnrolledMember[] = [
  {
    id: "p_rahul_01",
    name: "Rahul Verma",
    relation: "Son",
    phone: "+91 98112 04829",
    enrolledDate: "Aug 15, 2026",
    secretQuestion: "What is our hometown dog's name?",
  },
  {
    id: "p_priya_02",
    name: "Priya Sharma",
    relation: "Daughter",
    phone: "+91 99201 83721",
    enrolledDate: "Aug 18, 2026",
    secretQuestion: "What school did you go to?",
  },
];

export default function EnrollPage() {
  const [members, setMembers] = useState<EnrolledMember[]>(INITIAL_MEMBERS);
  const [name, setName] = useState("");
  const [relation, setRelation] = useState("Son");
  const [phone, setPhone] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleEnroll = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !relation) return;

    const newMember: EnrolledMember = {
      id: `p_${name.toLowerCase().replace(/\s+/g, "_")}_${Date.now().toString().slice(-2)}`,
      name,
      relation,
      phone: phone || "+91 98765 XXXXX",
      enrolledDate: "Today",
      secretQuestion: question || "None configured",
    };

    setMembers([newMember, ...members]);
    setIsSuccess(true);
    setName("");
    setPhone("");
    setQuestion("");
    setAnswer("");
    setFile(null);
    setTimeout(() => setIsSuccess(false), 5000);
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-[var(--text-primary)] tracking-tight font-mono">
          My Family Voice Vault
        </h1>
        <p className="text-sm sm:text-base text-[var(--text-secondary)] mt-1">
          Save a 30-second voice recording of your family. If you receive a suspicious emergency call, SatyaCheck verifies if the voice is authentic.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Enrollment Form (5 Cols) */}
        <div className="lg:col-span-5">
          <div className="sec-card p-6 space-y-4">
            <h2 className="text-base font-bold text-[var(--text-primary)] pb-3 border-b border-[var(--border-subtle)] flex items-center gap-2 font-mono">
              <span>Add a Family Member</span>
            </h2>

            {isSuccess && (
              <div className="p-3.5 rounded-lg bg-[var(--success-bg)] border border-[var(--success-border)] text-xs text-[var(--success-text)] font-semibold flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>Voice recording saved safely to your local vault!</span>
              </div>
            )}

            <form onSubmit={handleEnroll} className="space-y-3.5 text-sm">
              <div>
                <label className="block text-xs font-semibold text-[var(--text-secondary)] uppercase mb-1 font-mono">
                  Full Name *
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Rahul, Mother, Papa"
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-primary)] text-sm focus:border-[var(--accent)] outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[var(--text-secondary)] uppercase mb-1 font-mono">
                    Relationship *
                  </label>
                  <select
                    value={relation}
                    onChange={(e) => setRelation(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-primary)] text-sm focus:border-[var(--accent)] outline-none"
                  >
                    <option value="Son">Son</option>
                    <option value="Daughter">Daughter</option>
                    <option value="Mother">Mother</option>
                    <option value="Father">Father</option>
                    <option value="Spouse">Spouse</option>
                    <option value="Sibling">Sibling</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[var(--text-secondary)] uppercase mb-1 font-mono">
                    Phone Number
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                    className="w-full px-3.5 py-2.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-primary)] text-sm focus:border-[var(--accent)] outline-none"
                  />
                </div>
              </div>

              {/* Audio Reference Ingestion */}
              <div>
                <label className="block text-xs font-semibold text-[var(--text-secondary)] uppercase mb-1 font-mono">
                  Voice Note or Audio Recording (30s)
                </label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="p-4 rounded-lg border border-dashed border-[var(--border-strong)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-hover)] cursor-pointer text-center space-y-1 transition-colors"
                >
                  <div className="text-sm font-semibold text-[var(--accent)] font-mono">
                    {file ? file.name : "Tap to Choose Voice Recording"}
                  </div>
                  <div className="text-xs text-[var(--text-muted)]">
                    WAV, MP3, or WhatsApp Voice Note
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*,.wav,.mp3,.ogg,.m4a"
                    className="hidden"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </div>
              </div>

              {/* Secret Question Setup */}
              <div className="pt-2 border-t border-[var(--border-subtle)] space-y-2">
                <div className="text-xs font-bold text-[var(--text-secondary)] font-mono">
                  Secret Family Question (Optional)
                </div>
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. What is our hometown dog's name?"
                  className="w-full px-3.5 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-primary)] text-xs focus:border-[var(--accent)] outline-none"
                />
                <input
                  type="text"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Answer (encrypted on device)"
                  className="w-full px-3.5 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-primary)] text-xs focus:border-[var(--accent)] outline-none"
                />
              </div>

              <GlassButton
                type="submit"
                variant="default"
                size="lg"
                className="w-full font-mono font-bold mt-2"
                label="Save to Family Vault →"
              />
            </form>
          </div>
        </div>

        {/* Right: Enrolled Members (7 Cols) */}
        <div className="lg:col-span-7">
          <div className="sec-card p-6 space-y-4">
            <h2 className="text-base font-bold text-[var(--text-primary)] pb-3 border-b border-[var(--border-subtle)] flex items-center justify-between font-mono">
              <span>Enrolled Family Contacts ({members.length})</span>
              <span className="text-xs text-[var(--success-text)] font-medium">100% Private on Device</span>
            </h2>

            <div className="space-y-3">
              {members.map((m) => (
                <div
                  key={m.id}
                  className="p-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-default)] space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[var(--accent)] text-black font-bold text-base flex items-center justify-center shadow-sm font-mono">
                        {m.name.slice(0, 1)}
                      </div>
                      <div>
                        <div className="font-bold text-sm text-[var(--text-primary)]">
                          {m.name}
                        </div>
                        <div className="text-xs text-[var(--text-muted)] font-mono">
                          {m.phone}
                        </div>
                      </div>
                    </div>

                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[var(--success-bg)] text-[var(--success-text)] border border-[var(--success-border)] font-mono">
                      {m.relation}
                    </span>
                  </div>

                  <div className="pt-2 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between text-xs text-[var(--text-muted)] gap-2">
                    <div>
                      <span>Secret: </span>
                      <span className="text-[var(--text-secondary)] italic font-medium">"{m.secretQuestion}"</span>
                    </div>
                    <span className="font-mono">Saved: {m.enrolledDate}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
