// @aether/l5-policy-ts — Wave 2 hand-written mirror.
//
// The Rust crate at packages/l5-policy/ is the SOURCE OF TRUTH for every type
// and command surface in this package. This TS mirror exists so L7 and
// apps/desktop can compile against stable contract shapes while the
// Rust-to-TS generator (tools/ts-bindings-gen) is still being built.
//
// Do NOT hand-extend this package after the generator lands. Regenerate.
//
// Primary references:
//   planning/plans/implementation_prep/L5_interface_pack.md
//   planning/DECISION_LOCK_PASS_2026-04-18c.md

export * from "./decision.js";
export * from "./commands.js";

/** Marker — replaced wholesale by generated output in Wave 2+. */
export const L5_TS_MIRROR_WAVE = 2 as const;
