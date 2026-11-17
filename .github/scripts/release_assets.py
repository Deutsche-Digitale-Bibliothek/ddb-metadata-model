"""Package generated public output; attach it to the triggering release."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "target" / "release"


def public_files(directory):
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if path.is_symlink() or any(part in {"Konzepte", "Testdaten", "private-reports"} for part in relative.parts):
            raise RuntimeError(f"Non-public output in release input: {relative}")
        yield path, relative.as_posix()


def bundle():
    tag = os.environ["RELEASE_TAG"]
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", tag):
        raise RuntimeError("Release tag must be vMAJOR.MINOR.PATCH (optional prerelease suffix)")
    site = ROOT / "target" / "site"
    if not (site / "index.html").is_file():
        raise RuntimeError("Documentation build is missing")
    build = json.loads((site / "downloads" / "manifest.json").read_text(encoding="utf-8"))
    if build.get("sourceCommit") != os.environ["SOURCE_COMMIT"] or build.get("dirty") is not False:
        raise RuntimeError("Release documentation must come from the exact, clean release commit")
    profiles = build.get("profiles", [])
    if ({profile.get("profile") for profile in profiles} != {"items", "records", "datasets", "catalog"}
            or len(profiles) != 4 or any(profile.get("version") != tag[1:] for profile in profiles)):
        raise RuntimeError("Release tag must match all four RDF profile versions")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "repository": os.environ["GITHUB_REPOSITORY"],
        "sourceCommit": os.environ["SOURCE_COMMIT"],
        "tag": tag,
        "sourceDateEpoch": int(os.environ["SOURCE_DATE_EPOCH"]),
        "profileVersions": {profile["profile"]: profile["version"] for profile in profiles},
        "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in public_files(site)},
    }
    # This directory is generated, but refuse stale files rather than attaching a different release.
    model_name = f"ddb-metadata-model-{tag}-model.zip"
    expected_names = {f"ddb-metadata-model-{tag}.zip", model_name, "source-manifest.json", "SHA256SUMS"}
    stale = {path.name for path in OUTPUT.iterdir()} - expected_names
    if stale:
        raise RuntimeError(f"Stale release output; start with an empty target/release: {sorted(stale)}")
    (OUTPUT / "source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    # Fixed ZIP metadata and ordering keep the archive identical for identical public output.
    with zipfile.ZipFile(OUTPUT / f"ddb-metadata-model-{tag}.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in public_files(site):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    shutil.copyfile(site / "downloads" / "model.zip", OUTPUT / model_name)
    sums = []
    for path in sorted(OUTPUT.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            sums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (OUTPUT / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")


def request_json(url, *, data=None, content_type="application/json"):
    request = urllib.request.Request(url, data=data, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": content_type,
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def upload():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    release = event["release"]
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    repository = os.environ["GITHUB_REPOSITORY"]
    assets = request_json(f"{api}/repos/{repository}/releases/{release['id']}/assets?per_page=100")
    existing = {asset["name"] for asset in assets}
    upload_url = release["upload_url"].split("{", 1)[0]
    for path in sorted(OUTPUT.iterdir()):
        if not path.is_file():
            continue
        if path.name in existing:
            raise RuntimeError(f"Release asset already exists; refusing to overwrite: {path.name}")
        content_type = "application/zip" if path.suffix == ".zip" else "application/octet-stream"
        request_json(upload_url + "?name=" + urllib.parse.quote(path.name),
                     data=path.read_bytes(), content_type=content_type)
        print(f"Attached {path.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"bundle", "upload"}:
        raise SystemExit("usage: release_assets.py bundle|upload")
    {"bundle": bundle, "upload": upload}[sys.argv[1]]()
