import requests
import re
from urllib.parse import urlparse
from typing import Optional

class WebScraperService:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.headers = {'User-Agent': 'Mozilla/5.0 (compatible; EPIIS-Bot/1.0)'}

    def scrape_url(self, url: str) -> dict:
        try:
            return self._scrape_with_bs4(url)
        except Exception as e:
            return {"success": False, "url": url, "title": None, "content": "", "word_count": 0, "error": str(e)}

    def _scrape_with_bs4(self, url: str) -> dict:
        from bs4 import BeautifulSoup
        from markdownify import markdownify as md
        
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
            tag.decompose()
        
        title = soup.find('title')
        title = title.get_text().strip() if title else urlparse(url).netloc
        
        body = soup.find('main') or soup.find('article') or soup.find('body') or soup
        content = md(str(body), strip=['a', 'img'])
        content = re.sub(r'\n{3,}', '\n\n', content).strip()
        
        return {
            "success": True, "url": url, "title": title,
            "content": content, "word_count": len(content.split()), "error": None
        }

    def is_valid_url(self, url: str) -> bool:
        try:
            r = urlparse(url)
            return all([r.scheme in ('http', 'https'), r.netloc])
        except:
            return False
