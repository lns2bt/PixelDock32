"""Protect English page declarations and local documentation navigation."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryDocsTests(unittest.TestCase):
    def test_static_pages_declare_english(self):
        for page in (ROOT/'app/static').glob('*.html'):
            with self.subTest(page=page.name):
                self.assertRegex(page.read_text(), r'<html\s+lang="en"')

    def test_relative_documentation_links_exist(self):
        for page in [ROOT/'README.md', ROOT/'CHANGELOG.md', *(ROOT/'docs').glob('*.md')]:
            for target in re.findall(r'\]\(([^)]+)\)',page.read_text()):
                if target.startswith(('http:','https:','#','/')):continue
                with self.subTest(page=page.name,target=target):
                    self.assertTrue((page.parent/target.split('#')[0]).exists())
