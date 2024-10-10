#!/bin/bash

# Check for uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    echo "[$(date)] Uncommitted changes found. Skipping git pull."
    exit 1
fi

# Perform git pull
if git pull origin my-branch; then
    echo "[$(date)] Successfully pulled latest updates from remote."
else
    echo "[$(date)] Git pull failed."
    exit 1
fi

# Continue with the rest of your startup script
source tub-env/bin/activate
cd tubtitles/app
python cuke.py
