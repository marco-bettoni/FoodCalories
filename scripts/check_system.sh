#!/usr/bin/env bash
# FoodCalories hardware / environment preflight.
# Pure shell: no Python packages, no running Ollama service required.
#
# Safe to `source` from scripts that use `set -euo pipefail`.
#
# Usage:
#   ./scripts/check_system.sh              # print report, exit 0
#   source scripts/check_system.sh         # set FC_* variables in caller
#
# Variables set when sourced (and always computed when run):
#   FC_OS_LABEL FC_ARCH_LABEL FC_TOTAL_RAM_GB FC_AVAIL_RAM_GB
#   FC_DISK_AVAIL_GB FC_OLLAMA_CLI FC_MODEL_LOCAL FC_ASSESSMENT
#   FC_ACCEL_NOTE FC_SWAP_USED FC_ASSESS_DETAIL FC_LAB_MSG

_FC_SOURCED=0
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  _FC_SOURCED=1
fi

FC_MODEL_NAME="${OLLAMA_MODEL:-qwen3-vl:4b-instruct}"
FC_LAB_MSG="For reliable performance during the class, use a PolyU laboratory PC with the prepared AI environment."

_fc_round_gb() {
  # Convert bytes to whole GiB (integer). Always succeeds.
  awk -v b="${1:-0}" 'BEGIN { printf "%d", (b / 1024 / 1024 / 1024) + 0.5 }' 2>/dev/null || echo "0"
}

_fc_detect_os() {
  local uname_s
  uname_s="$(uname -s 2>/dev/null || echo unknown)"
  case "$uname_s" in
    Darwin)
      if command -v sw_vers >/dev/null 2>&1; then
        FC_OS_LABEL="macOS $(sw_vers -productVersion 2>/dev/null || echo "")"
      else
        FC_OS_LABEL="macOS"
      fi
      ;;
    Linux)
      if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        FC_OS_LABEL="${PRETTY_NAME:-Linux}"
      else
        FC_OS_LABEL="Linux"
      fi
      ;;
    *)
      FC_OS_LABEL="$uname_s"
      ;;
  esac
}

_fc_detect_arch() {
  local m
  m="$(uname -m 2>/dev/null || echo unknown)"
  case "$m" in
    arm64|aarch64)
      if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
        FC_ARCH_LABEL="Apple Silicon ($m)"
        FC_ACCEL_NOTE="Apple Silicon (Metal via Ollama when available)"
      else
        FC_ARCH_LABEL="ARM64 ($m)"
        FC_ACCEL_NOTE="ARM64 (acceleration depends on Ollama build)"
      fi
      ;;
    x86_64|amd64)
      if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
        FC_ARCH_LABEL="Intel Mac ($m)"
        FC_ACCEL_NOTE="Intel Mac (CPU inference; expect slower runs)"
      else
        FC_ARCH_LABEL="x86_64 ($m)"
        FC_ACCEL_NOTE="x86_64 (GPU acceleration if Ollama detects it)"
      fi
      ;;
    *)
      FC_ARCH_LABEL="$m"
      FC_ACCEL_NOTE="Unknown architecture; acceleration not verified"
      ;;
  esac
}

_fc_detect_ram() {
  FC_TOTAL_RAM_GB="unknown"
  FC_AVAIL_RAM_GB="unknown"
  FC_SWAP_USED="unknown"

  local uname_s
  uname_s="$(uname -s 2>/dev/null || echo unknown)"

  if [[ "$uname_s" == "Darwin" ]]; then
    local memsize pagesize free speculative purgeable avail_pages free_pct swap_line
    memsize=""
    if command -v sysctl >/dev/null 2>&1; then
      memsize="$(sysctl -n hw.memsize 2>/dev/null || true)"
    elif [[ -x /usr/sbin/sysctl ]]; then
      memsize="$(/usr/sbin/sysctl -n hw.memsize 2>/dev/null || true)"
    fi
    if [[ -n "${memsize:-}" ]]; then
      FC_TOTAL_RAM_GB="$(_fc_round_gb "$memsize")"
    fi

    pagesize="4096"
    if command -v pagesize >/dev/null 2>&1; then
      pagesize="$(pagesize 2>/dev/null || echo 4096)"
    elif command -v sysctl >/dev/null 2>&1; then
      pagesize="$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)"
    elif [[ -x /usr/sbin/sysctl ]]; then
      pagesize="$(/usr/sbin/sysctl -n hw.pagesize 2>/dev/null || echo 4096)"
    fi

    free_pct=""
    if command -v memory_pressure >/dev/null 2>&1; then
      free_pct="$(memory_pressure 2>/dev/null | awk -F': ' '/System-wide memory free percentage/ {gsub(/%/,"",$2); print $2; exit}' || true)"
    fi
    if [[ -n "$free_pct" && -n "${memsize:-}" ]]; then
      FC_AVAIL_RAM_GB="$(awk -v m="$memsize" -v p="$free_pct" 'BEGIN { printf "%d", (m * p / 100 / 1024 / 1024 / 1024) + 0.5 }' 2>/dev/null || echo unknown)"
    elif command -v vm_stat >/dev/null 2>&1; then
      free="$(vm_stat 2>/dev/null | awk '/Pages free/ {gsub(/\./,"",$3); print $3; exit}' || true)"
      speculative="$(vm_stat 2>/dev/null | awk '/Pages speculative/ {gsub(/\./,"",$3); print $3; exit}' || true)"
      purgeable="$(vm_stat 2>/dev/null | awk '/Pages purgeable/ {gsub(/\./,"",$3); print $3; exit}' || true)"
      free="${free:-0}"
      speculative="${speculative:-0}"
      purgeable="${purgeable:-0}"
      avail_pages=$((free + speculative + purgeable))
      FC_AVAIL_RAM_GB="$(_fc_round_gb "$((avail_pages * pagesize))")"
    fi

    swap_line=""
    if command -v sysctl >/dev/null 2>&1; then
      swap_line="$(sysctl -n vm.swapusage 2>/dev/null || true)"
    elif [[ -x /usr/sbin/sysctl ]]; then
      swap_line="$(/usr/sbin/sysctl -n vm.swapusage 2>/dev/null || true)"
    fi
    if [[ -n "$swap_line" ]]; then
      FC_SWAP_USED="$(printf '%s\n' "$swap_line" | awk '{
        for (i = 1; i <= NF; i++) if ($i == "used") { print $(i+2); exit }
      }' || true)"
      FC_SWAP_USED="${FC_SWAP_USED:-unknown}"
    fi
  elif [[ -r /proc/meminfo ]]; then
    local total_kb avail_kb swap_used_kb
    total_kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
    avail_kb="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
    swap_used_kb="$(awk '/SwapTotal:/ {t=$2} /SwapFree:/ {f=$2} END {if (t != "") print t-f}' /proc/meminfo 2>/dev/null || true)"
    if [[ -n "${total_kb:-}" ]]; then
      FC_TOTAL_RAM_GB="$(_fc_round_gb "$((total_kb * 1024))")"
    fi
    if [[ -n "${avail_kb:-}" ]]; then
      FC_AVAIL_RAM_GB="$(_fc_round_gb "$((avail_kb * 1024))")"
    fi
    if [[ -n "${swap_used_kb:-}" ]]; then
      FC_SWAP_USED="$(awk -v k="$swap_used_kb" 'BEGIN { printf "%.1fM", k/1024 }' 2>/dev/null || echo unknown)"
    fi
  fi
}

_fc_detect_disk() {
  FC_DISK_AVAIL_GB="unknown"
  local avail_kb
  avail_kb="$(df -k "$HOME" 2>/dev/null | awk 'NR==2 {print $4}' || true)"
  if [[ -n "${avail_kb:-}" ]]; then
    FC_DISK_AVAIL_GB="$(awk -v k="$avail_kb" 'BEGIN { printf "%d", (k / 1024 / 1024) + 0.5 }' 2>/dev/null || echo unknown)"
  fi
}

_fc_detect_ollama() {
  if command -v ollama >/dev/null 2>&1; then
    FC_OLLAMA_CLI="Installed"
  else
    FC_OLLAMA_CLI="Not found"
  fi
}

_fc_model_manifest_present() {
  local name tag base
  name="${FC_MODEL_NAME%%:*}"
  tag="${FC_MODEL_NAME#*:}"
  if [[ "$name" == "$FC_MODEL_NAME" ]]; then
    tag="latest"
  fi
  base="${HOME}/.ollama/models/manifests/registry.ollama.ai/library/${name}"
  if [[ -f "${base}/${tag}" || -d "${base}/${tag}" ]]; then
    return 0
  fi
  base="${HOME}/.ollama/models/manifests/library/${name}"
  if [[ -f "${base}/${tag}" || -d "${base}/${tag}" ]]; then
    return 0
  fi
  return 1
}

_fc_detect_model() {
  if _fc_model_manifest_present; then
    FC_MODEL_LOCAL="Present locally"
  else
    FC_MODEL_LOCAL="Not downloaded"
  fi
}

_fc_assess() {
  FC_ASSESSMENT="UNKNOWN"
  FC_ASSESS_DETAIL=""

  if [[ "$FC_TOTAL_RAM_GB" == "unknown" ]]; then
    FC_ASSESSMENT="UNKNOWN"
    FC_ASSESS_DETAIL="Hardware information could not be detected reliably."
    return 0
  fi

  local total avail
  total="$FC_TOTAL_RAM_GB"
  avail="${FC_AVAIL_RAM_GB:-0}"
  if [[ "$avail" == "unknown" ]]; then
    avail=0
  fi

  if (( total < 8 )); then
    FC_ASSESSMENT="UNSUITABLE"
    FC_ASSESS_DETAIL="Less than 8 GB RAM. Local AI inference is unlikely to be reliable."
  elif (( total == 8 )); then
    FC_ASSESSMENT="LIMITED"
    FC_ASSESS_DETAIL="8 GB RAM. The model may run slowly or cause high memory pressure."
  elif (( total < 16 )); then
    FC_ASSESSMENT="LIMITED"
    FC_ASSESS_DETAIL="Under 16 GB RAM. Expect slower inference under memory pressure."
  else
    FC_ASSESSMENT="OK"
    FC_ASSESS_DETAIL="RAM capacity looks adequate for a 4B vision model."
  fi

  if [[ "$FC_AVAIL_RAM_GB" != "unknown" ]] && (( avail < 4 )) && [[ "$FC_ASSESSMENT" != "UNSUITABLE" ]]; then
    FC_ASSESSMENT="LIMITED"
    FC_ASSESS_DETAIL="Only about ${avail} GB RAM currently free. Close other apps or use a laboratory PC."
  fi

  if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" && "$(uname -m 2>/dev/null || true)" == "x86_64" && "$FC_ASSESSMENT" == "OK" ]]; then
    FC_ASSESSMENT="LIMITED"
    FC_ASSESS_DETAIL="Intel Mac: local vision inference is often slow. Prefer a laboratory PC if interactive speed matters."
  fi
  return 0
}

_fc_print_report() {
  echo
  echo "FoodCalories System Check"
  echo "------------------------------"
  printf "OS:             %s\n" "$FC_OS_LABEL"
  printf "Architecture:   %s\n" "$FC_ARCH_LABEL"
  printf "Total RAM:      %s GB\n" "$FC_TOTAL_RAM_GB"
  printf "Available RAM:  %s GB\n" "$FC_AVAIL_RAM_GB"
  printf "Disk free:      %s GB\n" "$FC_DISK_AVAIL_GB"
  printf "Swap used:      %s\n" "$FC_SWAP_USED"
  printf "Acceleration:   %s\n" "$FC_ACCEL_NOTE"
  printf "Ollama:         %s\n" "$FC_OLLAMA_CLI"
  printf "AI model:       %s (%s)\n" "$FC_MODEL_NAME" "$FC_MODEL_LOCAL"
  echo
  printf "Hardware assessment: %s\n" "$FC_ASSESSMENT"
  if [[ -n "${FC_ASSESS_DETAIL:-}" ]]; then
    echo
    echo "$FC_ASSESS_DETAIL"
  fi
  if [[ "$FC_ASSESSMENT" == "LIMITED" || "$FC_ASSESSMENT" == "UNSUITABLE" ]]; then
    echo
    echo "$FC_LAB_MSG"
  fi
  if [[ "$FC_ASSESSMENT" == "UNKNOWN" ]]; then
    echo
    echo "Hardware could not be assessed automatically. If the app feels slow or unstable, use a PolyU laboratory PC."
  fi
  echo
}

_fc_detect_os
_fc_detect_arch
_fc_detect_ram
_fc_detect_disk
_fc_detect_ollama
_fc_detect_model
_fc_assess

if [[ "$_FC_SOURCED" -eq 0 ]]; then
  _fc_print_report
  exit 0
fi
