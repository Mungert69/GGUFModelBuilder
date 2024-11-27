#!/bin/bash

# Check if xvfb-run is available
if command -v xvfb-run &> /dev/null
then
    echo "Using xvfb-run for virtual display."
    xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" dotnet NetworkMonitorProcessor-debian12.dll
else
    echo "xvfb-run not found. Running directly."
    dotnet NetworkMonitorProcessor-debian12.dll
fi

