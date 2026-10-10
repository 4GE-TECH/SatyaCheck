import { useEffect, useState } from 'react';
import { getPeople, type PersonRecord } from '../lib/api';

/**
 * "Who's calling?" — the person the caller says they are. The voice is checked against that
 * person's voiceprint. A claim narrows the check; it is never proof, and leaving it blank is fine.
 */
export function CallerPicker({ value, onChange, disabled = false, id = 'caller-claim' }: {
  value: string | null;
  onChange: (personId: string | null) => void;
  disabled?: boolean;
  id?: string;
}) {
  const [people, setPeople] = useState<PersonRecord[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getPeople(controller.signal)
      .then(list => setPeople(list.filter(p => (p.voiceprints?.length ?? 1) > 0)))
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, []);

  if (failed || (people && !people.length)) return null;

  return (
    <div className="field caller-picker">
      <label htmlFor={id}>Who's calling? <span className="muted">(optional)</span></label>
      <select id={id} className="input" value={value ?? ''} disabled={disabled || !people}
        onChange={e => onChange(e.target.value || null)}>
        <option value="">{people ? 'Not sure, or someone new' : 'Loading saved voices…'}</option>
        {people?.map(p => (
          <option key={p.person_id} value={p.person_id}>{p.name}{p.relation ? ` (${p.relation})` : ''}</option>
        ))}
      </select>
      <span className="hint">If the caller says who they are, pick them. SatyaCheck checks the voice against theirs. It is a check, not proof either way.</span>
    </div>
  );
}

