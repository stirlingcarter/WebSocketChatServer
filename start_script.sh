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
# Find the latest version of the ICHY script
latest_file=$(ls ICHY-*.py 2>/dev/null | sort -V | tail -n 1)

# Check if the latest_file variable is not empty
if [[ -n "$latest_file" ]]; then
    echo "Running the latest script: $latest_file"
    python "$latest_file"
else
    echo "No ICHY script found."
    exit 1
fi