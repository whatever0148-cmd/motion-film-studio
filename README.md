# Motion Film Studio (a Claude skill)

Make motion graphics videos in code with Claude: launch films, product promos, explainers, animated reels. Free. No After Effects, no Remotion. Includes a renderer (Chrome, frame by frame), real sound design, a quality gate with scanners, and a green-screen laptop mockup.

## Install
**Claude Code (terminal or desktop):** copy this folder to `~/.claude/skills/motion-film-studio` (or `.claude/skills/` inside a project). Start Claude and say: "make me a motion graphics video".
**Claude.ai:** zip this folder (the zip must contain the `motion-film-studio` folder) and add it in the Skills settings (menu names may differ by version). The skill needs a computer where Claude can run commands (Claude Code, or Claude with a code environment); a chat-only Claude cannot render.

## What Claude will ask you
Claude runs a first-run check (Node, ffmpeg, Chrome), then asks what the video is for, whether you have reference videos, sound effects, a voice and music, and what real proof you have. If you have none of these, it tells you the free options and sets them up with you.

## Needs
Node 20+, ffmpeg, Google Chrome (or Chromium), Python 3. About 300 MB for the engine packages. All free.

## Folders
`SKILL.md` the method, `references/` the rules and recipes, `assets/` the engine, scanners, audio tools, mockup tools and a starter scene, `scripts/` setup, doctor, audio, scan and mockup commands.

Made from the SonarANE launch film workflow (a 38 s film, real sound design, laptop reel). Licences: check each sound, font and track you add. Fonts installed by setup are open fonts from Fontsource.
