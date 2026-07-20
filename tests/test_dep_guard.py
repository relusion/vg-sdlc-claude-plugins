"""Tests for skills/ce-implement/scripts/dep-guard.py.

Covers the Phase-2 ecosystem parsers (NuGet .csproj / Directory.Packages.props, Go go.mod,
Cargo Cargo.toml) plus the offline typosquat corpus, and pins the exit 0/1/2 contract
end-to-end through the CLI against real temp git repos:

    0  PASS  — no undeclared new direct dependency
    1  FAIL  — a new manifest dep the agent did not declare (D1)
    2  ERROR — unparseable manifest / a still-stub ecosystem (Maven/Gradle) changed

Parser unit tests import the module directly; the contract tests run the script exactly
as a gating caller does (subprocess, fully offline). Maven/Gradle stay loud exit-2 stubs.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-implement/scripts/dep-guard.py"
POPULAR = SCRIPT.parent / "popular-packages.json"

_spec = importlib.util.spec_from_file_location("dep_guard_mod", SCRIPT)
dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dg)

GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
)


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60,
    )


def _run_cli(repo, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *args],
        capture_output=True, text=True, env=GIT_ENV, timeout=60,
    )


class _Repo:
    """A throwaway git repo with `files` committed as the base revision (HEAD)."""

    def __init__(self, files):
        self.dir = tempfile.mkdtemp()
        p = Path(self.dir)
        _git(p, "init", "-q")
        for rel, content in files.items():
            fp = p / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
        _git(p, "add", "-A")
        _git(p, "commit", "-q", "-m", "base")

    def write(self, rel, content):
        fp = Path(self.dir) / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# NuGet parser
# ---------------------------------------------------------------------------

class NuGetParser(unittest.TestCase):
    def test_sdk_style_packagereference_include(self):
        xml = (
            '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
            '<PackageReference Include="Newtonsoft.Json" Version="13.0.1"/>'
            '<PackageReference Include="Serilog"/>'
            '</ItemGroup></Project>'
        )
        self.assertEqual(dg.parse_csproj(xml), {"newtonsoft-json", "serilog"})

    def test_legacy_namespaced_project(self):
        xml = (
            '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'
            '<ItemGroup><PackageReference Include="Autofac" Version="6.0"/></ItemGroup></Project>'
        )
        self.assertEqual(dg.parse_csproj(xml), {"autofac"})

    def test_central_package_management_props(self):
        xml = (
            '<Project><ItemGroup>'
            '<PackageVersion Include="xunit" Version="2.4.2"/>'
            '<GlobalPackageReference Include="Nerdbank.GitVersioning" Version="3.5"/>'
            '</ItemGroup></Project>'
        )
        self.assertEqual(dg.parse_csproj(xml), {"xunit", "nerdbank-gitversioning"})

    def test_no_package_references_is_empty(self):
        self.assertEqual(dg.parse_csproj("<Project><PropertyGroup/></Project>"), set())

    def test_malformed_xml_raises(self):
        with self.assertRaises(dg.DepGuardError):
            dg.parse_csproj("<Project><ItemGroup><PackageReference Include=")


# ---------------------------------------------------------------------------
# Go parser
# ---------------------------------------------------------------------------

class GoModParser(unittest.TestCase):
    def test_single_line_and_block_require(self):
        text = (
            "module example.com/x\n"
            "go 1.21\n"
            "require github.com/pkg/errors v0.9.1\n"
            "require (\n"
            "    github.com/gin-gonic/gin v1.9.1\n"
            "    github.com/stretchr/testify v1.8.0\n"
            ")\n"
        )
        self.assertEqual(
            dg.parse_gomod(text),
            {"github-com/pkg/errors", "github-com/gin-gonic/gin", "github-com/stretchr/testify"},
        )

    def test_indirect_deps_dropped_but_other_comments_kept(self):
        text = (
            "require (\n"
            "    golang.org/x/sync v0.3.0 // indirect\n"
            "    github.com/rs/zerolog v1.29.0 // pinned for CVE fix\n"
            ")\n"
        )
        # indirect dropped; the CVE-comment dep stays
        self.assertEqual(dg.parse_gomod(text), {"github-com/rs/zerolog"})

    def test_full_line_comment_and_blank_ignored(self):
        text = "// a comment\n\nrequire github.com/spf13/cobra v1.7.0\n"
        self.assertEqual(dg.parse_gomod(text), {"github-com/spf13/cobra"})


# ---------------------------------------------------------------------------
# Cargo parser
# ---------------------------------------------------------------------------

class CargoParser(unittest.TestCase):
    def test_all_dependency_tables(self):
        text = (
            '[dependencies]\nserde = "1.0"\ntokio = { version = "1", features = ["full"] }\n'
            '[dev-dependencies]\ncriterion = "0.5"\n'
            '[build-dependencies]\ncc = "1.0"\n'
            '[workspace.dependencies]\nanyhow = "1"\n'
            '[target.\'cfg(unix)\'.dependencies]\nnix = "0.27"\n'
        )
        self.assertEqual(
            dg.parse_cargo(text),
            {"serde", "tokio", "criterion", "cc", "anyhow", "nix"},
        )

    def test_package_rename_resolves_to_real_crate(self):
        # local alias `myrand` maps to the real registry crate `rand` — the typosquat target
        text = '[dependencies]\nmyrand = { package = "rand", version = "0.8" }\n'
        parsed = dg.parse_cargo(text)
        self.assertIn("rand", parsed)
        self.assertNotIn("myrand", parsed)

    def test_malformed_toml_raises(self):
        with self.assertRaises(dg.DepGuardError):
            dg.parse_cargo("[dependencies\nserde = ")


# ---------------------------------------------------------------------------
# classify / ecosystem routing
# ---------------------------------------------------------------------------

class ClassifyRouting(unittest.TestCase):
    def test_new_ecosystems_route_to_parsers(self):
        self.assertEqual(dg.classify("src/App/App.csproj"), "nuget")
        self.assertEqual(dg.classify("Directory.Packages.props"), "nuget")
        self.assertEqual(dg.classify("go.mod"), "go")
        self.assertEqual(dg.classify("Cargo.toml"), "cargo")

    def test_maven_gradle_stay_stubs(self):
        self.assertEqual(dg.classify("pom.xml"), "STUB:maven")
        self.assertEqual(dg.classify("build.gradle"), "STUB:gradle")
        self.assertEqual(dg.classify("build.gradle.kts"), "STUB:gradle")

    def test_ecosystem_of(self):
        self.assertEqual(dg.ecosystem_of("nuget"), "nuget")
        self.assertEqual(dg.ecosystem_of("go"), "go")
        self.assertEqual(dg.ecosystem_of("cargo"), "cargo")
        self.assertEqual(dg.ecosystem_of("npm"), "npm")
        self.assertEqual(dg.ecosystem_of("pypi-requirements"), "pypi")


# ---------------------------------------------------------------------------
# typosquat corpus
# ---------------------------------------------------------------------------

class TypoCorpus(unittest.TestCase):
    def test_load_popular_has_five_ecosystems(self):
        pop = dg.load_popular(None)
        self.assertEqual(set(pop), {"npm", "pypi", "nuget", "go", "cargo"})
        for eco in pop:
            self.assertIsInstance(pop[eco], set)
            self.assertLessEqual(len(pop[eco]), 500, f"{eco} corpus exceeds 500")
            self.assertTrue(pop[eco], f"{eco} corpus is empty")

    def test_class_typos_flag_in_every_ecosystem(self):
        pop = dg.load_popular(None)
        cases = {
            "npm": ("loadsh", "lodash"),
            "pypi": ("reqeusts", "requests"),
            "nuget": ("Newtonsoft.Jsonn", "newtonsoft-json"),
            "cargo": ("tokoi", "tokio"),
            "go": ("github.com/gin-gonic/gine", "github-com/gin-gonic/gin"),
        }
        for eco, (typo, expect) in cases.items():
            hit = dg.typo_match(dg._norm(typo), eco, pop)
            self.assertEqual(hit, expect, f"{eco}: {typo} should flag {expect}, got {hit}")

    def test_exact_popular_name_never_flags(self):
        pop = dg.load_popular(None)
        for eco, name in [("npm", "lodash"), ("pypi", "requests"), ("cargo", "serde")]:
            self.assertIsNone(dg.typo_match(dg._norm(name), eco, pop))

    def test_false_positive_rate_stays_bounded(self):
        # ~50 real, legitimate dependency adds across all five ecosystems (not typos).
        # Recorded measurement at generation: 2/52 flags (~1 per 26 adds), under the
        # ~1-per-25 target. This guards against a corpus regeneration that blows the
        # advisory false-positive rate up (a noisy gate gets ignored).
        pop = dg.load_popular(None)
        legit = [
            ("npm", "zod"), ("npm", "vitest"), ("npm", "drizzle-orm"), ("npm", "pino"),
            ("npm", "fastify"), ("npm", "tsx"), ("npm", "tsup"), ("npm", "nanoid"),
            ("npm", "zustand"), ("npm", "valtio"), ("npm", "undici"), ("npm", "hono"),
            ("npm", "kysely"), ("npm", "ky"),
            ("pypi", "polars"), ("pypi", "duckdb"), ("pypi", "httpcore"), ("pypi", "orjson"),
            ("pypi", "loguru"), ("pypi", "structlog"), ("pypi", "typer"), ("pypi", "ruff"),
            ("pypi", "litestar"), ("pypi", "asyncpg"), ("pypi", "tenacity"), ("pypi", "marshmallow"),
            ("nuget", "Dapper"), ("nuget", "Polly"), ("nuget", "MediatR"), ("nuget", "FluentValidation"),
            ("nuget", "Serilog.Sinks.Seq"), ("nuget", "Refit"), ("nuget", "Scrutor"), ("nuget", "Bogus"),
            ("nuget", "Hangfire"), ("nuget", "MassTransit"),
            ("cargo", "axum"), ("cargo", "reqwest"), ("cargo", "clap"), ("cargo", "tonic"),
            ("cargo", "sqlx"), ("cargo", "tracing"), ("cargo", "rayon"), ("cargo", "dashmap"),
            ("cargo", "indexmap"), ("cargo", "bytes"),
            ("go", "github.com/samber/mo"), ("go", "github.com/uptrace/bun"),
            ("go", "github.com/go-kit/kit"), ("go", "entgo.io/ent"),
            ("go", "connectrpc.com/connect"), ("go", "github.com/gofiber/storage"),
        ]
        flags = [
            (eco, name) for eco, name in legit
            if dg.typo_match(dg._norm(name), eco, pop) is not None
        ]
        # comfortably bounds the measured 2 while catching a gross regression
        self.assertLessEqual(
            len(flags), 4,
            f"false-positive rate regressed: {len(flags)}/{len(legit)} legit adds flagged: {flags}",
        )


# ---------------------------------------------------------------------------
# exit 0/1/2 contract, end-to-end through the CLI
# ---------------------------------------------------------------------------

class NuGetContract(unittest.TestCase):
    def setUp(self):
        base = (
            '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
            '<PackageReference Include="Newtonsoft.Json" Version="13.0.1"/>'
            '</ItemGroup></Project>'
        )
        self.repo = _Repo({"src/App/App.csproj": base})
        head = base.replace(
            "</ItemGroup>",
            '<PackageReference Include="Serilog" Version="3.0.1"/></ItemGroup>',
        )
        self.repo.write("src/App/App.csproj", head)

    def tearDown(self):
        self.repo.cleanup()

    def test_undeclared_new_dep_fails(self):
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "unrelated", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "fail")
        self.assertEqual([a["ecosystem"] for a in out["added"]], ["nuget"])
        self.assertTrue(any("D1 serilog" in h for h in out["hard_failures"]))

    def test_declared_new_dep_passes(self):
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "Serilog", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "pass")

    def test_cumulative_declared_set_covers_prior_and_later_features(self):
        # A sequential uncommitted run always diffs from Stage 0. The prior
        # feature's Serilog addition remains authorized; a later Polly addition
        # stays red until the cumulative verified set includes both names.
        current = (Path(self.repo.dir) / "src/App/App.csproj").read_text()
        self.repo.write(
            "src/App/App.csproj",
            current.replace(
                "</ItemGroup>",
                '<PackageReference Include="Polly" Version="8.4.0"/></ItemGroup>',
            ),
        )
        missing_later = _run_cli(
            self.repo.dir, "--base", "HEAD", "--declared", "Serilog", "--json")
        self.assertEqual(missing_later.returncode, 1, missing_later.stdout)
        self.assertTrue(any(
            "D1 polly" in finding
            for finding in json.loads(missing_later.stdout)["hard_failures"]
        ))
        cumulative = _run_cli(
            self.repo.dir, "--base", "HEAD", "--declared", "Serilog,Polly", "--json")
        self.assertEqual(cumulative.returncode, 0, cumulative.stdout + cumulative.stderr)

    def test_malformed_csproj_at_head_errors(self):
        self.repo.write("src/App/App.csproj", "<Project><ItemGroup><PackageReference Include=")
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "x", "--json")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "error")


class GoModContract(unittest.TestCase):
    def setUp(self):
        base = "module example.com/x\ngo 1.21\nrequire github.com/pkg/errors v0.9.1\n"
        self.repo = _Repo({"go.mod": base})
        self.repo.write(
            "go.mod",
            base + "require github.com/gin-gonic/gin v1.9.1\n",
        )

    def tearDown(self):
        self.repo.cleanup()

    def test_undeclared_fails(self):
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "nope", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([a["ecosystem"] for a in out["added"]], ["go"])

    def test_declared_passes(self):
        r = _run_cli(self.repo.dir, "--base", "HEAD",
                     "--declared", "github.com/gin-gonic/gin", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "pass")

    def test_indirect_addition_is_not_a_new_direct_dep(self):
        # adding only an `// indirect` line must not raise a direct-dep add
        base = "module example.com/x\ngo 1.21\nrequire github.com/pkg/errors v0.9.1\n"
        self.repo.write("go.mod", base + "require golang.org/x/sync v0.3.0 // indirect\n")
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["added"], [])


class CargoContract(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "repo"):
            self.repo.cleanup()

    def test_undeclared_fails(self):
        base = '[dependencies]\nserde = "1.0"\n'
        self.repo = _Repo({"Cargo.toml": base})
        self.repo.write("Cargo.toml", base + 'tokio = "1"\n')
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "serde", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([a["name"] for a in out["added"]], ["tokio"])
        self.assertEqual(out["added"][0]["ecosystem"], "cargo")

    def test_rename_declared_by_real_name_passes(self):
        base = '[dependencies]\nserde = "1.0"\n'
        self.repo = _Repo({"Cargo.toml": base})
        self.repo.write("Cargo.toml", base + 'myrand = { package = "rand", version = "0.8" }\n')
        # declaring the real crate name clears it; the local alias would NOT
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "rand", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "pass")

    def test_rename_declared_by_alias_still_fails(self):
        base = '[dependencies]\nserde = "1.0"\n'
        self.repo = _Repo({"Cargo.toml": base})
        self.repo.write("Cargo.toml", base + 'myrand = { package = "rand", version = "0.8" }\n')
        r = _run_cli(self.repo.dir, "--base", "HEAD", "--declared", "myrand", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class StillStubContract(unittest.TestCase):
    def test_changed_maven_manifest_still_exits_2(self):
        repo = _Repo({"pom.xml": "<project><dependencies></dependencies></project>"})
        repo.write("pom.xml", "<project><dependencies><!-- new --></dependencies></project>")
        try:
            r = _run_cli(repo.dir, "--base", "HEAD", "--declared", "x", "--json")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout)["status"], "error")
        finally:
            repo.cleanup()


if __name__ == "__main__":
    unittest.main()
