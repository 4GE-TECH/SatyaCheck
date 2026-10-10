import { useEffect, useRef, useState, type FormEvent } from 'react';
import { EASE, gsap, reducedMotion, useGSAP } from '../../lib/motion';
import { ambient } from '../../components/AmbientField';
import { ArrowClockwise, CheckCircle, Microphone, Stop, Trash, UploadSimple, UserPlus, UsersThree, X } from '@phosphor-icons/react';
import { audioError, deletePerson, enroll, getPeople, type PersonRecord } from '../../lib/api';
import { clock, when } from '../../lib/verdict';
import { useRecorder } from '../../hooks/useRecorder';
import VoiceField from '../../components/VoiceField';
import { Button, IconButton, Notice, Skeleton } from '../../components/ui';

const SCRIPT = {
  en: 'Hello, I’m recording my voice so my family can recognise me. I usually call in the evening to ask how everyone’s day went. If someone ever asks for money in my name, call me back on my saved number first. Now I’ll keep talking naturally about my day.',
  hi: 'नमस्ते, मैं अपनी आवाज़ इसलिए रिकॉर्ड कर रहा हूँ ताकि मेरा परिवार मुझे पहचान सके। मैं अक्सर शाम को फ़ोन करके सबका हाल पूछता हूँ। अगर कभी कोई मेरे नाम पर पैसे माँगे, तो पहले मेरे सेव किए हुए नंबर पर मुझे वापस फ़ोन करें। अब मैं अपने दिन के बारे में आराम से बात करता रहूँगा।',
};
const TARGET_SECONDS = 30;

export default function VoicesPage() {
  const [people, setPeople] = useState<PersonRecord[]>([]);
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [listError, setListError] = useState('');
  const [reload, setReload] = useState(0);
  const [editing, setEditing] = useState<PersonRecord | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [flash, setFlash] = useState('');
  const [removeError, setRemoveError] = useState('');
  const page = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (reducedMotion() || listState !== 'ready') return;
    gsap.from('.people-list li', { x: -16, duration: 0.7, stagger: 0.06, ease: EASE.out });
  }, { dependencies: [listState], scope: page });

  useEffect(() => {
    const controller = new AbortController();
    getPeople(controller.signal)
      .then(list => { setPeople(list); setListState('ready'); })
      .catch(problem => { if (!controller.signal.aborted) { setListError(problem.message); setListState('error'); } });
    return () => controller.abort();
  }, [reload]);

  async function remove(person: PersonRecord) {
    setRemoving(person.person_id);
    setRemoveError('');
    try {
      const { voiceprintDeleted } = await deletePerson(person.person_id);
      const row = page.current?.querySelector(`[data-id="${CSS.escape(person.person_id)}"]`);
      if (row && !reducedMotion()) await gsap.to(row, { height: 0, opacity: 0, paddingTop: 0, paddingBottom: 0, duration: 0.45, ease: EASE.inOut });
      setPeople(list => list.filter(p => p.person_id !== person.person_id));
      if (editing?.person_id === person.person_id) setEditing(null);
      setConfirming(null);
      setFlash(voiceprintDeleted === true
        ? `${person.name} was removed, with their stored voiceprint. Their voice will no longer be matched.`
        : voiceprintDeleted === false
          ? `${person.name} was removed. No stored voiceprint file was found to delete.`
          : `${person.name} was removed. Their voice will no longer be matched.`);
    } catch (problem) {
      setRemoveError(problem instanceof Error ? problem.message : 'Could not remove this voice. Please try again.');
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="page voices-page" ref={page}>
      <header className="page-head">
        <h1>Known voices</h1>
        <p>Enroll the people who might call. A future recording can then be compared with their voice. Anyone not enrolled stays <em>unverified</em>, which is normal and not a warning.</p>
      </header>
        {flash && (
          <div className="flash">
            <Notice tone="safe" action={<IconButton label="Dismiss" onClick={() => setFlash('')}><X size={16} weight="bold" /></IconButton>}>{flash}</Notice>
          </div>
        )}

      <div className="voices-grid">
        <section className="panel people" aria-labelledby="people-title">
          <div className="panel-head">
            <h2 id="people-title">Enrolled{listState === 'ready' && <span className="count num">{people.length}</span>}</h2>
            <IconButton label="Refresh the list" onClick={() => { setListState('loading'); setReload(n => n + 1); }} disabled={listState === 'loading'}>
              <ArrowClockwise size={17} weight="bold" />
            </IconButton>
          </div>
          {listState === 'loading' ? (
            <div className="people-loading" role="status" aria-label="Loading known voices"><Skeleton lines={3} /></div>
          ) : listState === 'error' ? (
            <div className="panel-pad">
              <Notice tone="danger" action={<Button size="sm" onClick={() => { setListState('loading'); setReload(n => n + 1); }}>Try again</Button>}>{listError}</Notice>
            </div>
          ) : !people.length ? (
            <div className="people-empty">
              <UsersThree size={36} weight="duotone" aria-hidden="true" />
              <h3>No one enrolled yet</h3>
              <p>Start with the people most likely to call: children, parents, a spouse.</p>
            </div>
          ) : (
            <ul className="people-list">
                {people.map(person => (
                  <li key={person.person_id} data-id={person.person_id} className={editing?.person_id === person.person_id ? 'is-editing' : undefined}>
                    <span className="avatar" aria-hidden="true">{Array.from(person.name)[0]?.toUpperCase()}</span>
                    <div className="person">
                      <strong className="ellipsis" title={person.name}>{person.name}</strong>
                      <span className="ellipsis">{person.relation}{person.phone_number ? <> · <span className="num">{person.phone_number}</span></> : null}</span>
                      <span className="person-sub">
                        {person.voiceprints?.length ? `${person.voiceprints.length} ${person.voiceprints.length === 1 ? 'voiceprint' : 'voiceprints'}` : 'No voiceprint returned'}
                        {person.created_at ? ` · since ${when(person.created_at)}` : ''}
                        {person.consent_recorded_at ? ' · consent recorded' : ' · no consent on record'}
                      </span>
                    </div>
                    {confirming === person.person_id ? (
                      <div className="confirm" role="group" aria-label={`Confirm removing ${person.name}`}>
                        <span>Remove {person.name}?</span>
                        <Button size="sm" variant="danger" busy={removing === person.person_id} onClick={() => remove(person)}>Remove</Button>
                        <Button size="sm" variant="ghost" disabled={removing === person.person_id} onClick={() => setConfirming(null)}>Keep</Button>
                      </div>
                    ) : (
                      <div className="person-actions">
                        <Button size="sm" variant="ghost" onClick={() => { setEditing(person); setFlash(''); }}><Microphone size={15} weight="bold" aria-hidden="true" />Re-record</Button>
                        <IconButton label={`Remove ${person.name}`} onClick={() => { setConfirming(person.person_id); setRemoveError(''); }}><Trash size={16} weight="bold" /></IconButton>
                      </div>
                    )}
                  </li>
                ))}
            </ul>
          )}
          {removeError && <div className="panel-pad"><Notice tone="danger">{removeError}</Notice></div>}
          <p className="panel-note">A match is one piece of evidence, not proof. For anything unexpected, call back on a number you already trust.</p>
        </section>

        <Enroll
          key={editing?.person_id ?? 'new'}
          editing={editing}
          onCancel={() => setEditing(null)}
          onDone={person => {
            setPeople(list => [person, ...list.filter(p => p.person_id !== person.person_id)]);
            setFlash(`${person.name}’s voice is enrolled.`);
            setEditing(null);
            setListState('ready');
          }}
        />
      </div>
    </div>
  );
}

function Enroll({ editing, onCancel, onDone }: { editing: PersonRecord | null; onCancel: () => void; onDone: (person: PersonRecord) => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [relation, setRelation] = useState(editing?.relation ?? '');
  const [phone, setPhone] = useState(editing?.phone_number ?? '');
  const [otherNumbers, setOtherNumbers] = useState((editing?.phone_numbers ?? []).filter(n => n !== editing?.phone_number).join(', '));
  const [aliases, setAliases] = useState((editing?.aliases ?? []).join(', '));
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [clipSeconds, setClipSeconds] = useState<number | null>(null);
  const [consent, setConsent] = useState(false);
  const [lang, setLang] = useState<'en' | 'hi'>('en');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const nameField = useRef<HTMLInputElement>(null);
  const recorder = useRecorder((clip, length) => { setFile(clip); setClipSeconds(length); setError(''); });
  const recording = recorder.state !== 'idle';
  useEffect(() => { ambient.level = recording ? recorder.level : 0; }, [recording, recorder.level]);
  useEffect(() => () => { ambient.level = 0; }, []);

  useEffect(() => { if (editing) nameField.current?.focus(); }, [editing]);
  useEffect(() => () => controller.current?.abort(), []);

  function pick(next: File) {
    const problem = audioError(next);
    if (problem) { setError(problem); return; }
    setError('');
    setFile(next);
    setClipSeconds(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !name.trim() || !relation.trim() || !consent || busy || recording) return;
    if (Boolean(question.trim()) !== Boolean(answer.trim())) { setError('Add both a question and its answer, or leave both empty.'); return; }
    const active = new AbortController();
    controller.current = active;
    setBusy(true);
    setError('');
    try {
      const person = await enroll({
        name: name.trim(), relation: relation.trim(), phone: phone.trim() || undefined, file,
        personId: editing?.person_id ?? null,
        secret: question.trim() ? { question: question.trim(), answer: answer.trim() } : null,
        consent,
        phoneNumbers: splitList(otherNumbers),
        aliases: splitList(aliases),
      }, active.signal);
      if (!active.signal.aborted) onDone(person);
    } catch (problem) {
      if (!active.signal.aborted) setError(problem instanceof Error ? problem.message : 'Enrollment could not be completed. Please try again.');
    } finally {
      if (controller.current === active) { controller.current = null; setBusy(false); }
    }
  }

  const progress = Math.min(1, (recording ? recorder.seconds : clipSeconds ?? 0) / TARGET_SECONDS);

  return (
    <section className="panel studio" aria-labelledby="studio-title">
      <div className="panel-head">
        <h2 id="studio-title">{editing ? `Re-record ${editing.name}` : 'Enroll a voice'}</h2>
        {editing ? <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button> : <UserPlus size={20} weight="duotone" aria-hidden="true" className="muted" />}
      </div>
      <form className="studio-form" onSubmit={submit}>
        <fieldset disabled={busy || recording} className="studio-step">
          <legend><span className="step-n num">1</span>Who is it?</legend>
          <div className="field">
            <label htmlFor="v-name">Name</label>
            <input ref={nameField} id="v-name" className="input" required maxLength={100} autoComplete="off" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="v-relation">Relationship</label>
              <input id="v-relation" className="input" required maxLength={60} value={relation} onChange={e => setRelation(e.target.value)} placeholder="Son, mother, friend…" />
            </div>
            <div className="field">
              <label htmlFor="v-phone">Phone <span className="muted">(optional)</span></label>
              <input id="v-phone" className="input" type="tel" maxLength={30} value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91" />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="v-aliases">What callers call them <span className="muted">(optional)</span></label>
              <input id="v-aliases" className="input" maxLength={200} value={aliases} onChange={e => setAliases(e.target.value)} placeholder="Papa, Raju bhaiya" />
              <span className="hint">Separate with commas. Helps match “It’s Papa” to this person.</span>
            </div>
            <div className="field">
              <label htmlFor="v-numbers">Other numbers <span className="muted">(optional)</span></label>
              <input id="v-numbers" className="input" type="tel" maxLength={120} value={otherNumbers} onChange={e => setOtherNumbers(e.target.value)} placeholder="+91…, +91…" />
              <span className="hint">A matching number is a hint, never proof. Numbers can be faked.</span>
            </div>
          </div>
        </fieldset>

        <div className="studio-step">
          <div className="legend"><span className="step-n num">2</span>Their voice</div>
          <div className="script">
            <div className="script-head">
              <span>Ask them to read this aloud, or just talk</span>
              <div className="segmented small" role="group" aria-label="Script language">
                <button type="button" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>English</button>
                <button type="button" aria-pressed={lang === 'hi'} onClick={() => setLang('hi')} lang="hi">हिन्दी</button>
              </div>
            </div>
            <p lang={lang}>{SCRIPT[lang]}</p>
          </div>
          <div className={`mic-stage${recording ? ' is-recording' : ''}`}>
            <VoiceField level={recorder.level} />
            <div className="mic-stage-content">
              {recording ? (
                <>
                  <span className="num stage-clock small">{clock(recorder.seconds)}</span>
                  <Button variant="danger" onClick={recorder.stop}><Stop size={16} weight="fill" aria-hidden="true" />Stop</Button>
                </>
              ) : file ? (
                <div className="file-chip compact">
                  <CheckCircle size={20} weight="fill" className="t-safe" aria-hidden="true" />
                  <div className="file-meta"><strong className="ellipsis">{file.name}</strong><span>{clipSeconds != null ? `${clipSeconds} s recorded` : `${(file.size / 1024 / 1024).toFixed(2)} MB`}</span></div>
                  <IconButton label="Remove this audio" onClick={() => { setFile(null); setClipSeconds(null); }} disabled={busy}><X size={16} weight="bold" /></IconButton>
                </div>
              ) : (
                <div className="row-gap">
                  <Button variant="primary" onClick={recorder.start} busy={recorder.state === 'starting'} disabled={busy}><Microphone size={16} weight="fill" aria-hidden="true" />Record</Button>
                  <Button onClick={() => picker.current?.click()} disabled={busy}><UploadSimple size={16} weight="bold" aria-hidden="true" />Upload</Button>
                </div>
              )}
            </div>
          </div>
          <div className="target" aria-hidden={!recording && clipSeconds == null}>
            <div className="target-track"><span className="target-fill" style={{ transform: `scaleX(${progress})` }} /></div>
            <span className="muted small"><span className="num">{Math.min(TARGET_SECONDS, Math.floor(recording ? recorder.seconds : clipSeconds ?? 0))} / {TARGET_SECONDS} s</span> · aim for {TARGET_SECONDS} seconds in a quiet room. The service needs at least 15 seconds of speech.</span>
          </div>
          {recorder.error && <Notice tone="danger">{recorder.error}</Notice>}
          <input ref={picker} type="file" className="sr-only" tabIndex={-1} aria-hidden="true" accept="audio/*,.wav,.mp3,.ogg,.opus,.webm,.m4a,.flac,.amr" onChange={e => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ''; }} />
        </div>

        <fieldset disabled={busy || recording} className="studio-step">
          <legend><span className="step-n num">3</span>Consent</legend>
          <details className="secret">
            <summary>Add a question only they would know (optional)</summary>
            <div className="field">
              <label htmlFor="v-q">Question</label>
              <input id="v-q" className="input" maxLength={240} value={question} onChange={e => setQuestion(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="v-a">Answer</label>
              <input id="v-a" className="input" type="password" autoComplete="off" maxLength={240} value={answer} onChange={e => setAnswer(e.target.value)} />
              <span className="hint">Stored by your screening service. Use it alongside a call back, never instead of one.</span>
            </div>
          </details>
          <label className="checkline">
            <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
            <span>{name.trim() || 'This person'} has agreed to have their voice enrolled for comparison. A voiceprint is biometric data: the service records when consent was given, and removing the person deletes it.</span>
          </label>
        </fieldset>

        {error && <Notice tone="danger">{error}</Notice>}
        <div className="studio-foot">
          <span className="muted small">Enrollment counts only once the service confirms a saved voiceprint.</span>
          <Button type="submit" variant="primary" size="lg" busy={busy} disabled={!file || !name.trim() || !relation.trim() || !consent || recording}>
            {busy ? 'Enrolling…' : editing ? 'Save new recording' : 'Enroll voice'}
          </Button>
        </div>
      </form>
    </section>
  );
}

/** "Papa, Raju" → ["Papa", "Raju"]. */
function splitList(text: string): string[] {
  return text.split(/[,;\n]/).map(part => part.trim()).filter(Boolean);
}
