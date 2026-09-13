#!/usr/bin/env python3
"""Local environment management: start / stop / reset / smoke.

LOCAL-ONLY by construction (D-053): every destructive operation here
is prefixed `local-` and refuses to run outside the local machine
(no staging/production targets exist in this script).

Current machine reality (2026-09-13): Docker Desktop is not installed.
Commands degrade gracefully and explain exactly what is needed — no
hidden failure (RULES §41).
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COMPOSE_FILE = os.path.join(ROOT, "local", "infra", "docker-compose.yml")
PROJECT = "engine-local"


def _have(*bins) -> bool:
    return all(shutil.which(b) for b in bins)


def _die(msg: str) -> int:
    print(f"ERROR: {msg}")
    return 1


def _docker():
    if not _have("docker"):
        print(_docker_hint())
        return None
    return "docker"


def _docker_hint() -> str:
    return (
        "Docker is not available on this machine yet.\n"
        "  Install Docker Desktop for Mac (or colima + docker CLI),\n"
        "  then re-run: python3 local/scripts/local_env.py up\n"
        "Everything else (canonical logic, schema, seeds, tests, mock,\n"
        "media, fixtures) is runnable right now without Docker."
    )


def compose(*args: str) -> int:
    if _docker() is None:
        return 1
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT,
           *args]
    print("$", " ".join(cmd))
    return subprocess.run(cmd).returncode


def up() -> int:
    if _docker() is None:
        return 1
    rc = compose("up", "-d", "--wait")
    if rc == 0:
        print("Local stack is up. Seeding vocabulary...")
        rc = subprocess.run(
            [sys.executable, os.path.join(HERE, "seed_registry.py")]
        ).returncode
        print("Run the smoke test: python3 local/scripts/smoke_test.py")
    return rc


def stop() -> int:
    return compose("stop")


def down() -> int:
    return compose("down")  # keeps volumes


def reset_volumes() -> int:
    """DESTRUCTIVE — LOCAL VOLUMES ONLY. Deletes: engine-local Woo DB,
    canonical DB, n8n data, media objects, mock state. Then recreates
    and reseeds. Never touches anything beyond this machine."""
    print("=" * 62)
    print("LOCAL-ONLY DESTRUCTIVE RESET")
    print("Deletes (on THIS machine only):")
    print("  - docker volumes: engine-local_woo_data,")
    print("    engine-local_canonical_data, engine-local_n8n_data,")
    print("    engine-local_media_data, engine-local_mock_state")
    print("  - all local test data in them")
    print("Then recreates the stack and reseeds approved vocabulary.")
    print("=" * 62)
    answer = input("Type 'RESET-LOCAL' to continue: ").strip()
    if answer != "RESET-LOCAL":
        print("Aborted.")
        return 1
    if _docker() is None:
        return 1
    rc = compose("down", "-v")
    if rc == 0:
        mock_state = os.path.join(ROOT, "local", "volumes", "mock-woo",
                                  "state.json")
        if os.path.exists(mock_state):
            os.remove(mock_state)
        rc = up()
    return rc


def status() -> int:
    return compose("ps")


def main() -> int:
    cmds = {
        "up": up, "stop": stop, "down": down, "status": status,
        "reset-volumes": reset_volumes,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(f"usage: local_env.py {'|'.join(cmds)}")
        if _docker() is None:
            print(_docker_hint())
        return 2
    return cmds[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
