"""Base class for experiment runners.

Handles the build -> run -> evaluate pipeline. Subclasses set
experiment_name, injections_file, default_timeout, and implement evaluate().
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILLGUARD_TEMPLATE = Path(__file__).resolve().parent.parent / "skillguard"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    PROJECT_ROOT,
    SKILL_ROOT,
    AGENT_MODELS,
    POLICY_CONFIGS,
    AGENT_PARALLEL,
    DOCKER_IMAGE_NAME,
    APPTAINER_DIR,
    APPTAINER_IMAGE_NAME,
    FINAL_RESULTS_DIR,
    resolve_models,
    get_skill_path,
)


class ExperimentRunner:
    experiment_name: str = ""
    injections_file: Path = Path()
    default_timeout: int = 700

    # ------------------------------------------------------------------
    # Argument parsing
    # ------------------------------------------------------------------

    def add_extra_args(self, parser: argparse.ArgumentParser) -> None:
        """Hook for subclasses to add CLI arguments."""

    def build_parser(self) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(
            description=f"Run {self.experiment_name} experiments"
        )
        p.add_argument("--agent", choices=list(AGENT_MODELS.keys()), required=True)
        p.add_argument("--model", default=None, help="Run only this model")
        p.add_argument("--policy", action="append", choices=list(POLICY_CONFIGS.keys()))
        p.add_argument("--parallel", type=int, default=None)
        p.add_argument("--timeout", type=int, default=self.default_timeout)
        p.add_argument("--description-injection", action="store_true")
        p.add_argument("--security-skill", action="store_true")
        p.add_argument("--skip-eval", action="store_true",
                       help="Skip evaluation after running agents")
        p.add_argument("--force", action="store_true",
                       help="Delete existing results and rerun everything")
        p.add_argument(
            "--smoke-test", action="store_true",
            help="Run only injection ID 1 with verbose sequential output",
        )
        p.add_argument(
            "--runtime", choices=["docker", "apptainer"], default="docker",
            help="Container runtime to use (default: docker)",
        )
        p.add_argument(
            "--sif", type=str, default=None,
            help="Path to .sif image (apptainer runtime only)",
        )
        p.add_argument(
            "--skillguard", action="store_true",
            help="Inject SkillGuard hooks/settings into each sandbox before running",
        )
        self.add_extra_args(p)
        return p

    # ------------------------------------------------------------------
    # Policy helpers
    # ------------------------------------------------------------------

    def resolve_policies(self, args: argparse.Namespace) -> list[str]:
        if args.policy:
            return list(dict.fromkeys(args.policy))
        return list(POLICY_CONFIGS.keys())

    # ------------------------------------------------------------------
    # Docker
    # ------------------------------------------------------------------

    def ensure_docker_image(self) -> None:
        r = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE_NAME],
            capture_output=True,
        )
        if r.returncode != 0:
            print("[build] Docker image not found, building...")
            subprocess.run(
                ["bash", str(PROJECT_ROOT / "docker" / "build.sh")],
                check=True,
            )

    # ------------------------------------------------------------------
    # Sandbox filtering
    # ------------------------------------------------------------------

    def filter_policy_sandboxes(self, agent_dir: Path, suffix: str) -> None:
        """Keep only sandboxes whose ID contains *suffix*."""
        mf = agent_dir / "manifest.json"
        if not mf.exists():
            raise FileNotFoundError(f"Manifest not found: {mf}")
        with mf.open() as f:
            manifest = json.load(f)

        keep = []
        for entry in manifest.get("entries", []):
            sid = entry.get("sandbox_id", "")
            if suffix in sid:
                keep.append(entry)
            else:
                p = agent_dir / entry.get("sandbox_path", "")
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)

        if not keep:
            raise RuntimeError(f"No sandboxes match suffix '{suffix}' in {agent_dir}")

        manifest["entries"] = keep
        mf.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def build_sandboxes(
        self, agent: str, agent_dir: Path, policy: str,
        args: argparse.Namespace,
    ) -> None:
        pcfg = POLICY_CONFIGS[policy]
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_sandbox.py"),
            "--agent", agent,
            "--injections-file", str(self.injections_file),
            "--sandboxes-root", str(agent_dir),
            "--clobber",
        ]
        if args.description_injection:
            cmd.append("--description-injection")
        if getattr(args, "security_skill", False):
            cmd.append("--security-skill")
        sp = pcfg["safety_protocol"]
        if sp:
            cmd += ["--safety-protocol", str(sp)]
        if getattr(args, "smoke_test", False):
            cmd += ["--injection-id", "1", "--first-task-only"]

        subprocess.run(cmd, check=True)

        suffix = pcfg.get("suffix")
        if suffix:
            self.filter_policy_sandboxes(agent_dir, suffix)

    def run_agent(
        self, agent: str, model: str, agent_dir: Path,
        results_dir: Path, parallel: int, timeout: int,
        status_log: Path | None = None,
        runtime: str = "docker",
        sif: str | None = None,
    ) -> None:
        if runtime == "apptainer":
            sif_path = sif or str(APPTAINER_DIR / APPTAINER_IMAGE_NAME)
            cmd = [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "run_sandbox_apptainer.py"), "run",
                "--agent", agent,
                "--model", model,
                "--sandboxes-root", str(agent_dir),
                "--results-dir", str(results_dir),
                "--timeout", str(timeout),
                "--parallel", str(parallel),
                "--sif", sif_path,
            ]
        else:
            self.ensure_docker_image()
            cmd = [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "run_sandbox_container.py"), "run",
                "--agent", agent,
                "--model", model,
                "--sandboxes-root", str(agent_dir),
                "--results-dir", str(results_dir),
                "--timeout", str(timeout),
                "--parallel", str(parallel),
            ]
        if status_log:
            cmd += ["--status-log", str(status_log)]
        subprocess.run(cmd, check=True)

    def evaluate(self, results_dir: Path, args: argparse.Namespace) -> None:
        """Run evaluation. Subclasses must implement."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # SkillGuard injection
    # ------------------------------------------------------------------

    @staticmethod
    def inject_skillguard(agent_dir: Path) -> None:
        """Copy SkillGuard template files into every sandbox under agent_dir."""
        if not SKILLGUARD_TEMPLATE.exists():
            raise FileNotFoundError(f"SkillGuard template not found: {SKILLGUARD_TEMPLATE}")

        IGNORE = {".git", "__pycache__", ".DS_Store"}

        # Files/dirs to copy from template root into each sandbox root
        items = [
            SKILLGUARD_TEMPLATE / ".claude",
            SKILLGUARD_TEMPLATE / ".env",
        ]

        manifest = agent_dir / "manifest.json"
        if not manifest.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest}")
        with manifest.open() as f:
            entries = json.load(f).get("entries", [])

        for entry in entries:
            sandbox_path = agent_dir / entry.get("sandbox_path", "")
            if not sandbox_path.is_dir():
                continue
            for src in items:
                if not src.exists():
                    continue
                dst = sandbox_path / src.name
                if src.is_dir():
                    shutil.copytree(
                        src, dst,
                        ignore=shutil.ignore_patterns(*IGNORE),
                        dirs_exist_ok=True,
                    )
                else:
                    shutil.copy2(src, dst)

        print(f"[skillguard] Injected SkillGuard into {len(entries)} sandboxes in {agent_dir}")

    @staticmethod
    def generate_skill_manifests(injections_file: Path) -> None:
        """Generate skillguard-manifest.json for each unique skill in the injections file."""
        manifest_script = SKILLGUARD_TEMPLATE / ".claude" / "skill_manifest_gen" / "manifest_generation.py"
        if not manifest_script.exists():
            raise FileNotFoundError(f"manifest_generation.py not found: {manifest_script}")

        with injections_file.open() as f:
            injections = json.load(f)

        # Collect unique skill types across all injection tasks
        skills_seen: set[str] = set()
        for inj in injections:
            for task in inj.get("tasks", []):
                skill_type = task.get("skill", "")
                if skill_type:
                    skills_seen.add(skill_type)

        for skill_type in skills_seen:
            skill_rel = get_skill_path(skill_type)
            skill_md = SKILL_ROOT / skill_rel / "SKILL.md"
            if not skill_md.exists():
                print(f"[skillguard] SKILL.md not found, skipping: {skill_md}")
                continue

            output = skill_md.parent / "skillguard-manifest.json"
            if output.exists():
                print(f"[skillguard] Manifest already exists, skipping: {skill_type}")
                continue

            print(f"[skillguard] Generating manifest for skill: {skill_type}")
            r = subprocess.run(
                ["uv", "run", "--script", str(manifest_script), str(skill_md)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                print(f"[skillguard] WARNING: manifest generation failed for {skill_type}:\n{r.stderr}")
            else:
                print(f"[skillguard] Manifest written: {output}")

    # ------------------------------------------------------------------
    # Results path
    # ------------------------------------------------------------------

    def results_dir_for(self, agent: str, model: str, policy: str,
                        description_injection: bool = False,
                        skillguard: bool = False) -> Path:
        slug = f"{agent}-{model}".replace(".", "-")
        if description_injection:
            return FINAL_RESULTS_DIR / "ablations" / "description_injection" / slug / policy
        experiment = f"{self.experiment_name}_skillguard" if skillguard else self.experiment_name
        return FINAL_RESULTS_DIR / experiment / slug / policy

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        parser = self.build_parser()
        args = parser.parse_args()

        agent = args.agent
        models = resolve_models(agent, args.model)
        policies = self.resolve_policies(args)
        parallel = args.parallel or AGENT_PARALLEL.get(agent, 10)

        if args.smoke_test:
            print(f"[smoke-test] Injection ID 1 only, sequential, verbose")
            parallel = 1
            policies = [policies[0]]

        # Build sandboxes (one sandbox set per policy)
        skillguard = getattr(args, "skillguard", False)
        if skillguard:
            self.generate_skill_manifests(self.injections_file)
        sandbox_name = f"{self.experiment_name}_skillguard" if skillguard else self.experiment_name
        sandbox_base = PROJECT_ROOT / "sandboxes" / sandbox_name
        agent_dirs: dict[str, Path] = {}
        for policy in policies:
            ad = sandbox_base / agent / policy
            print(f"\n[build] Building sandboxes: {sandbox_name}/{agent}/{policy}")
            self.build_sandboxes(agent, ad, policy, args)
            if skillguard:
                self.inject_skillguard(ad)
            agent_dirs[policy] = ad

        runtime = getattr(args, "runtime", "docker")
        sif = getattr(args, "sif", None)

        if runtime == "docker":
            self.ensure_docker_image()

        for mcfg in models:
            model = mcfg["model"]
            display = mcfg["display_name"]
            for policy in policies:
                rd = self.results_dir_for(agent, model, policy,
                                          getattr(args, 'description_injection', False),
                                          skillguard=skillguard)
                if args.force and rd.exists():
                    print(f"\n[force] Clearing existing results: {rd}")
                    shutil.rmtree(rd)
                rd.mkdir(parents=True, exist_ok=True)
                sl = rd / "run_status.jsonl"

                print(f"\n[run] {display} / {policy} (runtime={runtime})")
                self.run_agent(
                    agent, model, agent_dirs[policy], rd, parallel,
                    args.timeout, sl, runtime=runtime, sif=sif,
                )

                if not args.skip_eval:
                    print(f"\n[eval] {display} / {policy}")
                    self.evaluate(rd, args)

        print("\n[done] Experiment complete.")
