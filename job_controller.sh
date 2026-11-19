#!/bin/bash

# JOBPILOT - Background Job Controller

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/commands.conf"
MAX_JOBS=3

declare -A JOB_PIDS
declare -A JOB_NAMES
declare -A JOB_STATUS

# Refresh process status
refresh_status() {
    for pid in "${!JOB_PIDS[@]}"; do

        if [[ "${JOB_STATUS[$pid]}" == "RUNNING" ]]; then
            process_state=$(ps -o stat= -p "$pid" 2>/dev/null)
            process_state="${process_state//[[:space:]]/}"

            if [[ -z "$process_state" || "$process_state" == Z* ]]; then
                wait "$pid" 2>/dev/null
                JOB_STATUS[$pid]="COMPLETED"
            fi
        fi
    done
}

# Start a trusted job
start_job() {
    echo ""
    echo "AVAILABLE JOBS"
    echo "------------------------"

    if [[ ! -f "$CONFIG" ]]; then
        echo "Configuration file not found!"
        return
    fi

    while IFS='|' read -r key value; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        echo "$key"
    done < "$CONFIG"

    read -r -p "Enter job name: " name

    local command=""

    while IFS='|' read -r key value; do
        key="${key//$'\r'/}"
        value="${value//$'\r'/}"

        if [[ "$key" == "$name" ]]; then
            command="$value"
            break
        fi
    done < "$CONFIG"

    if [[ -z "$command" ]]; then
        echo "Job not authorized!"
        return
    fi

    refresh_status

    local count=0

    for pid in "${!JOB_PIDS[@]}"; do
        [[ "${JOB_STATUS[$pid]}" == "RUNNING" ]] && ((count++))
    done

    if (( count >= MAX_JOBS )); then
        echo "Maximum job limit reached!"
        return
    fi

    bash -c "$command" &
    local pid=$!

    JOB_PIDS[$pid]=$pid
    JOB_NAMES[$pid]=$name
    JOB_STATUS[$pid]="RUNNING"

    echo ""
    echo "JOB STARTED SUCCESSFULLY"
    echo "------------------------"
    echo "Job Name : $name"
    echo "Process ID : $pid"
    echo "Status : RUNNING"
}

# Display job status
show_status() {
    refresh_status

    echo ""
    echo "========== JOB STATUS =========="

    if (( ${#JOB_PIDS[@]} == 0 )); then
        echo "No jobs have been started."
        return
    fi

    for pid in "${!JOB_PIDS[@]}"; do
        echo ""
        echo "Job Name : ${JOB_NAMES[$pid]}"
        echo "PID      : $pid"
        echo "Status   : ${JOB_STATUS[$pid]}"
        echo "--------------------------------"
    done
}

# Stop a job
stop_job() {
    refresh_status

    echo ""
    read -r -p "Enter PID to stop: " pid

    if [[ ! -v JOB_PIDS[$pid] ]]; then
        echo "Invalid PID!"
        return
    fi

    if [[ "${JOB_STATUS[$pid]}" != "RUNNING" ]]; then
        echo "Job is already finished."
        return
    fi

    kill "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null

    JOB_STATUS[$pid]="STOPPED"

    echo "Job stopped successfully!"
}

# Main menu
while true; do

    echo ""
    echo "================================"
    echo "       JOBPILOT CONTROLLER"
    echo "================================"
    echo "1. Start Job"
    echo "2. View Job Status"
    echo "3. Stop Job"
    echo "4. Exit"
    echo "================================"

    read -r -p "Enter choice: " choice

    case "$choice" in
        1) start_job ;;
        2) show_status ;;
        3) stop_job ;;
        4)
            echo "Exiting JobPilot..."
            exit 0
            ;;
        *)
            echo "Invalid choice! Enter 1-4."
            ;;
    esac

done