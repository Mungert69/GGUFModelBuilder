#!/usr/bin/env bash

# openblas-env.sh
#
# Source this file:
#   source ./openblas-env.sh
#
# It detects the CPU capabilities exposed to the guest and configures
# sensible OpenBLAS runtime/build values.

set -e

flags="$(awk -F: '/^flags[[:space:]]*:/ {print $2; exit}' /proc/cpuinfo)"
model="$(lscpu | sed -n 's/^[[:space:]]*Model name:[[:space:]]*//p')"
vendor="$(lscpu | sed -n 's/^[[:space:]]*Vendor ID:[[:space:]]*//p')"
hypervisor="$(lscpu | sed -n 's/^[[:space:]]*Hypervisor vendor:[[:space:]]*//p')"

vcpus="$(nproc)"

has_flag() {
    grep -qw "$1" <<< "$flags"
}

# ------------------------------------------------------------
# Choose OpenBLAS CPU kernel
# ------------------------------------------------------------

if has_flag avx512f && has_flag fma; then
    OPENBLAS_TARGET="SKYLAKEX"

elif has_flag avx2 && has_flag fma; then
    # Covers Haswell/Broadwell-style AVX2 CPUs.
    OPENBLAS_TARGET="HASWELL"

elif has_flag avx; then
    OPENBLAS_TARGET="SANDYBRIDGE"

elif has_flag sse4_2; then
    OPENBLAS_TARGET="NEHALEM"

else
    OPENBLAS_TARGET="CORE2"
fi


# ------------------------------------------------------------
# Read cache sizes reported by the VM
# ------------------------------------------------------------

cache_kib() {
    local level="$1"
    local dir

    for dir in /sys/devices/system/cpu/cpu0/cache/index*; do
        [[ "$(cat "$dir/level")" == "$level" ]] || continue

        size="$(cat "$dir/size")"

        case "$size" in
            *K)
                echo "${size%K}"
                ;;
            *M)
                echo $(( ${size%M} * 1024 ))
                ;;
        esac

        return
    done
}

REPORTED_L2_KIB="$(cache_kib 2)"
REPORTED_L3_KIB="$(cache_kib 3)"


# ------------------------------------------------------------
# Choose L2 size for OpenBLAS
#
# In virtual machines CPUID cache information may be synthetic.
# Prefer architectural values for known virtual CPU models.
# ------------------------------------------------------------

OPENBLAS_L2_KIB="$REPORTED_L2_KIB"

if [[ -n "$hypervisor" ]] || has_flag hypervisor; then

    case "$model" in

        *Broadwell*|*Haswell*)
            OPENBLAS_L2_KIB=256
            ;;

        *Sandy*|*Ivy*)
            OPENBLAS_L2_KIB=256
            ;;

        *"Skylake-Server"*|*"Skylake Server"*)
            OPENBLAS_L2_KIB=1024
            ;;

        *Skylake*)
            OPENBLAS_L2_KIB=256
            ;;

    esac
fi


# ------------------------------------------------------------
# Threads
# ------------------------------------------------------------

OPENBLAS_THREADS="${OPENBLAS_THREADS:-$vcpus}"


# ------------------------------------------------------------
# Runtime OpenBLAS configuration
# ------------------------------------------------------------

export OPENBLAS_CORETYPE="$OPENBLAS_TARGET"
export OPENBLAS_L2_SIZE="$OPENBLAS_L2_KIB"
export OPENBLAS_NUM_THREADS="$OPENBLAS_THREADS"

# Some software still honours this older OpenBLAS/Goto variable.
export GOTO_NUM_THREADS="$OPENBLAS_THREADS"


# ------------------------------------------------------------
# Build arguments
#
# Usage:
#   make -j"$vcpus" "${OPENBLAS_BUILD_ARGS[@]}"
# ------------------------------------------------------------

OPENBLAS_BUILD_ARGS=(
    "TARGET=$OPENBLAS_TARGET"
    "USE_THREAD=1"
    "NUM_THREADS=$OPENBLAS_THREADS"
    "NO_AFFINITY=1"
)


echo "OpenBLAS configuration"
echo "----------------------"
echo "Vendor:             $vendor"
echo "CPU model:          $model"
echo "Hypervisor:         ${hypervisor:-none}"
echo "vCPUs:              $vcpus"
echo
echo "AVX:                $(has_flag avx  && echo yes || echo no)"
echo "AVX2:               $(has_flag avx2 && echo yes || echo no)"
echo "FMA:                $(has_flag fma  && echo yes || echo no)"
echo "AVX-512:            $(has_flag avx512f && echo yes || echo no)"
echo
echo "OpenBLAS target:     $OPENBLAS_TARGET"
echo "Reported L2:        ${REPORTED_L2_KIB} KiB"
echo "Selected L2:        ${OPENBLAS_L2_KIB} KiB"
echo "Reported L3:        ${REPORTED_L3_KIB} KiB"
echo "OpenBLAS threads:   $OPENBLAS_THREADS"
