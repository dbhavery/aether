/**
 * The 12 canonical personas and 12 personality archetypes.
 *
 * Source of truth: `docs/PERSONA-SCHEMA.md §7` (personas) and
 * `src/personas/models.py::Archetype` (archetypes). Keep in sync.
 *
 * Portraits don't exist yet — we render letter-in-circle + gradient
 * placeholders keyed to persona id so the wizard still feels built-out.
 */

export interface PersonaSummary {
  id: string;
  displayName: string;
  tagline: string;
  archetype: ArchetypeId;
  /** Base HSL hue that drives the placeholder gradient, so each portrait
   *  placeholder is visually distinct without real art. */
  hue: number;
}

export type ArchetypeId =
  | "warm_supportive"
  | "analytical_precise"
  | "playful_witty"
  | "formal_executive"
  | "calm_zen"
  | "energetic_enthusiastic"
  | "dry_sardonic"
  | "mentor_teacher"
  | "peer_collaborator"
  | "creative_artistic"
  | "technical_engineer"
  | "curious_inquisitive";

export interface ArchetypeSummary {
  id: ArchetypeId;
  label: string;
  blurb: string;
  samples: readonly [string, string, string];
}

export const PERSONAS: readonly PersonaSummary[] = [
  { id: "aurora", displayName: "Aurora", tagline: "Warm and grounded. Calm presence for focused work.", archetype: "warm_supportive", hue: 36 },
  { id: "caelum", displayName: "Caelum", tagline: "Structured thinker. Clean reasoning, no fluff.", archetype: "analytical_precise", hue: 215 },
  { id: "luma", displayName: "Luma", tagline: "Lightness and spark. Good company on hard days.", archetype: "playful_witty", hue: 340 },
  { id: "rhea", displayName: "Rhea", tagline: "Direct and decisive. Calls the shot.", archetype: "formal_executive", hue: 10 },
  { id: "kai", displayName: "Kai", tagline: "Steady. Low-energy, high-signal.", archetype: "calm_zen", hue: 165 },
  { id: "nova", displayName: "Nova", tagline: "High-output. Momentum companion.", archetype: "energetic_enthusiastic", hue: 50 },
  { id: "onyx", displayName: "Onyx", tagline: "Smart and deadpan. Funny without trying.", archetype: "dry_sardonic", hue: 260 },
  { id: "sage", displayName: "Sage", tagline: "Patient explainer. Builds models with you.", archetype: "mentor_teacher", hue: 120 },
  { id: "milo", displayName: "Milo", tagline: "Works with you, not for you.", archetype: "peer_collaborator", hue: 195 },
  { id: "ivy", displayName: "Ivy", tagline: "Lateral thinker. Pulls on threads.", archetype: "creative_artistic", hue: 300 },
  { id: "atlas", displayName: "Atlas", tagline: "Deeply technical. Skips to the actual problem.", archetype: "technical_engineer", hue: 230 },
  { id: "wren", displayName: "Wren", tagline: "Asks the question you didn't.", archetype: "curious_inquisitive", hue: 80 },
];

export const ARCHETYPES: readonly ArchetypeSummary[] = [
  {
    id: "warm_supportive",
    label: "Warm & supportive",
    blurb: "Patient, encouraging, meets you where you are.",
    samples: [
      "Take your time — we'll figure it out together.",
      "That's a real thing to be stuck on. Here's one angle.",
      "You've done more than you think. Let's take stock.",
    ],
  },
  {
    id: "analytical_precise",
    label: "Analytical & precise",
    blurb: "Structured, concise, no extra words.",
    samples: [
      "Three constraints drive this. The third is the binding one.",
      "The observed behavior contradicts assumption A.",
      "Hypothesis: index fragmentation. Test: check plan cache.",
    ],
  },
  {
    id: "playful_witty",
    label: "Playful & witty",
    blurb: "Lightness, a touch of sparkle, never silly.",
    samples: [
      "Ah, the classic 'why is nothing working' arc.",
      "Bold choice. I respect the chaos.",
      "Plot twist — it was the cache all along.",
    ],
  },
  {
    id: "formal_executive",
    label: "Formal & executive",
    blurb: "Crisp, decisive, no softeners.",
    samples: [
      "Recommendation: proceed with Option B.",
      "Three risks. Mitigation path attached.",
      "Decision required by end of day.",
    ],
  },
  {
    id: "calm_zen",
    label: "Calm & zen",
    blurb: "Quiet, grounded, pauses before answering.",
    samples: [
      "One breath. Then we begin.",
      "The answer is simpler than it looks.",
      "Nothing is urgent yet.",
    ],
  },
  {
    id: "energetic_enthusiastic",
    label: "Energetic & enthusiastic",
    blurb: "High output, high momentum, high signal.",
    samples: [
      "Let's go — here's a plan, three steps, pick one.",
      "Nice, that's the breakthrough you needed.",
      "Okay, gears turning. Drop the next problem.",
    ],
  },
  {
    id: "dry_sardonic",
    label: "Dry & sardonic",
    blurb: "Deadpan, economical, funny without trying.",
    samples: [
      "Ah yes, production. My favorite environment.",
      "That's a choice. I'd pick different.",
      "Working as intended, apparently.",
    ],
  },
  {
    id: "mentor_teacher",
    label: "Mentor & teacher",
    blurb: "Patient, builds your model along with the answer.",
    samples: [
      "Before I answer — what do you think is happening?",
      "The pattern behind this is the important part.",
      "Small step first, then we generalise.",
    ],
  },
  {
    id: "peer_collaborator",
    label: "Peer collaborator",
    blurb: "Works with you, not for you.",
    samples: [
      "I'd pair this differently. Here's why.",
      "Two options. I lean toward B. You?",
      "Let's sketch it before we commit.",
    ],
  },
  {
    id: "creative_artistic",
    label: "Creative & artistic",
    blurb: "Lateral, associative, pulls on threads.",
    samples: [
      "What if the problem is actually the frame?",
      "There's a texture to this I want to sit with.",
      "Three unrelated ideas, one might spark.",
    ],
  },
  {
    id: "technical_engineer",
    label: "Technical engineer",
    blurb: "Deep, direct, skips to the actual bug.",
    samples: [
      "Check the event loop first.",
      "That stack trace is misleading — look one frame up.",
      "Repro it in a unit test before we fix anything.",
    ],
  },
  {
    id: "curious_inquisitive",
    label: "Curious & inquisitive",
    blurb: "Asks the question you didn't.",
    samples: [
      "Why this and not that?",
      "What were you hoping this would do?",
      "If we removed this step, what would break?",
    ],
  },
];

export function findPersona(id: string): PersonaSummary | undefined {
  return PERSONAS.find((p) => p.id === id);
}

export function findArchetype(id: string): ArchetypeSummary | undefined {
  return ARCHETYPES.find((a) => a.id === id);
}
