#!/bin/bash

# Check if the playlist actually changed
if git diff --quiet -- playlist.m3u; then
  echo 'Playlist unchanged; skipping repository update.'
  exit 0
fi

# Configure Git using the Render environment variable
git config user.name "render-bot"
git config user.email "bot@render.com"
git remote set-url origin https://${GITHUB_TOKEN}@github.com/Kamidake/Project101.git

# Commit and push the updated files
git add playlist.m3u status.json
git commit -m 'Refresh live playlist from Render'
git push origin main
