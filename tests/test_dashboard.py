import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


class DashboardRegressionTests(unittest.TestCase):
    def test_html_ids_are_unique(self):
        ids = re.findall(r'\bid="([^"]+)"', HTML)
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        self.assertEqual(duplicates, [], f"Duplicate HTML IDs: {duplicates}")

    def test_all_fragment_links_have_targets(self):
        ids = set(re.findall(r'\bid="([^"]+)"', HTML))
        targets = re.findall(r'href="#([^"]+)"', HTML)
        missing = sorted(set(targets) - ids)
        self.assertEqual(missing, [], f"Broken fragment links: {missing}")

    def test_each_dashboard_tab_has_a_panel(self):
        tabs = re.findall(r'data-tab="([^"]+)"', HTML)
        panels = re.findall(r'id="tab-([^"]+)"', HTML)
        self.assertEqual(set(tabs), set(panels))
        self.assertTrue(tabs, "No dashboard tabs found")

    def test_sidebar_navigation_activates_tab_before_scroll(self):
        self.assertIn("sidebarTabByTarget", HTML)
        for target in (
            "sharesPanel",
            "hashrateHistoryPanel",
            "blockHistoryPanel",
            "electricityPanel",
            "diagnosticsPanel",
            "troubleshootingAgentPanel",
            "setupPanel",
        ):
            self.assertIn(f"{target}:", HTML)
        self.assertIn("selectTab(tabName,false)", HTML)
        self.assertIn("target.scrollIntoView", HTML)

    def test_theme_toggle_and_persistence_are_present(self):
        self.assertIn('id="themeToggle"', HTML)
        self.assertIn("bchn-solo-dashboard-theme", HTML)
        self.assertIn("dark-mode", HTML)


if __name__ == "__main__":
    unittest.main()

    def test_dashboard_numeric_parser_keeps_missing_values_missing(self):
        self.assertIn("if(value===null||value===undefined||value==='')return null;", HTML)

    def test_pool_log_parser_accepts_space_after_colon(self):
        source = (ROOT / "docker" / "setup_server.py").read_text(encoding="utf-8")
        self.assertIn('re.search(r"Pool:\\s*(\\{.*\\})", line)', source)
