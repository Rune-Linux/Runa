import subprocess
from dataclasses import dataclass
from typing import List

from rune.api.aur import AURClient, AURPackage


def _run_pacman(args: List[str]) -> str:
    proc = subprocess.run([
        "pacman",
        *args,
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        msg = proc.stderr.strip() or "pacman command failed"
        raise RuntimeError(msg)
    return proc.stdout


def _vercmp(ver1: str, ver2: str) -> int:

    proc = subprocess.run(
        ["vercmp", ver1, ver2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out = proc.stdout.strip()
    if proc.returncode == 0 and out in {"-1", "0", "1"}:
        return int(out)
    if ver1 == ver2:
        return 0
    return 1 if ver1 > ver2 else -1


@dataclass
class RepoPackage:
    name: str
    version: str
    description: str
    repo: str
    local_version: str


def list_installed_aur() -> List[AURPackage]:
    output = _run_pacman(["-Qm"])
    local_versions = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            version = parts[1]
            local_versions[name] = version
    if not local_versions:
        return []
    client = AURClient()
    packages = client.info(list(local_versions.keys()))
    for pkg in packages:
        setattr(pkg, "local_version", local_versions.get(pkg.name, ""))
    return packages


def list_aur_updates() -> List[AURPackage]:
    installed = list_installed_aur()
    updates = []
    for pkg in installed:
        local = getattr(pkg, "local_version", pkg.version)
        aur_ver = pkg.version
        try:
            if _vercmp(aur_ver, local) > 0:
                updates.append(pkg)
        except Exception:
            continue
    return updates


def list_core_extra_updates() -> List[RepoPackage]:
    output = _run_pacman(["-Qu"])
    updates: List[RepoPackage] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] != "->":
            continue
        name = parts[0]
        local_version = parts[1]
        repo_version = parts[3]
        info = _run_pacman(["-Qi", name])
        repo = ""
        desc = ""
        for info_line in info.splitlines():
            if ":" in info_line:
                key, value = info_line.split(":", 1)
                k = key.strip().lower()
                if "repository" in k:
                    repo = value.strip()
                elif "description" in k:
                    desc = value.strip()
        updates.append(RepoPackage(
            name=name,
            version=repo_version,
            description=desc,
            repo=repo,
            local_version=local_version,
        ))
    return updates


def _get_repo_package_info(name: str, version: str) -> RepoPackage:
    info = _run_pacman(["-Qi", name])
    repo = ""
    desc = ""
    for info_line in info.splitlines():
        if ":" in info_line:
            key, value = info_line.split(":", 1)
            k = key.strip().lower()
            if "repository" in k:
                repo = value.strip()
            elif "description" in k:
                desc = value.strip()
    return RepoPackage(
        name=name,
        version=version,
        description=desc,
        repo=repo,
        local_version=version,
    )


def list_all_installed_packages() -> List[RepoPackage]:
    output = _run_pacman(["-Q"])
    packages: List[RepoPackage] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            version = parts[1]
            packages.append(_get_repo_package_info(name, version))
    return packages


def list_explicit_installed_packages() -> List[RepoPackage]:
    output = _run_pacman(["-Qe"])
    packages: List[RepoPackage] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            version = parts[1]
            packages.append(_get_repo_package_info(name, version))
    return packages


def list_orphan_packages() -> List[RepoPackage]:
    output = _run_pacman(["-Qdt"])
    packages: List[RepoPackage] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            version = parts[1]
            packages.append(_get_repo_package_info(name, version))
    return packages
