import urllib.request
import urllib.parse
import json
from typing import List, Dict, Optional


AUR_RPC_URL = "https://aur.archlinux.org/rpc/"


class AURPackage:
    def __init__(self, data: Dict):
        self.name = data.get("Name", "")
        self.version = data.get("Version", "")
        self.description = data.get("Description", "")
        self.maintainer = data.get("Maintainer", "orphan")
        self.votes = data.get("NumVotes", 0)
        self.popularity = data.get("Popularity", 0.0)
        self.out_of_date = data.get("OutOfDate")
        self.first_submitted = data.get("FirstSubmitted", 0)
        self.last_modified = data.get("LastModified", 0)
        self.url = data.get("URL", "")
        self.url_path = data.get("URLPath", "")
        self.depends = data.get("Depends", [])
        self.make_depends = data.get("MakeDepends", [])
        self.opt_depends = data.get("OptDepends", [])
        self.conflicts = data.get("Conflicts", [])
        self.license = data.get("License", [])
        self.keywords = data.get("Keywords", [])
    
    @property
    def aur_url(self) -> str:
        return f"https://aur.archlinux.org/packages/{self.name}"
    
    @property
    def git_clone_url(self) -> str:
        return f"https://aur.archlinux.org/{self.name}.git"
    
    def __repr__(self) -> str:
        return f"AURPackage({self.name} {self.version})"


class AURClient:
    def __init__(self):
        self.base_url = AUR_RPC_URL
    
    def _request(self, params: Dict) -> Dict:
        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}?{query_string}"
        
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to AUR: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid response from AUR: {e}")
    
    def search(self, query: str, by: str = "name-desc") -> List[AURPackage]:
        if not query or len(query) < 2:
            return []
        
        params = {
            "v": "5",
            "type": "search",
            "by": by,
            "arg": query
        }
        
        result = self._request(params)
        
        if result.get("type") == "error":
            raise ValueError(result.get("error", "Unknown error"))
        
        packages = [AURPackage(pkg) for pkg in result.get("results", [])]
        packages.sort(key=lambda p: p.votes, reverse=True)
        return packages
    
    def info(self, package_names: List[str]) -> List[AURPackage]:
        if not package_names:
            return []
        
        query_parts = ["v=5", "type=info"]
        for name in package_names:
            query_parts.append(f"arg[]={urllib.parse.quote(name)}")
        
        url = f"{self.base_url}?{'&'.join(query_parts)}"
        
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to AUR: {e}")
        
        return [AURPackage(pkg) for pkg in data.get("results", [])]
    
    def search_by_name(self, query: str) -> List[AURPackage]:
        return self.search(query, by="name")
    
    def search_by_description(self, query: str) -> List[AURPackage]:
        return self.search(query, by="name-desc")
    
    def search_by_keywords(self, query: str) -> List[AURPackage]:
        return self.search(query, by="keywords")
    
    def search_by_maintainer(self, maintainer: str) -> List[AURPackage]:
        return self.search(maintainer, by="maintainer")
