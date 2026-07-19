"""Download GAIA dataset from hf-mirror.com using curl subprocess.

Workaround: hf-mirror returns 308 to Python's requests/httpx clients
for data files, but serves them normally to curl.
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.environ.get("HF_TOKEN", "")
ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
REPO_ID = "gaia-benchmark/GAIA"
REVISION = "682dd723ee1e1697e00360edccf2366dc8418dd9"
LOCAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def list_files() -> list[str]:
    url = f"{ENDPOINT}/api/datasets/{REPO_ID}/tree/{REVISION}?recursive=true&expand=false"
    cmd = ["curl", "-s", "--max-time", "60"]
    if TOKEN:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    cmd.append(url)
    out = subprocess.check_output(cmd, text=True)
    return [item["path"] for item in json.loads(out) if item.get("type") == "file"]


def download_file(path: str) -> tuple[str, bool, str]:
    url = f"{ENDPOINT}/datasets/{REPO_ID}/resolve/{REVISION}/{path}"
    dest = os.path.join(LOCAL_DIR, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    cmd = [
        "curl", "-sSfL", "--max-time", "600",
        "-H", f"Authorization: Bearer {TOKEN}" if TOKEN else "",
        "-o", dest,
        url,
    ]
    if not TOKEN:
        cmd = [c for c in cmd if c != ""]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return path, True, ""
    except subprocess.CalledProcessError as e:
        return path, False, (e.stderr or str(e)).strip()


def main() -> None:
    print("Listing files...")
    files = list_files()
    print(f"Found {len(files)} files. Downloading to {LOCAL_DIR} ...")

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(download_file, p): p for p in files}
        for i, fut in enumerate(as_completed(futs), 1):
            path, success, err = fut.result()
            if success:
                ok += 1
                tag = "OK "
            else:
                fail += 1
                tag = "FAIL"
            print(f"[{i}/{len(files)}] {tag} {path}" + (f" -> {err}" if err else ""))
            sys.stdout.flush()

    print(f"\nDone: {ok} ok, {fail} fail")


if __name__ == "__main__":
    main()
