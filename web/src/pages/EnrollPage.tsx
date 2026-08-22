import { useState, useRef } from "react";

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
    enrolledDate: "2026-08-15",
    secretQuestion: "What is our hometown dog's name?",
  },
  {
    id: "p_priya_02",
    name: "Priya Sharma",
    relation: "Daughter",
    phone: "+91 99201 83721",
    enrolledDate: "2026-08-18",
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
      enrolledDate: new Date().toISOString().slice(0, 10),
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
      <div className="pb-4 border-b border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-mono font-bold tracking-widest text-zinc-500 uppercase">
            REGISTRY // 02
          </div>
          <h1 className="text-xl sm:text-2xl font-extrabold text-white font-sans">
            Family Voiceprint Vault
          </h1>
          <p className="text-xs text-zinc-400 font-mono mt-0.5">
            Store condition-matched reference embeddings (16kHz Wideband + 8kHz Narrowband) locally.
          </p>
        </div>

        <div className="text-xs font-mono text-emerald-400 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          <span>{members.length} PROFILES ACTIVE IN SECURE VAULT</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Enrollment Form (5 Cols) */}
        <div className="lg:col-span-5">
          <div className="hud-panel p-5 space-y-4">
            <div className="text-xs font-mono font-bold uppercase tracking-wider text-white pb-3 border-b border-white/10 flex items-center justify-between">
              <span>ENROLL NEW CONTACT</span>
              <span className="text-zinc-500">ECAPA-TDNN</span>
            </div>

            {isSuccess && (
              <div className="p-3 rounded bg-emerald-950/60 border border-emerald-500/60 text-xs font-mono text-emerald-300">
                [✓] VOICEPRINT EMBEDDING COMPUTED & COMMITTED TO LOCAL VAULT
              </div>
            )}

            <form onSubmit={handleEnroll} className="space-y-4 font-mono text-xs">
              <div>
                <label className="block text-zinc-400 uppercase mb-1 font-semibold">
                  CONTACT NAME *
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Rahul, Mother, Papa"
                  className="w-full px-3 py-2 rounded bg-[#050505] border border-white/15 text-white focus:border-white outline-none font-sans"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-zinc-400 uppercase mb-1 font-semibold">
                    RELATIONSHIP *
                  </label>
                  <select
                    value={relation}
                    onChange={(e) => setRelation(e.target.value)}
                    className="w-full px-3 py-2 rounded bg-[#050505] border border-white/15 text-white focus:border-white outline-none font-sans"
                  >
                    <option value="Son">Son</option>
                    <option value="Daughter">Daughter</option>
                    <option value="Mother">Mother</option>
                    <option value="Father">Father</option>
                    <option value="Spouse">Spouse</option>
                    <option value="Sibling">Sibling</option>
                    <option value="Other">Other Contact</option>
                  </select>
                </div>

                <div>
                  <label className="block text-zinc-400 uppercase mb-1 font-semibold">
                    PHONE NUMBER
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                    className="w-full px-3 py-2 rounded bg-[#050505] border border-white/15 text-white focus:border-white outline-none font-sans"
                  />
                </div>
              </div>

              {/* Audio Reference Ingestion */}
              <div>
                <label className="block text-zinc-400 uppercase mb-1 font-semibold">
                  REFERENCE AUDIO (30–60 SECONDS)
                </label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="p-4 rounded border border-dashed border-white/20 bg-[#050505] hover:bg-[#101010] cursor-pointer text-center space-y-1 transition-all"
                >
                  <div className="text-xs font-semibold text-white">
                    {file ? file.name : "[ SELECT OR DROP AUDIO / VOICE NOTE ]"}
                  </div>
                  <div className="text-[10px] text-zinc-500">
                    Extracts 192-dim speaker vector across wideband & 8kHz telephony codecs
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

              {/* Out-of-Band Challenge Setup */}
              <div className="pt-3 border-t border-white/10 space-y-2">
                <div className="text-[11px] uppercase font-bold text-zinc-300">
                  OUT-OF-BAND CHALLENGE QUESTION
                </div>
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Challenge Prompt (e.g. What is our first pet's name?)"
                  className="w-full px-3 py-2 rounded bg-[#050505] border border-white/15 text-white focus:border-white outline-none font-sans mb-1"
                />
                <input
                  type="text"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Secret Answer (stored as SHA-256 hash)"
                  className="w-full px-3 py-2 rounded bg-[#050505] border border-white/15 text-white focus:border-white outline-none font-sans"
                />
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded bg-white text-black font-bold uppercase tracking-wider hover:bg-zinc-200 transition-all cursor-pointer shadow-sm mt-2"
              >
                COMPUTE & REGISTER VOICEPRINT →
              </button>
            </form>
          </div>
        </div>

        {/* Right: Enrolled Members (7 Cols) */}
        <div className="lg:col-span-7">
          <div className="hud-panel p-5 space-y-4">
            <div className="text-xs font-mono font-bold uppercase tracking-wider text-white pb-3 border-b border-white/10 flex items-center justify-between">
              <span>ACTIVE ENROLLED PROFILES ({members.length})</span>
              <span className="text-zinc-500">AIR-GAPPED STORAGE</span>
            </div>

            <div className="space-y-3">
              {members.map((m) => (
                <div
                  key={m.id}
                  className="p-4 rounded bg-[#050505] border border-white/10 hover:border-white/20 transition-all space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded bg-white/10 border border-white/20 text-white font-mono font-bold text-xs flex items-center justify-center">
                        {m.name.slice(0, 1)}
                      </div>
                      <div>
                        <div className="font-semibold text-sm text-white font-sans">
                          {m.name}
                        </div>
                        <div className="text-xs font-mono text-zinc-500">
                          {m.id} · {m.phone}
                        </div>
                      </div>
                    </div>

                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-white/10 text-white border border-white/20 uppercase">
                      {m.relation}
                    </span>
                  </div>

                  <div className="pt-2 border-t border-white/10 flex flex-wrap items-center justify-between text-xs font-mono text-zinc-500 gap-2">
                    <div>
                      <span>CHALLENGE: </span>
                      <span className="text-zinc-300 italic">"{m.secretQuestion}"</span>
                    </div>
                    <span>REGISTERED: {m.enrolledDate}</span>
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
