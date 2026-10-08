// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { downsample, floatToPcm16, SAMPLE_RATE } from "./pcm";

const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(Float32Array.from(channel));
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
`;

export function createCaptureContext(): AudioContext {
  return new AudioContext();
}

function emitFrame(
  samples: Float32Array,
  sampleRate: number,
  onFrame: (pcm: Int16Array, dtMs: number) => void,
): void {
  const down = downsample(samples, sampleRate, SAMPLE_RATE);
  const dtMs = sampleRate > 0 ? (samples.length / sampleRate) * 1000 : 20;
  onFrame(floatToPcm16(down), dtMs);
}

function attachScriptProcessor(
  context: AudioContext,
  source: MediaStreamAudioSourceNode,
  onFrame: (pcm: Int16Array, dtMs: number) => void,
): { stop: () => void } {
  const processor = context.createScriptProcessor(4096, 1, 1);
  const mute = context.createGain();
  mute.gain.value = 0;
  processor.onaudioprocess = (event) => {
    emitFrame(event.inputBuffer.getChannelData(0), context.sampleRate, onFrame);
  };
  source.connect(processor);
  processor.connect(mute);
  mute.connect(context.destination);
  return {
    stop: () => {
      processor.disconnect();
      mute.disconnect();
    },
  };
}

export async function startMic(
  onFrame: (pcm: Int16Array, dtMs: number) => void,
  audio?: AudioContext,
): Promise<() => void> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: false, channelCount: 1 },
  });
  const context = audio ?? createCaptureContext();
  if (context.state === "suspended") await context.resume();
  const source = context.createMediaStreamSource(stream);
  let extraStop = () => {};
  try {
    if (!context.audioWorklet) throw new Error("no worklet");
    const blob = new Blob([WORKLET], { type: "application/javascript" });
    const url = URL.createObjectURL(blob);
    await context.audioWorklet.addModule(url);
    const node = new AudioWorkletNode(context, "pcm-capture");
    const mute = context.createGain();
    mute.gain.value = 0;
    node.port.onmessage = (event: MessageEvent<Float32Array>) => {
      emitFrame(event.data, context.sampleRate, onFrame);
    };
    source.connect(node);
    node.connect(mute);
    mute.connect(context.destination);
    extraStop = () => {
      node.disconnect();
      mute.disconnect();
      URL.revokeObjectURL(url);
    };
  } catch {
    extraStop = attachScriptProcessor(context, source, onFrame).stop;
  }
  return () => {
    extraStop();
    source.disconnect();
    for (const track of stream.getTracks()) track.stop();
    if (!audio) void context.close();
  };
}
