import os
import subprocess
import shutil
from typing import List, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from rune.api.aur import AURPackage


class InstallationError(Exception):
    pass


class PackageInstaller:
    def __init__(self, build_dir: Optional[str] = None):
        self.build_dir = build_dir or os.path.join(
            os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
            "rune-aur-helper"
        )
        os.makedirs(self.build_dir, exist_ok=True)
    
    def _run_command(
        self, 
        cmd: List[str], 
        cwd: str = None,
        password: str = None,
        log_callback: Callable[[str], None] = None
    ) -> int:
        env = os.environ.copy()
        
        if password and cmd[0] == "sudo":
            cmd = ["sudo", "-S", "--"] + cmd[1:]
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            stdout, stderr = process.communicate(input=(password + "\n").encode())
            
            if log_callback:
                output = stdout.decode('utf-8', errors='replace')
                for line in output.splitlines():
                    log_callback(line)
                err_output = stderr.decode('utf-8', errors='replace')
                for line in err_output.splitlines():
                    if not line.startswith('[sudo]') and line.strip():
                        log_callback(line)
            
            return process.returncode
        else:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True
            )
        
            for line in iter(process.stdout.readline, ''):
                if log_callback:
                    log_callback(line.rstrip())
            
            process.wait()
            return process.returncode
    
    def clone_package(
        self, 
        package: "AURPackage", 
        log_callback: Callable[[str], None] = None
    ) -> str:
        """
        Clone an AUR package repository
        
        Returns:
            Path to the cloned package directory
        """
        pkg_dir = os.path.join(self.build_dir, package.name)
        if os.path.exists(pkg_dir):
            shutil.rmtree(pkg_dir)
        
        if log_callback:
            log_callback(f"Cloning {package.name}...")
        
        ret = self._run_command(
            ["git", "clone", "--depth=1", package.git_clone_url, pkg_dir],
            log_callback=log_callback
        )
        
        if ret != 0:
            raise InstallationError(f"Failed to clone {package.name}")
        
        return pkg_dir
    
    def get_dependencies(self, pkg_dir: str) -> List[str]:
        deps = []
        pkgbuild = os.path.join(pkg_dir, "PKGBUILD")
        
        if not os.path.exists(pkgbuild):
            return deps
        
        try:
            result = subprocess.run(
                ["makepkg", "--printsrcinfo"],
                cwd=pkg_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("depends = ") or line.startswith("makedepends = "):
                    dep = line.split(" = ", 1)[1]
                    dep = dep.split(">")[0].split("<")[0].split("=")[0]
                    if dep and dep not in deps:
                        deps.append(dep)
        except Exception:
            pass
        
        return deps
    
    def install_dependencies(
        self,
        deps: List[str],
        password: str,
        log_callback: Callable[[str], None] = None
    ) -> None:
        if not deps:
            return
        
        if log_callback:
            log_callback(f"Installing dependencies: {', '.join(deps)}")
        
        cmd = ["sudo", "pacman", "-S", "--needed", "--noconfirm"] + deps
        ret = self._run_command(
            cmd,
            password=password,
            log_callback=log_callback
        )
        
        if ret != 0 and log_callback:
            log_callback("Note: Some dependencies may need to be installed from AUR first")
    
    def build_package(
        self, 
        pkg_dir: str,
        password: str = None,
        log_callback: Callable[[str], None] = None
    ) -> List[str]:
        deps = self.get_dependencies(pkg_dir)
        if deps:
            self.install_dependencies(deps, password, log_callback)
        
        if log_callback:
            log_callback("Building package with makepkg...")
        
        ret = self._run_command(
            ["makepkg", "-f", "--noconfirm", "--skipchecksums", "--skippgpcheck"],
            cwd=pkg_dir,
            log_callback=log_callback
        )
        
        if ret != 0:
            raise InstallationError("makepkg failed - check if all dependencies are installed")
        
        packages = []
        for f in os.listdir(pkg_dir):
            if f.endswith(".pkg.tar.zst") or f.endswith(".pkg.tar.xz"):
                packages.append(os.path.join(pkg_dir, f))
        
        if not packages:
            raise InstallationError("No packages were built")
        
        return packages
    
    def install_packages(
        self, 
        pkg_files: List[str],
        password: str,
        log_callback: Callable[[str], None] = None
    ) -> None:
        if log_callback:
            log_callback("Installing packages with pacman...")
        
        cmd = ["sudo", "pacman", "-U", "--noconfirm"] + pkg_files
        ret = self._run_command(
            cmd,
            password=password,
            log_callback=log_callback
        )
        
        if ret != 0:
            raise InstallationError("pacman installation failed")
    
    def install_aur_package(
        self, 
        package: "AURPackage",
        password: str,
        log_callback: Callable[[str], None] = None
    ) -> None:
        try:
            pkg_dir = self.clone_package(package, log_callback)
            
            pkg_files = self.build_package(pkg_dir, password, log_callback)
            
            self.install_packages(pkg_files, password, log_callback)
            
            if log_callback:
                log_callback(f"Successfully installed {package.name}!")
                
        except InstallationError:
            raise
        except Exception as e:
            raise InstallationError(f"Installation failed: {e}")
    
    def install_multiple(
        self,
        packages: List["AURPackage"],
        password: str,
        log_callback: Callable[[str], None] = None,
        progress_callback: Callable[[int, int], None] = None
    ) -> dict:
        results = {"success": [], "failed": []}
        total = len(packages)
        
        for i, package in enumerate(packages):
            if progress_callback:
                progress_callback(i + 1, total)
            
            try:
                if log_callback:
                    log_callback(f"\n{'='*50}")
                    log_callback(f"Installing {package.name} ({i+1}/{total})")
                    log_callback(f"{'='*50}\n")
                
                self.install_aur_package(package, password, log_callback)
                results["success"].append(package.name)
                
            except InstallationError as e:
                if log_callback:
                    log_callback(f"ERROR: {e}")
                results["failed"].append((package.name, str(e)))
        
        return results
    
    def check_dependencies(self) -> List[str]:
        missing = []
        
        required = ["git", "makepkg", "pacman"]
        for tool in required:
            if shutil.which(tool) is None:
                missing.append(tool)
        
        return missing
    
    def cleanup(self, package_name: str = None) -> None:
        if package_name:
            pkg_dir = os.path.join(self.build_dir, package_name)
            if os.path.exists(pkg_dir):
                shutil.rmtree(pkg_dir)
        else:
            # Clean all
            if os.path.exists(self.build_dir):
                shutil.rmtree(self.build_dir)
                os.makedirs(self.build_dir, exist_ok=True)
