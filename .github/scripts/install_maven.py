"""Install one verified Apache Maven distribution for the CI build."""

import hashlib
import os
from pathlib import Path
import tarfile
import urllib.request


VERSION = "3.9.11"
# https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.tar.gz.sha512
SHA512 = ("bcfe4fe305c962ace56ac7b5fc7a08b87d5abd8b7e89027ab251069faebee516"
          "b0ded8961445d6d91ec1985dfe30f8153268843c89aa392733d1a3ec956c9978")


def main():
    destination = Path(os.environ["RUNNER_TEMP"]) / "pinned-maven"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"apache-maven-{VERSION}-bin.tar.gz"
    url = (f"https://archive.apache.org/dist/maven/maven-3/{VERSION}/binaries/"
           f"apache-maven-{VERSION}-bin.tar.gz")
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    if hashlib.sha512(payload).hexdigest() != SHA512:
        raise RuntimeError("Maven archive checksum does not match the pinned Apache checksum")
    archive.write_bytes(payload)
    with tarfile.open(archive) as distribution:
        distribution.extractall(destination, filter="data")
    with Path(os.environ["GITHUB_PATH"]).open("a", encoding="utf-8") as path_file:
        path_file.write(str(destination / f"apache-maven-{VERSION}" / "bin") + "\n")


if __name__ == "__main__":
    main()
