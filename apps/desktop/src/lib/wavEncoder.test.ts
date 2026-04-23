import { describe, expect, it } from "vitest";

import { bytesToBase64, encodeWav, pcmToWavDataUrl } from "./wavEncoder";

function readAscii(bytes: Uint8Array, offset: number, length: number): string {
  let out = "";
  for (let i = 0; i < length; i++) {
    out += String.fromCharCode(bytes[offset + i]);
  }
  return out;
}

function readU32LE(bytes: Uint8Array, offset: number): number {
  return (
    bytes[offset] |
    (bytes[offset + 1] << 8) |
    (bytes[offset + 2] << 16) |
    (bytes[offset + 3] << 24)
  );
}

function readU16LE(bytes: Uint8Array, offset: number): number {
  return bytes[offset] | (bytes[offset + 1] << 8);
}

describe("encodeWav", () => {
  it("writes a valid RIFF/WAVE header for 16 kHz mono", () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1, -1]);
    const out = encodeWav(samples, 16000, 1);

    expect(readAscii(out, 0, 4)).toBe("RIFF");
    expect(readAscii(out, 8, 4)).toBe("WAVE");
    expect(readAscii(out, 12, 4)).toBe("fmt ");
    expect(readAscii(out, 36, 4)).toBe("data");

    expect(readU16LE(out, 20)).toBe(1); // PCM
    expect(readU16LE(out, 22)).toBe(1); // channels
    expect(readU32LE(out, 24)).toBe(16000); // sample rate
    expect(readU16LE(out, 34)).toBe(16); // bit depth

    const dataSize = samples.length * 2;
    expect(readU32LE(out, 40)).toBe(dataSize);
    expect(readU32LE(out, 4)).toBe(36 + dataSize);
    expect(out.length).toBe(44 + dataSize);
  });

  it("clips samples to [-1, 1] before writing int16", () => {
    // +2 and -2 should clamp to +1 and -1 respectively.
    const samples = new Float32Array([2, -2]);
    const out = encodeWav(samples, 16000, 1);
    // +1 maps to 32767 (0x7fff), -1 maps to -32768 (0x8000).
    const first = (out[44] | (out[45] << 8)) << 16 >> 16; // sign-extend
    const second = (out[46] | (out[47] << 8)) << 16 >> 16;
    expect(first).toBe(32767);
    expect(second).toBe(-32768);
  });

  it("rejects nonsense sample rate", () => {
    expect(() => encodeWav(new Float32Array([0]), 0, 1)).toThrow();
    expect(() => encodeWav(new Float32Array([0]), -1, 1)).toThrow();
    expect(() => encodeWav(new Float32Array([0]), NaN, 1)).toThrow();
  });

  it("rejects unsupported channel counts", () => {
    expect(() => encodeWav(new Float32Array([0]), 16000, 0)).toThrow();
    expect(() => encodeWav(new Float32Array([0]), 16000, 3)).toThrow();
  });
});

describe("bytesToBase64", () => {
  it("round-trips ASCII", () => {
    const input = new TextEncoder().encode("Hello, Aether!");
    expect(bytesToBase64(input)).toBe("SGVsbG8sIEFldGhlciE=");
  });

  it("handles bytes with the high bit set without mangling", () => {
    const input = new Uint8Array([0x00, 0x80, 0xff, 0x7f]);
    // Manually computed: AID/fw==
    expect(bytesToBase64(input)).toBe("AID/fw==");
  });
});

describe("pcmToWavDataUrl", () => {
  it("produces a data:audio/wav;base64 URL with a non-trivial body", () => {
    const samples = new Float32Array(128).fill(0.1);
    const url = pcmToWavDataUrl(samples, 16000, 1);
    expect(url.startsWith("data:audio/wav;base64,")).toBe(true);
    const body = url.slice("data:audio/wav;base64,".length);
    // 44-byte header + 256 bytes of int16 samples = 300 bytes,
    // base64 encoded = 400 chars (with no padding needed here).
    expect(body.length).toBeGreaterThanOrEqual(400);
  });

  it("output satisfies the shell-side MIN_UTTERANCE_BODY_LEN = 64", () => {
    const samples = new Float32Array(16).fill(0); // very short
    const url = pcmToWavDataUrl(samples, 16000, 1);
    const body = url.slice("data:audio/wav;base64,".length);
    // Even 16 zero samples + header comfortably exceeds 64 chars of
    // base64 — the validator's floor is about "this is a plausibly
    // real capture", not "this is a long utterance".
    expect(body.length).toBeGreaterThan(64);
  });
});
