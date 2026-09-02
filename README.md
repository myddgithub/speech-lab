# Speech Articulation Animation Lab

Interactive browser-based teaching animations for speech articulation and voice production.

## Projects

- `yunmu-anim` — Mandarin finals: tongue position, lip shape, formants, and nasal endings.
- `shengmu-anim` — Mandarin initials: place, manner, voicing, aspiration, and spectral energy.
- `vocal-fold-sim` — vocal-fold vibration and voice-mode simulation.
- `intonation-lab` — Streamlit F0 / intonation lab: drag pitch, annotate syllables, Praat TextGrid, TD-PSOLA resynthesis.

The shared `pinyin-anim-common` directory contains the vocal-tract drawing and audio helpers used by the initials and finals animations.

## Run locally

Serve this directory with any static HTTP server, then open the project HTML files in a browser. For example:

```bash
python -m http.server 8000
```

Open `/yunmu-anim/`, `/shengmu-anim/`, or `/vocal-fold-sim/`.

`intonation-lab` is a Streamlit app (port **8507**), not a static page. See `intonation-lab/README.md`.

Each animation provides Chinese and English interface modes through the language button.
