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
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
          My Family Voice Vault
        </h1>
        <p className="text-base text-slate-300 mt-1">
          Save a 30-second voice recording of your children and family. If you ever receive a suspicious call claiming to be them, SatyaCheck checks if the voice is authentic.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Enrollment Form (5 Cols) */}
        <div className="lg:col-span-5">
          <div className="p-6 rounded-2xl bg-[#111827] border border-slate-700 space-y-4 shadow-lg">
            <h2 className="text-lg font-bold text-white pb-3 border-b border-slate-800 flex items-center gap-2">
              <span>Add a Family Member</span>
            </h2>

            {isSuccess && (
              <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-500 text-sm text-emerald-200">
                ✓ Voice recording saved safely to your family vault!
              </div>
            )}

            <form onSubmit={handleEnroll} className="space-y-4 text-sm">
              <div>
                <label className="block text-sm font-semibold text-slate-200 mb-1.5">
                  Full Name *
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Rahul, Mother, Papa"
                  className="w-full px-4 py-3 rounded-xl bg-[#1F2937] border border-slate-600 text-white text-base focus:border-blue-500 outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-semibold text-slate-200 mb-1.5">
                    Relationship *
                  </label>
                  <select
                    value={relation}
                    onChange={(e) => setRelation(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl bg-[#1F2937] border border-slate-600 text-white text-base focus:border-blue-500 outline-none"
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
                  <label className="block text-sm font-semibold text-slate-200 mb-1.5">
                    Phone Number
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                    className="w-full px-4 py-3 rounded-xl bg-[#1F2937] border border-slate-600 text-white text-base focus:border-blue-500 outline-none"
                  />
                </div>
              </div>

              {/* Audio Reference Ingestion */}
              <div>
                <label className="block text-sm font-semibold text-slate-200 mb-1.5">
                  Voice Note or Audio Recording (30s)
                </label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="p-5 rounded-xl border-2 border-dashed border-slate-600 bg-[#1F2937] hover:bg-[#374151] cursor-pointer text-center space-y-1 transition-all"
                >
                  <div className="text-base font-bold text-blue-400">
                    {file ? file.name : "📁 Tap to Choose Voice Recording"}
                  </div>
                  <div className="text-xs text-slate-400">
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
              <div className="pt-3 border-t border-slate-800 space-y-3">
                <div className="text-sm font-bold text-slate-200">
                  Secret Family Question (Optional)
                </div>
                <p className="text-xs text-slate-400">
                  Set a question only this person knows. SatyaCheck will prompt you to ask this if a scam occurs.
                </p>

                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. What is our hometown dog's name?"
                  className="w-full px-4 py-2.5 rounded-xl bg-[#1F2937] border border-slate-600 text-white text-sm focus:border-blue-500 outline-none"
                />
                <input
                  type="text"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Answer (encrypted on device)"
                  className="w-full px-4 py-2.5 rounded-xl bg-[#1F2937] border border-slate-600 text-white text-sm focus:border-blue-500 outline-none"
                />
              </div>

              <button
                type="submit"
                className="w-full py-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-base transition-all cursor-pointer shadow-md mt-2"
              >
                Save to Family Vault →
              </button>
            </form>
          </div>
        </div>

        {/* Right: Enrolled Members (7 Cols) */}
        <div className="lg:col-span-7">
          <div className="p-6 rounded-2xl bg-[#111827] border border-slate-700 space-y-4 shadow-lg">
            <h2 className="text-lg font-bold text-white pb-3 border-b border-slate-800 flex items-center justify-between">
              <span>Enrolled Family Contacts ({members.length})</span>
              <span className="text-xs text-emerald-400 font-medium">100% Private on Device</span>
            </h2>

            <div className="space-y-3">
              {members.map((m) => (
                <div
                  key={m.id}
                  className="p-5 rounded-xl bg-[#1F2937] border border-slate-600 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3.5">
                      <div className="w-11 h-11 rounded-full bg-blue-600 text-white font-bold text-lg flex items-center justify-center shadow">
                        {m.name.slice(0, 1)}
                      </div>
                      <div>
                        <div className="font-bold text-base text-white">
                          {m.name}
                        </div>
                        <div className="text-sm text-slate-300">
                          {m.phone}
                        </div>
                      </div>
                    </div>

                    <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60">
                      {m.relation}
                    </span>
                  </div>

                  <div className="pt-3 border-t border-slate-700 flex flex-wrap items-center justify-between text-xs text-slate-400 gap-2">
                    <div>
                      <span>Secret: </span>
                      <span className="text-slate-200 italic font-medium">"{m.secretQuestion}"</span>
                    </div>
                    <span>Saved: {m.enrolledDate}</span>
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
