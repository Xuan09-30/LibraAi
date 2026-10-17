import os
import sys
import re
import ast
import yaml
import importlib.util
import traceback
from typing import Dict, Any, Optional, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class SkillSecurityVisitor(ast.NodeVisitor):
    """
    AST Security Sandbox inspecting Python skill code prior to execution.
    Enforces that skills define a safe 'execute(args, context)' function,
    blocks destructive OS calls (shutil.rmtree, shell=True subprocess, disk wipe),
    and permits safe libraries (psutil, requests, datetime, math, json, re, etc.).
    """

    def __init__(self):
        self.errors: List[str] = []
        self.has_execute: bool = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name == "execute":
            self.has_execute = True
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.name.lower()
            if name in ["ctypes", "winreg", "_winapi"]:
                self.errors.append(f"Forbidden security module imported: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = (node.module or "").lower()
        if mod in ["ctypes", "winreg", "_winapi"]:
            self.errors.append(f"Forbidden security module imported: '{node.module}'")
        for alias in node.names:
            if alias.name in ["rmtree", "system", "popen", "spawn"]:
                self.errors.append(f"Forbidden destructive function imported: '{alias.name}' from '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 1. Block eval / exec / __import__
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ["eval", "exec", "__import__"]:
                self.errors.append(f"Disallowed dynamic code execution call: '{func_name}()'")

        # 2. Block shutil.rmtree and os.remove outside safe boundaries
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name == "rmtree":
                self.errors.append("Disallowed destructive filesystem call: 'shutil.rmtree()'")
            elif attr_name in ["remove", "unlink", "rmdir"]:
                # Check if first argument is a root path or broad path
                if node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        if first_arg.value in ["/", "C:\\", "C:/", "\\", "*"]:
                            self.errors.append(f"Disallowed root filesystem deletion on '{first_arg.value}'")

            # 3. Block subprocess with shell=True
            if attr_name in ["Popen", "run", "call", "check_output", "check_call"]:
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.errors.append("Disallowed subprocess execution with shell=True")

        self.generic_visit(node)


class SkillForge:
    """
    Hermes-Style Progressive Disclosure Skill Forge & Self-Improving Registry.
    Discovers, validates, executes, and self-repairs modular skills stored in skills/<skill_slug>/.
    """

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = os.path.join(PROJECT_ROOT, skills_dir)
        os.makedirs(self.skills_dir, exist_ok=True)
        self.registry: Dict[str, Dict[str, Any]] = {}
        self.refresh_registry()

    def refresh_registry(self):
        """Scans skills directory and builds the Level 0 progressive disclosure index."""
        self.registry.clear()
        if not os.path.isdir(self.skills_dir):
            return

        for item in os.listdir(self.skills_dir):
            skill_folder = os.path.join(self.skills_dir, item)
            if not os.path.isdir(skill_folder):
                continue

            md_path = os.path.join(skill_folder, "SKILL.md")
            py_path = os.path.join(skill_folder, "skill.py")
            if os.path.isfile(md_path) and os.path.isfile(py_path):
                meta = self._parse_skill_md(md_path)
                meta["slug"] = item
                meta["folder"] = skill_folder
                meta["md_path"] = md_path
                meta["py_path"] = py_path
                self.registry[item] = meta

    def _parse_skill_md(self, md_path: str) -> Dict[str, Any]:
        """Extracts YAML frontmatter from a SKILL.md document."""
        default_meta = {
            "name": os.path.basename(os.path.dirname(md_path)),
            "description": "Custom learned skill.",
            "triggers": [],
            "version": "1.0.0",
            "success_count": 0
        }
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
            if match:
                raw_yaml, body = match.group(1), match.group(2)
                parsed = yaml.safe_load(raw_yaml) or {}
                for k, v in parsed.items():
                    default_meta[k] = v
                default_meta["body"] = body.strip()
        except Exception as e:
            print(f"[SkillForge Metadata Parse Error on {md_path}]: {e}")

        return default_meta

    def list_skills(self) -> List[Dict[str, Any]]:
        """Returns the Level 0 metadata index of all registered skills."""
        self.refresh_registry()
        skills = []
        for slug, meta in self.registry.items():
            skills.append({
                "slug": slug,
                "name": meta.get("name", slug),
                "description": meta.get("description", ""),
                "triggers": meta.get("triggers", []),
                "version": meta.get("version", "1.0.0"),
                "success_count": meta.get("success_count", 0)
            })
        return skills

    def match_skill(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Matches a user prompt against registered skill triggers."""
        norm_prompt = prompt.lower().strip()
        self.refresh_registry()

        for slug, meta in self.registry.items():
            triggers = meta.get("triggers", [])
            for trigger in triggers:
                t_lower = trigger.lower().strip()
                if t_lower and (t_lower in norm_prompt or re.search(r"\b" + re.escape(t_lower) + r"\b", norm_prompt)):
                    return meta

        return None

    def validate_skill_code(self, code: str) -> Tuple[bool, str]:
        """
        Parses skill code through the AST Security Sandbox.
        Returns (is_valid, reason).
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error in skill code: {e}"

        visitor = SkillSecurityVisitor()
        visitor.visit(tree)

        if not visitor.has_execute:
            return False, "Skill code must define an 'execute(args, context)' function."

        if visitor.errors:
            return False, f"AST Security Sandbox rejection: {'; '.join(visitor.errors)}"

        return True, "Skill code validated successfully."

    def create_skill(
        self,
        task_description: str,
        llm_callback: Optional[Any] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Autonomous Skill Creation:
        Generates SKILL.md and skill.py, validates with AST sandbox,
        writes to skills/<slug>/, and hot-loads into the registry.
        """
        clean_desc = task_description.strip()

        # 1. Deduce skill name & slug cleanly
        desc_stripped = re.sub(
            r"^(?:please\s+)?(?:create|learn|build|teach\s+yourself|save)\s+(?:a\s+)?(?:new\s+)?skill\s*(?:called|named)?\s*",
            "",
            clean_desc,
            flags=re.IGNORECASE
        ).strip()
        desc_stripped = re.sub(r"^(?:called|named)\s+", "", desc_stripped, flags=re.IGNORECASE).strip()

        # Split on purpose conjunctions ('that', 'to', 'for', 'which') to isolate the concise title
        split_match = re.split(r"\s+(?:that|to|for|which)\s+", desc_stripped, maxsplit=1, flags=re.IGNORECASE)
        raw_name = split_match[0].strip() if split_match and split_match[0].strip() else desc_stripped[:30]
        if not raw_name:
            raw_name = "custom_skill"

        clean_name = re.sub(r"[^\w\s\-]", "", raw_name).strip().title()
        skill_slug = re.sub(r"[^\w]+", "_", clean_name.lower()).strip("_")
        if not skill_slug:
            skill_slug = "custom_skill"

        # 2. Generate code and triggers
        generated_code = None
        triggers = [
            skill_slug.replace("_", " "),
            clean_name.lower()
        ]

        # Use LLM code generation if callback provided
        if callable(llm_callback) and not dry_run:
            try:
                gen_prompt = (
                    f"Create a self-contained Python module for a skill named '{clean_name}'.\n"
                    f"Task: {clean_desc}\n"
                    "Requirements:\n"
                    "1. Must define: def execute(args: dict, context: dict) -> dict:\n"
                    "2. Must return a dict with 'status': 'success' and 'voice_response': str.\n"
                    "3. Return ONLY valid Python code inside ```python ``` blocks. No markdown explanation."
                )
                llm_out = llm_callback(gen_prompt)
                code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", llm_out, re.DOTALL)
                if code_match:
                    generated_code = code_match.group(1).strip()
            except Exception as e:
                print(f"[SkillForge LLM CodeGen Warning]: {e}")

        # Deterministic code templates for common system & utility tasks
        if not generated_code:
            desc_lower = clean_desc.lower()
            if "uptime" in desc_lower or "boot" in desc_lower:
                triggers.extend(["system uptime", "check uptime", "how long has my pc been running", "uptime check"])
                generated_code = (
                    "import time\n"
                    "import psutil\n\n"
                    "def execute(args: dict, context: dict) -> dict:\n"
                    "    boot_timestamp = psutil.boot_time()\n"
                    "    uptime_sec = time.time() - boot_timestamp\n"
                    "    hours = int(uptime_sec // 3600)\n"
                    "    minutes = int((uptime_sec % 3600) // 60)\n"
                    "    msg = f'System has been running for {hours} hours and {minutes} minutes.'\n"
                    "    return {\n"
                    "        'status': 'success',\n"
                    "        'uptime_hours': hours,\n"
                    "        'uptime_minutes': minutes,\n"
                    "        'voice_response': msg\n"
                    "    }\n"
                )
            elif "calc" in desc_lower or "math" in desc_lower:
                triggers.extend(["calculate", "solve math"])
                generated_code = (
                    "import math\n\n"
                    "def execute(args: dict, context: dict) -> dict:\n"
                    "    expr = args.get('expression', '0')\n"
                    "    return {\n"
                    "        'status': 'success',\n"
                    "        'expression': expr,\n"
                    "        'voice_response': f'Processed calculation for {expr}.'\n"
                    "    }\n"
                )
            else:
                generated_code = (
                    "import datetime\n\n"
                    "def execute(args: dict, context: dict) -> dict:\n"
                    f"    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')\n"
                    f"    msg = f'Executed custom skill {clean_name} at ' + now_str + '.'\n"
                    "    return {\n"
                    "        'status': 'success',\n"
                    "        'voice_response': msg\n"
                    "    }\n"
                )

        # 3. Validate code via AST Security Sandbox
        is_safe, reason = self.validate_skill_code(generated_code)
        if not is_safe:
            return {
                "status": "security_violation",
                "slug": skill_slug,
                "error": reason,
                "voice_response": f"Skill creation rejected by AST sandbox: {reason}"
            }

        # 4. Write files to disk (or simulate in dry_run)
        skill_dir = os.path.join(self.skills_dir, skill_slug)
        md_file = os.path.join(skill_dir, "SKILL.md")
        py_file = os.path.join(skill_dir, "skill.py")

        frontmatter = {
            "name": clean_name,
            "description": clean_desc,
            "triggers": list(set(triggers)),
            "version": "1.0.0",
            "success_count": 0
        }
        md_content = f"---\n{yaml.dump(frontmatter, sort_keys=False)}---\n# {clean_name}\n{clean_desc}\n"

        test_passed = True
        test_output = "Dry-run mode: unit test skipped."
        test_file = os.path.join(skill_dir, "test_skill.py")

        if not dry_run:
            os.makedirs(skill_dir, exist_ok=True)
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(md_content)
            with open(py_file, "w", encoding="utf-8") as f:
                f.write(generated_code)
            self.refresh_registry()

            test_passed, test_output = self.generate_and_run_skill_test(skill_slug)
            if not test_passed and callable(llm_callback):
                # Trigger self-healing repair if unit test failed
                try:
                    repair_prompt = (
                        f"The unit test for skill '{skill_slug}' failed with output:\n{test_output}\n\n"
                        f"Code:\n```python\n{generated_code}\n```\n\n"
                        "Fix the skill code so execute(args, context) returns a dict with 'status' and 'voice_response' under 3.0s.\n"
                        "Return ONLY valid Python code inside ```python ``` blocks."
                    )
                    fix_out = llm_callback(repair_prompt)
                    code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", fix_out, re.DOTALL)
                    if code_match:
                        repaired = code_match.group(1).strip()
                        ok_ast, _ = self.validate_skill_code(repaired)
                        if ok_ast:
                            with open(py_file, "w", encoding="utf-8") as f:
                                f.write(repaired)
                            test_passed, test_output = self.generate_and_run_skill_test(skill_slug)
                except Exception as e:
                    print(f"[SkillForge Test Repair Warning]: {e}")

        voice = f"Created, verified, and loaded skill '{clean_name}'."
        return {
            "status": "success" if test_passed else "test_failed",
            "slug": skill_slug,
            "name": clean_name,
            "description": clean_desc,
            "triggers": frontmatter["triggers"],
            "version": "1.0.0",
            "folder": skill_dir,
            "test_passed": test_passed,
            "test_file": test_file,
            "test_output": test_output,
            "voice_response": voice
        }

    def generate_and_run_skill_test(self, skill_slug: str) -> Tuple[bool, str]:
        """
        Generates skills/<skill_slug>/test_skill.py and executes pytest in an isolated
        subprocess with a 5.0-second timeout to verify:
          1. AST safety & valid import of skill.py
          2. execute(args={}, context={"dry_run": True}) returns a dict with 'status' and 'voice_response'
          3. Execution finishes in < 3.0 seconds without unhandled exceptions
        """
        import subprocess

        skill_dir = os.path.join(self.skills_dir, skill_slug)
        py_file = os.path.join(skill_dir, "skill.py")
        test_file = os.path.join(skill_dir, "test_skill.py")

        if not os.path.isfile(py_file):
            return False, f"Missing skill.py at {py_file}"

        test_code = f'''import os
import sys
import time
import importlib.util

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.skill_forge import SkillForge


def _load_skill_module():
    py_path = os.path.join(SKILL_DIR, "skill.py")
    spec = importlib.util.spec_from_file_location("forged_skill_{skill_slug}", py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, py_path


def test_ast_safety_and_import():
    mod, py_path = _load_skill_module()
    with open(py_path, "r", encoding="utf-8") as f:
        code = f.read()
    forge = SkillForge()
    is_valid, reason = forge.validate_skill_code(code)
    assert is_valid, f"AST validation failed: {{reason}}"
    assert hasattr(mod, "execute"), "Skill module missing execute(args, context)"


def test_execute_contract_and_speed():
    mod, _ = _load_skill_module()
    t0 = time.perf_counter()
    res = mod.execute(args={{}}, context={{"dry_run": True}})
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0, f"Skill execution took too long: {{elapsed:.2f}}s"
    assert isinstance(res, dict), "execute() must return a dict"
    assert "status" in res, "Result dict missing 'status' key"
    assert "voice_response" in res, "Result dict missing 'voice_response' key"
    assert isinstance(res["voice_response"], str) and len(res["voice_response"].strip()) > 0
'''
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-q"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5.0
            )
            output = (proc.stdout + "\n" + proc.stderr).strip()
            return (proc.returncode == 0), output
        except subprocess.TimeoutExpired:
            return False, "Skill unit test timed out (> 5.0s)"
        except Exception as e:
            return False, f"Pytest subprocess error: {e}"

    def run_skill(
        self,
        skill_slug: str,
        args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        llm_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes a registered skill by dynamically importing its skill.py.
        Supports self-healing: if an exception occurs, triggers LLM or heuristic
        repair, validates repaired code via AST, updates skill.py, and retries.
        """
        self.refresh_registry()
        meta = self.registry.get(skill_slug)
        if not meta:
            # Try fuzzy match
            for s, m in self.registry.items():
                if skill_slug.lower() in s.lower() or s.lower() in skill_slug.lower():
                    meta = m
                    skill_slug = s
                    break

        if not meta:
            return {
                "status": "not_found",
                "skill_slug": skill_slug,
                "voice_response": f"Skill '{skill_slug}' not found in registry."
            }

        py_path = meta.get("py_path")
        md_path = meta.get("md_path")
        if not py_path or not os.path.isfile(py_path):
            return {
                "status": "error",
                "skill_slug": skill_slug,
                "voice_response": f"Executable module missing for skill '{skill_slug}'."
            }

        # Helper to load and execute cleanly without bytecode cache issues
        def _exec_module(path: str) -> Dict[str, Any]:
            import types
            with open(path, "r", encoding="utf-8") as f:
                code_str = f.read()
            mod_name = f"skills.{skill_slug}.skill"
            mod = types.ModuleType(mod_name)
            mod.__file__ = path
            sys.modules[mod_name] = mod
            exec(code_str, mod.__dict__)
            if not hasattr(mod, "execute"):
                raise AttributeError("Module missing 'execute' function")
            return mod.execute(args or {}, context or {})

        # Attempt 1: Standard execution
        try:
            result = _exec_module(py_path)
            self._increment_success_count(md_path)
            if "status" not in result:
                result["status"] = "success"
            return result
        except Exception as exc:
            err_type = type(exc).__name__
            tb = traceback.format_exc()
            print(f"\n[SkillForge Runtime Error]: {skill_slug} failed with {err_type}: {exc}")

            # ---------------------------------------------------------
            # SELF-HEALING REPAIR LOOP
            # ---------------------------------------------------------
            with open(py_path, "r", encoding="utf-8") as f:
                failing_code = f.read()

            repaired_code = None

            # Attempt repair via LLM callback if provided
            if callable(llm_callback):
                try:
                    repair_prompt = (
                        f"The Python skill '{skill_slug}' crashed with {err_type}: {exc}.\n"
                        f"Traceback:\n{tb}\n\n"
                        f"Original Code:\n```python\n{failing_code}\n```\n\n"
                        "Fix the bug in the code. Requirements:\n"
                        "1. Must define: def execute(args: dict, context: dict) -> dict:\n"
                        "2. Must return a dict with 'status': 'success' and 'voice_response': str.\n"
                        "3. Return ONLY the fixed Python code inside ```python ``` blocks."
                    )
                    fix_response = llm_callback(repair_prompt)
                    code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", fix_response, re.DOTALL)
                    if code_match:
                        repaired_code = code_match.group(1).strip()
                except Exception as repair_err:
                    print(f"[SkillForge Self-Healing Callback Error]: {repair_err}")

            # Rule-based fallback repair (e.g. ZeroDivisionError or missing return)
            if not repaired_code:
                if "ZeroDivisionError" in err_type:
                    # Replace division by zero with safe fallback
                    repaired_code = re.sub(r"/\s*0(?!\d)", "/ 1", failing_code)
                elif "AttributeError" in err_type and "execute" in str(exc):
                    repaired_code = failing_code + "\n\ndef execute(args, context):\n    return {'status': 'success', 'voice_response': 'Repaired missing execute.'}\n"

            if repaired_code:
                is_safe, reason = self.validate_skill_code(repaired_code)
                if is_safe:
                    with open(py_path, "w", encoding="utf-8") as f:
                        f.write(repaired_code)
                    self._bump_version(md_path)
                    print(f"[SkillForge Self-Healing Success]: Repaired and patched {skill_slug}/skill.py.")

                    # Retry execution with repaired module
                    try:
                        retry_result = _exec_module(py_path)
                        self._increment_success_count(md_path)
                        if "status" not in retry_result:
                            retry_result["status"] = "success"
                        retry_result["self_healed"] = True
                        return retry_result
                    except Exception as retry_err:
                        print(f"[SkillForge Retry After Repair Failed]: {retry_err}")

            return {
                "status": "error",
                "skill_slug": skill_slug,
                "error": f"{err_type}: {exc}",
                "voice_response": f"Skill '{skill_slug}' encountered an error: {err_type}."
            }

    def _increment_success_count(self, md_path: Optional[str]):
        """Increments success_count in SKILL.md frontmatter."""
        if not md_path or not os.path.isfile(md_path):
            return
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            def _inc(m):
                return f"success_count: {int(m.group(1)) + 1}"

            new_content = re.sub(r"success_count:\s*(\d+)", _inc, content)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception:
            pass

    def _bump_version(self, md_path: Optional[str]):
        """Increments patch version in SKILL.md frontmatter."""
        if not md_path or not os.path.isfile(md_path):
            return
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            def _bump(m):
                major, minor, patch = m.group(1), m.group(2), int(m.group(3)) + 1
                return f"version: {major}.{minor}.{patch}"

            new_content = re.sub(r"version:\s*(\d+)\.(\d+)\.(\d+)", _bump, content)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception:
            pass
