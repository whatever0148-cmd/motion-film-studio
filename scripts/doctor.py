#!/usr/bin/env python3
"""Reports what this computer already has for making motion films, and what is missing. Read-only. Usage: doctor.py [workspace]"""
import os, shutil, subprocess, sys, glob
ws = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/motion-studio')
def ok(name, good, hint=''): print(('OK      ' if good else 'MISSING ') + name + ('' if good else '   -> ' + hint)); return good
chromes = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', os.environ.get('CHROME_PATH', '')]
print('Workspace:', ws)
ok('node 20+', bool(shutil.which('node')) and int(subprocess.run(['node', '-v'], capture_output=True, text=True).stdout.strip().lstrip('v').split('.')[0] or 0) >= 20, 'install Node from nodejs.org')
ok('ffmpeg', bool(shutil.which('ffmpeg')), 'brew install ffmpeg (Mac) / winget install ffmpeg (Windows) / sudo apt install ffmpeg (Linux)')
ok('Chrome or Chromium', any(c and os.path.exists(c) for c in chromes), 'install Google Chrome, or set CHROME_PATH')
ok('engine installed', os.path.exists(f'{ws}/direct-engine/node_modules/puppeteer-core'), f'run scripts/setup.sh {ws}')
ok('python venv with numpy', os.path.exists(f'{ws}/.venv/bin/python') or os.path.exists(f'{ws}/.venv/Scripts/python.exe'), f'run scripts/setup.sh {ws}')
refs = [f for e in ('mp4', 'mov', 'webm', 'm4v') for f in glob.glob(f'{ws}/references/*.{e}')]
snd = [f for e in ('wav', 'mp3', 'ogg', 'flac', 'aif', 'aiff') for f in glob.glob(f'{ws}/sounds/**/*.{e}', recursive=True)]
print(f'\nReference videos in {ws}/references: {len(refs)}' + ('' if refs else '   (optional but the biggest quality lever: drop 3 to 5 motion videos you love there)'))
print(f'Sound effects in {ws}/sounds: {len(snd)}' + ('' if snd else '   (add free CC0 sounds, see references/sound-and-music.md)'))
print('Voice: free options are your own recording, macOS "say", or Google AI Studio Gemini TTS (free tier). See references/sound-and-music.md')
