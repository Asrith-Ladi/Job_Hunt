import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "job_hunt"
EXPECTED_PACKAGES = {
    "api",
    "discovery",
    "gmail",
    "integrations",
    "intelligence",
    "jobs",
    "network",
    "parsers",
    "resumes",
    "runtime",
}


class PackageArchitectureTests(unittest.TestCase):
    def test_feature_modules_are_not_added_back_to_package_root(self):
        root_modules = sorted(path.name for path in PACKAGE_ROOT.glob("*.py"))
        self.assertEqual(root_modules, ["__init__.py"])

    def test_expected_bounded_packages_are_present(self):
        packages = {
            path.name
            for path in PACKAGE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        self.assertEqual(packages, EXPECTED_PACKAGES)

    def test_job_domain_does_not_depend_on_application_features(self):
        forbidden = (
            "job_hunt.api",
            "job_hunt.discovery",
            "job_hunt.gmail",
            "job_hunt.intelligence",
            "job_hunt.network",
            "job_hunt.resumes",
            "job_hunt.runtime",
        )
        violations: list[str] = []
        for path in sorted((PACKAGE_ROOT / "jobs").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                for name in names:
                    if name.startswith(forbidden):
                        violations.append(f"{path.name}: {name}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
