import { api, type DictationToken } from "@/lib/api"

/**
 * Wispr Flow's voice API from the browser: the microphone streams to Wispr over a WebSocket with a short-lived token
 * from the app, and Wispr answers with the finished text (filler words gone, self-corrections applied, names spelled
 * from the dictionary). Protocol: https://api-docs.wisprflow.ai/websocket_api
 */

const RATE = 16_000 // Wispr wants 16 kHz mono 16-bit PCM
const PACKET_SECONDS = 1 // ~1 s packets, all the same length
const MAX_SECONDS = 5 * 60

export type DictationContext = {
  kind: "email" | "other"
  before: string
  selected: string
  after: string
}

export type Dictation = {
  /** Stop listening and wait for Wispr's text. */
  finish: () => Promise<string>
  cancel: () => void
}

let cached: (DictationToken & { until: number }) | null = null

async function token(): Promise<DictationToken> {
  if (cached && cached.until > Date.now()) return cached
  const fresh = await api.dictationToken()
  cached = { ...fresh, until: Date.now() + (fresh.expires_in - 60) * 1000 }
  return fresh
}

// Copies each block of microphone samples to the page.
const TAP = `registerProcessor("wispr-tap", class extends AudioWorkletProcessor {
  process(inputs) { const ch = inputs[0][0]; if (ch) this.port.postMessage(ch.slice(0)); return true }
})`

function base64(samples: Int16Array): string {
  const bytes = new Uint8Array(samples.buffer)
  let binary = ""
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(binary)
}

/** One second of microphone audio (at the device's rate) as a 16 kHz int16 packet and its loudness. */
function packet(input: Float32Array): { data: string; volume: number } {
  const out = new Int16Array(RATE * PACKET_SECONDS)
  const step = input.length / out.length
  let sum = 0
  for (let i = 0; i < out.length; i++) {
    const from = Math.floor(i * step)
    const to = Math.max(from + 1, Math.floor((i + 1) * step))
    let v = 0
    for (let j = from; j < to; j++) v += input[j] ?? 0
    v = Math.max(-1, Math.min(1, v / (to - from)))
    sum += v * v
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff
  }
  return { data: base64(out), volume: Math.sqrt(sum / out.length) }
}

export async function startDictation(context: DictationContext, onAutoStop: () => void): Promise<Dictation> {
  const [auth, stream] = await Promise.all([
    token(),
    navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }),
  ])
  const audio = new AudioContext()
  const perPacket = Math.round(audio.sampleRate * PACKET_SECONDS)
  const url = URL.createObjectURL(new Blob([TAP], { type: "application/javascript" }))
  await audio.audioWorklet.addModule(url)
  URL.revokeObjectURL(url)
  const source = audio.createMediaStreamSource(stream)
  const tap = new AudioWorkletNode(audio, "wispr-tap")

  const ws = new WebSocket(`${auth.ws_url}?client_key=${encodeURIComponent(`Bearer ${auth.access_token}`)}`)
  const outbox: string[] = []
  let ready = false
  const send = (message: object) => {
    const text = JSON.stringify(message)
    if (ready) ws.send(text)
    else outbox.push(text)
  }

  let pending = new Float32Array(0)
  let sent = 0
  const flush = (input: Float32Array) => {
    const p = packet(input)
    send({
      type: "append",
      position: sent,
      audio_packets: {
        packets: [p.data],
        volumes: [p.volume],
        packet_duration: PACKET_SECONDS,
        audio_encoding: "wav",
        byte_encoding: "base64",
      },
    })
    sent += 1
  }
  tap.port.onmessage = (e: MessageEvent<Float32Array>) => {
    const next = new Float32Array(pending.length + e.data.length)
    next.set(pending)
    next.set(e.data, pending.length)
    pending = next
    while (pending.length >= perPacket) {
      flush(pending.subarray(0, perPacket))
      pending = pending.slice(perPacket)
    }
  }
  source.connect(tap)

  const stopAudio = () => {
    source.disconnect()
    tap.disconnect()
    tap.port.onmessage = null
    stream.getTracks().forEach((t) => t.stop())
    void audio.close()
  }
  const limit = window.setTimeout(onAutoStop, MAX_SECONDS * 1000)

  let text = ""
  const result = new Promise<string>((resolve, reject) => {
    ws.onopen = () =>
      ws.send(
        JSON.stringify({
          type: "auth",
          access_token: auth.access_token,
          language: ["en"],
          context: {
            app: { name: "Bide Follow-up", type: context.kind },
            dictionary_context: auth.dictionary,
            textbox_contents: {
              before_text: context.before,
              selected_text: context.selected,
              after_text: context.after,
            },
          },
        }),
      )
    ws.onmessage = (e) => {
      const message = JSON.parse(e.data as string)
      if (message.status === "auth") {
        ready = true
        outbox.splice(0).forEach((m) => ws.send(m))
      } else if (message.status === "text") {
        text = message.body?.text ?? text
        if (message.final) resolve(text)
      } else if (message.status === "error" || message.error) {
        reject(new Error(String(message.error ?? "Wispr Flow stopped")))
      }
    }
    ws.onerror = () => reject(new Error("Couldn't reach Wispr Flow"))
    ws.onclose = () => resolve(text)
  })
  result.catch(() => {}) // a failure while still listening surfaces when finishing

  return {
    finish: async () => {
      window.clearTimeout(limit)
      stopAudio()
      if (pending.length) {
        const last = new Float32Array(perPacket) // pad the last packet to the same length as the others
        last.set(pending)
        flush(last)
      }
      send({ type: "commit", total_packets: sent })
      const timeout = new Promise<never>((_, reject) =>
        window.setTimeout(() => reject(new Error("Wispr Flow took too long")), 30_000),
      )
      try {
        return (await Promise.race([result, timeout])).trim()
      } finally {
        ws.close()
      }
    },
    cancel: () => {
      window.clearTimeout(limit)
      stopAudio()
      ws.close()
    },
  }
}
