#!/bin/bash

# Log file for debugging
LOG_FILE="application.log"

# Function to log messages
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check if xvfb-run is available
if command -v xvfb-run &> /dev/null; then
    log "Using xvfb-run for virtual display."

    # Set the DISPLAY environment variable explicitly
    export DISPLAY=:99

    # Run the application with xvfb-run
    xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" dotnet NetworkMonitorProcessor-debian12.dll 2>&1 | tee -a "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
else
    log "xvfb-run not found. Running directly."

    # Run the application directly
    dotnet NetworkMonitorProcessor-debian12.dll 2>&1 | tee -a "$LOG_FILE"
    EXIT_CODE=$?
fi

# Check the exit code and log the result
if [ $EXIT_CODE -eq 0 ]; then
    log "Application completed successfully."
else
    log "Application failed with exit code $EXIT_CODE."
fi

exit $EXIT_CODE
