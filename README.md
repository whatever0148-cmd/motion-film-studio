# Motion Film Studio

**A Claude skill that makes motion graphics videos in code.** Launch films, product promos, explainers and animated reels, rendered frame by frame by Chrome, with real recorded sound design and a measured quality gate. Free. No After Effects, no Remotion, no paid tools.

Made by [@whatever0148-cmd](https://github.com/whatever0148-cmd) from the workflow behind the SonarANE launch film (38 s, voice, sound design, laptop-screen reel).

## What you get
- **A guided start.** Claude checks your computer (Node, ffmpeg, Chrome), then asks what the video is for, whether you have reference videos, sound effects, a voice and music, and what real proof you have. Missing pieces get free options and are set up with you.
- **A renderer.** HTML, Canvas and CSS scenes, deterministic frame by frame, 60 fps, 1080p or 1080x1920.
- **Sound design.** A cue sheet, real recorded sounds, a four-stem mix at -14 LUFS with the voice at least 12 dB over the bed, hits that carry mids so they survive a phone speaker.
- **Four scanners.** Flaw scan, skip-psychology audit, sound QA and a motion lint, with a fix loop and plain pass lines.
- **A laptop mockup.** Put the finished film on a green-screen laptop photo with a chroma matte, perspective warp, masked grade and a virtual camera for a 9:16 reel.
- **Ship notes.** Instagram export spec, caption and hashtag rules, posting plan, AI-label disclosure, all dated and with unverified points marked.

## Install
**Claude Code:**
```bash
git clone https://github.com/whatever0148-cmd/motion-film-studio ~/.claude/skills/motion-film-studio
```
Start Claude and say: *"make me a motion graphics video"*.

**Claude.ai:** download the repository as a ZIP, make sure it contains the `motion-film-studio` folder, and add it in the Skills settings (menu names may differ by version). Rendering needs an environment where Claude can run commands; a chat-only Claude cannot render.

## Requirements
Node 20 or newer, ffmpeg, Google Chrome or Chromium, Python 3. About 300 MB of npm packages. All free. The first run does the checking for you:

```bash
bash scripts/setup.sh ~/motion-studio
python3 scripts/doctor.py ~/motion-studio
```

## Layout
| Path | What it is |
|---|---|
| `SKILL.md` | The method: first-run check, interview, pipeline, hard rules |
| `references/` | Onboarding, craft rules, scene contract, sound and music, reference analysis, QA loop, social shipping, laptop mockup |
| `assets/engine` | The Chrome frame renderer |
| `assets/qa` | Scanners and motion lint |
| `assets/audio` | Cue-sheet to mix tools |
| `assets/mockup` | Green-screen laptop tools |
| `assets/starter` | A small starter scene to copy |
| `scripts/` | `setup`, `doctor`, `make_audio`, `scan_all`, `laptop_mockup` |

## Honest limits
- Scanners measure; they do not watch or listen. Always watch and listen to the result yourself.
- Nothing here guarantees reach. Platform rules change and several are unverified; the references say which.
- Tested end to end on macOS (Apple silicon). Windows and Linux paths exist but are untested.
- Check the licence of every sound, font and track you add.

## Licence
MIT, see `LICENSE`.
