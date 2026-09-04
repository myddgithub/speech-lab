# Speech Articulation Animation Lab

Interactive browser-based teaching animations for speech articulation and voice production.

## Projects

- `yunmu-anim` — Mandarin finals: tongue position, lip shape, formants, and nasal endings.
- `shengmu-anim` — Mandarin initials: place, manner, voicing, aspiration, and spectral energy.
- `yuanyin-anim` — Vowel production: physiology (resonance cavities) ↔ acoustics (formants/timbre) ↔ hearing (ear sensitivity), driven by a draggable a–i–u vowel triangle.
- `vocal-fold-sim` — vocal-fold vibration and voice-mode simulation.
- `wave-anim` — sound wave in air (longitudinal), compared with water, radio/EM, and seismic waves.
- `tone-anim` — pure & complex tones: additive stacking, timbre = frequency × energy, fundamental = harmonic spacing (missing-fundamental demo).
- `music-acoustics-anim` — musical pitch & tuning: piano keyboard & violin strings (scale/semitones/Hz, linear vs logarithmic rulers), equal temperament vs just intonation (algorithms & cents), harmony as coinciding harmonic series with chord spectra and a beating demo.
- `intonation-lab` — Streamlit F0 / intonation lab: drag pitch, annotate syllables, Praat TextGrid, TD-PSOLA resynthesis.

The shared `pinyin-anim-common` directory contains the vocal-tract drawing and audio helpers used by the initials and finals animations.

## Run locally

Serve this directory with any static HTTP server, then open the project HTML files in a browser. For example:

```bash
python -m http.server 8000
```

Open `/yunmu-anim/`, `/shengmu-anim/`, `/yuanyin-anim/`, `/vocal-fold-sim/`, `/wave-anim/`, `/tone-anim/`, or `/music-acoustics-anim/`.

`intonation-lab` is a Streamlit app (port **8507**), not a static page. Double-click `intonation-lab/一键启动.bat` (Windows) or `intonation-lab/一键启动.command` (macOS). See `intonation-lab/README.md`.

Each animation provides Chinese and English interface modes through the language button.
