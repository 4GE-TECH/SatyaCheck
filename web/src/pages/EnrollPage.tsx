import { useEffect, useRef, useState, type FormEvent } from 'react';
import { UsersRound, ArrowRight, RefreshCw, Mic, Trash2 } from 'lucide-react';
import { deletePerson, getPeople, request, type PersonRecord } from '../api/client';
import { PageHeading, Button, Notice, EmptyState } from '../components/Primitives';
import AudioInput from '../components/AudioInput';
import { date } from '../lib/presentation';
import { initial } from '../lib/initial';

const prompts = {
  en: 'Hello, I’m recording my voice so my family can recognise me. I usually call in the evening to ask how everyone’s day went. If someone asks for money in my name, call me on my saved number first. Now I’ll keep talking naturally about my day.',
  hi: 'नमस्ते, मैं अपनी आवाज़ पहचानने के लिए यह रिकॉर्डिंग बना रहा हूँ। आज का दिन कैसा रहा? मैं अक्सर अपने परिवार से शाम को बात करता हूँ। अगर कोई मेरे नाम पर पैसे माँगे, तो पहले मेरे परिचित नंबर पर फ़ोन करके पूछें। अपने दिन के बारे में कुछ और बताइए।',
};

export default function EnrollPage() {
  const [people, setPeople] = useState<PersonRecord[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [retry, setRetry] = useState(0);
  const [name, setName] = useState('');
  const [relation, setRelation] = useState('Family');
  const [phone, setPhone] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [promptLanguage, setPromptLanguage] = useState<'en' | 'hi'>('en');
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState('');
  const saving = useRef<AbortController | null>(null);
  const nameInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    getPeople(controller.signal)
      .then(setPeople)
      .catch(problem => { if (!controller.signal.aborted) setListError(problem.message); })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => () => saving.current?.abort(), []);

  function reload() {
    setListLoading(true);
    setListError('');
    setRetry(n => n + 1);
  }

  function resetForm() {
    setName(''); setRelation('Family'); setPhone(''); setQuestion(''); setAnswer('');
    setFile(null); setConsent(false); setEditing(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !name.trim() || !consent || saving.current || recording || removing) return;
    if (Boolean(question.trim()) !== Boolean(answer.trim())) {
      setError('Add both a verification question and its answer, or leave both empty.');
      return;
    }
    const controller = new AbortController();
    saving.current = controller;
    setBusy(true); setError(''); setSuccess('');
    try {
      const body = new FormData();
      body.append('name', name.trim());
      body.append('relation', relation.trim());
      body.append('file', file);
      if (phone.trim()) body.append('phone_number', phone.trim());
      if (editing) body.append('person_id', editing);
      if (question.trim()) body.append('shared_secrets', JSON.stringify([{ question: question.trim(), answer: answer.trim() }]));
      const response = await request('/api/enroll', { method: 'POST', body, signal: controller.signal });
      const person = await response.json() as PersonRecord;
      if (!person.person_id || !Array.isArray(person.voiceprints) || !person.voiceprints.length) {
        throw new Error('The service did not confirm a saved voiceprint. Please retry with a clearer recording.');
      }
      if (controller.signal.aborted) return;
      setPeople(current => [person, ...current.filter(p => p.person_id !== person.person_id)]);
      setSuccess(`${person.name}’s voice was enrolled successfully.`);
      resetForm();
    } catch (problem) {
      if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : 'Enrollment could not be completed. Please try again.');
    } finally {
      if (saving.current === controller) { saving.current = null; setBusy(false); }
    }
  }

  function edit(person: PersonRecord) {
    setEditing(person.person_id);
    setName(person.name);
    setRelation(person.relation);
    setPhone(person.phone_number || '');
    setFile(null); setConsent(false); setQuestion(''); setAnswer(''); setError(''); setSuccess('');
    nameInput.current?.focus();
  }

  async function remove(person: PersonRecord) {
    if (removing || busy || recording) return;
    setRemoving(person.person_id);
    setRemoveError('');
    try {
      await deletePerson(person.person_id);
      setPeople(current => current.filter(p => p.person_id !== person.person_id));
      if (editing === person.person_id) resetForm();
      setConfirming(null);
      setSuccess(`${person.name} was removed. Their voice will no longer be matched.`);
    } catch (problem) {
      setRemoveError(problem instanceof Error ? problem.message : 'Could not remove this voice. Please try again.');
    } finally {
      setRemoving(null);
    }
  }

  const locked = busy || recording || Boolean(removing);

  return (
    <div className="page-stack">
      <PageHeading
        title="Known voices"
        description="Enroll people you know so a future recording can be compared with their voice. Strangers stay unverified, which is normal."
      />
      {success && <Notice tone="success">{success}</Notice>}

      <div className="enroll-grid">
        <section className="panel" aria-labelledby="people-heading">
          <div className="panel-head">
            <h2 id="people-heading">
              Enrolled {!listLoading && !listError && <span className="count">{people.length}</span>}
            </h2>
            <button type="button" className="icon-button" disabled={listLoading || locked} onClick={reload} aria-label="Refresh known voices">
              <RefreshCw size={17} />
            </button>
          </div>
          {listLoading ? (
            <div className="skeleton-list" role="status" aria-label="Loading known voices">
              {[0, 1, 2].map(i => <span key={i} />)}
            </div>
          ) : listError ? (
            <div className="panel-body">
              <Notice tone="danger">
                {listError}{' '}
                <Button variant="quiet" onClick={reload}>Try again</Button>
              </Notice>
            </div>
          ) : !people.length ? (
            <EmptyState icon={<UsersRound size={24} />} title="No one enrolled yet">
              <p>Add a family member with the form. Until then, every voice is reported as unverified.</p>
            </EmptyState>
          ) : (
            <ul className="people-list">
              {people.map(person => (
                <li key={person.person_id} className={editing === person.person_id ? 'editing' : undefined}>
                  <span className="avatar" aria-hidden="true">{initial(person.name)}</span>
                  <div className="person-meta">
                    <strong className="person-name" dir="auto">{person.name}</strong>
                    {(person.relation || person.phone_number) && <span>
                      {person.relation}
                      {person.phone_number && <>{person.relation && ' · '}<span className="mono">{person.phone_number}</span></>}
                    </span>}
                    <span className="person-sub">
                      {person.voiceprints?.length
                        ? `${person.voiceprints.length} ${person.voiceprints.length === 1 ? 'voiceprint' : 'voiceprints'}`
                        : 'No voiceprint returned'}
                      {person.created_at && ` · since ${date(person.created_at)}`}
                    </span>
                  </div>
                  {confirming === person.person_id ? (
                    <div className="confirm-row" role="group" aria-label={`Confirm removing ${person.name}`}>
                      <span>Remove {person.name}?</span>
                      <Button variant="danger" busy={removing === person.person_id} onClick={() => remove(person)}>Remove</Button>
                      <Button variant="quiet" disabled={removing === person.person_id} onClick={() => { setConfirming(null); setRemoveError(''); }}>Keep</Button>
                    </div>
                  ) : (
                    <div className="person-actions">
                      <Button variant="quiet" disabled={locked} onClick={() => edit(person)}><Mic size={15} aria-hidden="true" />Re-record</Button>
                      <button
                        type="button" className="icon-button" disabled={locked}
                        onClick={() => { setConfirming(person.person_id); setRemoveError(''); }}
                        aria-label={`Remove ${person.name}`}
                      >
                        <Trash2 size={17} />
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {removeError && <div className="panel-body"><Notice tone="danger">{removeError}</Notice></div>}
          <p className="panel-note">A match is one piece of evidence. For an unexpected request, call back on a number you already trust.</p>
        </section>

        <section className="panel" aria-labelledby="enroll-heading">
          <div className="panel-head">
            <h2 id="enroll-heading">{editing ? 'Re-record a voice' : 'Add a voice'}</h2>
            {editing && <Button variant="quiet" disabled={locked} onClick={resetForm}>Cancel</Button>}
          </div>
          <form onSubmit={submit} className="panel-body form">
            <fieldset disabled={locked} className="form-fields">
              <div className="field">
                <label htmlFor="person-name">Name</label>
                <input ref={nameInput} id="person-name" required maxLength={100} autoComplete="off" value={name} onChange={e => setName(e.target.value)} />
              </div>
              <div className="field-pair">
                <div className="field">
                  <label htmlFor="relation">Relationship</label>
                  <input id="relation" required maxLength={60} value={relation} onChange={e => setRelation(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="phone">Phone <span className="optional">optional</span></label>
                  <input id="phone" type="tel" autoComplete="off" maxLength={30} value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91" />
                </div>
              </div>
            </fieldset>

            <div className="script-card">
              <div className="script-head">
                <span>Read this aloud, or speak naturally</span>
                <div className="mini-toggle" role="group" aria-label="Script language">
                  <button type="button" aria-pressed={promptLanguage === 'en'} onClick={() => setPromptLanguage('en')}>English</button>
                  <button type="button" aria-pressed={promptLanguage === 'hi'} onClick={() => setPromptLanguage('hi')} lang="hi">हिन्दी</button>
                </div>
              </div>
              <p lang={promptLanguage}>{prompts[promptLanguage]}</p>
            </div>

            <AudioInput file={file} onFile={setFile} disabled={busy || Boolean(removing)} enrollment onBusyChange={setRecording} />

            <fieldset disabled={locked} className="form-fields">
              <details className="optional-fields">
                <summary>Add a verification question</summary>
                <div className="field">
                  <label htmlFor="question">A question only they would know</label>
                  <input id="question" maxLength={240} value={question} onChange={e => setQuestion(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="answer">Answer</label>
                  <input id="answer" type="password" autoComplete="off" maxLength={240} value={answer} onChange={e => setAnswer(e.target.value)} />
                  <small>Sent to your screening service. Use it alongside a callback, never instead of one.</small>
                </div>
              </details>
              <label className="check-label">
                <input type="checkbox" checked={consent} required onChange={e => setConsent(e.target.checked)} />
                <span>{name.trim() || 'This person'} has agreed to have their voice enrolled for comparison.</span>
              </label>
            </fieldset>

            {error && <Notice tone="danger">{error}</Notice>}
            <div className="panel-foot">
              <p>Enrollment is confirmed only after the service saves a voiceprint.</p>
              <Button type="submit" busy={busy} disabled={!file || !name.trim() || !relation.trim() || !consent || locked}>
                {busy ? 'Enrolling…' : editing ? 'Save new recording' : 'Enroll voice'}
                {!busy && <ArrowRight size={17} aria-hidden="true" />}
              </Button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
