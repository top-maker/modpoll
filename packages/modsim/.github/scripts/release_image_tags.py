"""Choose Docker tags without allowing an older release to replace newer aliases."""

import json
import os
import re
import sys
import urllib.request

VERSION = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def parse_version(tag):
    match = VERSION.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else None


def select_tags(tag, releases):
    version = parse_version(tag)
    if version is None:
        raise ValueError("release tag must be a stable semantic version")
    versions = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        candidate = parse_version(release.get("tag_name", ""))
        if candidate is not None:
            versions.append(candidate)
    if version not in versions:
        raise ValueError("release tag is not a published stable GitHub release")
    tags = ["%d.%d.%d" % version]
    if version == max(v for v in versions if v[0] == version[0]):
        tags.append(str(version[0]))
    if version == max(v for v in versions if v[:2] == version[:2]):
        tags.append("%d.%d" % version[:2])
    is_latest = version == max(versions)
    if is_latest:
        tags.append("latest")
    return tags, is_latest


def fetch_releases():
    api = os.environ["GITHUB_API_URL"].rstrip("/")
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    releases = []
    for page in range(1, 101):
        req = urllib.request.Request(
            "%s/repos/%s/releases?per_page=100&page=%d" % (api, repo, page),
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("GitHub releases response is not a list")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
    raise ValueError("too many release pages to choose tags safely")


def main():
    tags, is_latest = select_tags(os.environ["TAG"], fetch_releases())
    image = "%s/%s/%s" % (
        os.environ["DOCKER_REGISTRY"],
        os.environ["DOCKER_USERNAME"],
        os.environ["IMAGE_NAME"],
    )
    for tag in tags:
        print("%s:%s" % (image, tag))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("latest=%s\n" % str(is_latest).lower())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Cannot select release image tags: %s" % exc, file=sys.stderr)
        sys.exit(1)
