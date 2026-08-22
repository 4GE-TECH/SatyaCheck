import { useState } from "react";
import type { ChallengeQuestion } from "../types/contracts";

interface ChallengeCardProps {
  question: ChallengeQuestion;
}

export default function ChallengeCard({ question }: ChallengeCardProps) {
  const [isAnswerRevealed, setIsAnswerRevealed] = useState(false);

  return (
    <div className="p-4 rounded-lg bg-amber-950/30 border border-amber-500/40 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
          <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-amber-300">
            Out-of-Band Challenge Prompt (Shared Secret)
          </h4>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-900/60 text-amber-200 border border-amber-700/60 font-semibold">
          IDENTITY VERIFICATION
        </span>
      </div>

      <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed font-sans">
        Instruct the listener to read this question immediately to the caller. An authentic contact will answer instantly; an AI clone or imposter will stall or deflect.
      </p>

      <div className="p-3 rounded bg-[var(--color-bg-root)] border border-amber-500/30">
        <div className="text-[10px] font-mono text-[var(--color-text-muted)] mb-1">
          CHALLENGE QUESTION (ASK VERBATIM):
        </div>
        <div className="text-sm font-semibold text-amber-200 font-sans">
          "{question.question_text}"
        </div>

        {question.relation_context && (
          <div className="text-[11px] text-[var(--color-text-muted)] mt-1.5 flex items-center justify-between border-t border-[var(--color-border-subtle)] pt-1.5 font-mono">
            <span>CONTEXT: {question.relation_context}</span>
            <button
              onClick={() => setIsAnswerRevealed(!isAnswerRevealed)}
              className="text-amber-400 hover:text-amber-300 text-[10px] font-semibold underline cursor-pointer"
            >
              {isAnswerRevealed ? "HIDE SECRET" : "REVEAL SECRET PROMPT"}
            </button>
          </div>
        )}

        {isAnswerRevealed && (
          <div className="mt-2 p-2 rounded bg-amber-950/60 border border-amber-700/50 text-xs font-mono text-amber-100">
            EXPECTED SHA-256 ANSWER HASH: <span className="text-amber-300 font-bold">{question.expected_answer_hash?.slice(0, 16)}...</span>
          </div>
        )}
      </div>
    </div>
  );
}
