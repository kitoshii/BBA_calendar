#!/bin/bash

set -euo pipefail

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# ===========================
# Default values
# ===========================
EMAILS=${EMAILS-"shahar.barak@gmail.com"}

# ===========================
# Construct command safely
# ===========================
cmd="python3.14 generate_bba_ics.py $@"

# ===========================
# Debug: show what will run
# ===========================
echo "Running command:"
echo ${cmd}
echo

# ===========================
# Execute the command
# ===========================
eval ${cmd}
