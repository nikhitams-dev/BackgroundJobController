from flask import Flask, jsonify, request, render_template
import subprocess
import psutil
import os
import signal
import time
import atexit
import threading

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "commands.conf")

MAX_JOBS = 3

jobs = {}
activity_log = []
lock = threading.RLock()


# -------------------------------
# ACTIVITY LOG
# -------------------------------

def log_activity(message):
    with lock:
        activity_log.insert(0, {
            "message": message,
            "time": time.strftime("%H:%M:%S")
        })

        del activity_log[50:]


# -------------------------------
# LOAD TRUSTED COMMANDS
# -------------------------------

def load_trusted_jobs():
    trusted = {}

    if not os.path.exists(CONFIG_FILE):
        return trusted

    with open(CONFIG_FILE, "r") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "|" in line:
                name, command = line.split("|", 1)
                trusted[name.strip()] = command.strip()

    return trusted


# -------------------------------
# REFRESH JOB STATUS
# -------------------------------

def refresh_jobs():
    with lock:
        for pid, job in jobs.items():

            if job["status"] == "RUNNING":

                if job["process"].poll() is not None:
                    job["status"] = "COMPLETED"
                    log_activity(
                        f"{job['name']} completed (PID {pid})"
                    )


# -------------------------------
# DASHBOARD
# -------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# -------------------------------
# GET ALL JOBS
# -------------------------------

@app.route("/api/jobs")
def get_jobs():
    refresh_jobs()

    with lock:
        result = []

        for pid, job in jobs.items():
            result.append({
                "name": job["name"],
                "pid": pid,
                "status": job["status"]
            })

    return jsonify(result)


# -------------------------------
# START JOB
# -------------------------------

@app.route("/api/start", methods=["POST"])
def start_job():

    data = request.get_json(silent=True) or {}
    name = data.get("name", "")

    trusted = load_trusted_jobs()

    if name not in trusted:
        return jsonify({
            "error": "Job is not authorized"
        }), 403

    refresh_jobs()

    with lock:

        running = sum(
            1 for job in jobs.values()
            if job["status"] == "RUNNING"
        )

        if running >= MAX_JOBS:
            return jsonify({
                "error": "Maximum job limit reached"
            }), 400

        try:
            command = trusted[name]

            process = subprocess.Popen(
                ["bash", "-c", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            pid = str(process.pid)

            jobs[pid] = {
                "name": name,
                "process": process,
                "status": "RUNNING"
            }

            log_activity(
                f"Started {name} (PID {pid})"
            )

            return jsonify({
                "message": "Job started successfully",
                "pid": pid
            })

        except Exception as error:
            return jsonify({
                "error": str(error)
            }), 500


# -------------------------------
# STOP JOB
# -------------------------------

@app.route("/api/stop", methods=["POST"])
def stop_job():

    data = request.get_json(silent=True) or {}
    pid = str(data.get("pid", ""))

    with lock:

        job = jobs.get(pid)

        if not job:
            return jsonify({
                "error": "Job not found"
            }), 404

        if job["status"] != "RUNNING":
            return jsonify({
                "error": "Job is not running"
            }), 400

        process = job["process"]

        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)

            job["status"] = "STOPPED"

            log_activity(
                f"Stopped {job['name']} (PID {pid})"
            )

            return jsonify({
                "message": "Job stopped successfully"
            })

        except subprocess.TimeoutExpired:

            os.killpg(process.pid, signal.SIGKILL)
            process.wait()

            job["status"] = "STOPPED"

            log_activity(
                f"Force stopped {job['name']} (PID {pid})"
            )

            return jsonify({
                "message": "Job force-stopped successfully"
            })

        except ProcessLookupError:

            job["status"] = "COMPLETED"

            return jsonify({
                "error": "Process already finished"
            }), 400


# -------------------------------
# SYSTEM RESOURCE MONITOR
# -------------------------------

@app.route("/api/resources")
def resources():

    return jsonify({
        "cpu": psutil.cpu_percent(interval=0.2),
        "memory": psutil.virtual_memory().percent
    })


# -------------------------------
# ACTIVITY HISTORY
# -------------------------------

@app.route("/api/activity")
def activity():

    with lock:
        return jsonify(activity_log)


# -------------------------------
# AUTOMATIC PROCESS CLEANUP
# -------------------------------

def cleanup_jobs():

    print("\nCleaning up background jobs...")

    with lock:

        for pid, job in jobs.items():

            process = job["process"]

            if process.poll() is None:

                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=3)

                    job["status"] = "STOPPED"

                    print(
                        f"Stopped {job['name']} (PID {pid})"
                    )

                except subprocess.TimeoutExpired:

                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()

                    job["status"] = "STOPPED"

                except ProcessLookupError:
                    job["status"] = "COMPLETED"

    print("All background jobs cleaned up.")


atexit.register(cleanup_jobs)


# -------------------------------
# RUN APPLICATION
# -------------------------------

if __name__ == "__main__":

    print("================================")
    print("       JOBPILOT CONTROLLER")
    print("================================")
    print("Server: http://127.0.0.1:5000")
    print("Maximum concurrent jobs:", MAX_JOBS)
    print("Press CTRL+C to stop the server.")
    print("================================")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )