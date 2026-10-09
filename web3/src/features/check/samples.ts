import type { ScreeningResponse } from '../../types/contracts';
import type { MockScenario } from '../../api/mock';

export interface Sample {
  scenario: MockScenario;
  label: string;
  story: string;
  load: () => Promise<ScreeningResponse>;
}

function sample(scenario: MockScenario, label: string, story: string): Sample {
  return {
    scenario,
    label,
    story,
    load: async () => {
      const { getMockFixture } = await import('../../api/mock');
      return { ...getMockFixture(scenario), timestamp: new Date().toISOString() };
    },
  };
}

/** Labelled demonstrations. They never describe the person's own audio, and every surface says so. */
export const SAMPLES: Sample[] = [
  sample('red', 'Cloned emergency', 'A son’s cloned voice demands UPI money and secrecy'),
  sample('unverified', 'Bank IVR', 'A legitimate automated bank call'),
  sample('green', 'Familiar voice', 'An enrolled family member, nothing unusual'),
  sample('caution', 'Unusual request', 'A known voice asking for something odd'),
  sample('suspicious', 'Synthetic stranger', 'An unknown synthetic voice, no script'),
  sample('insufficient', 'Too short', 'Under a second of speech'),
];
