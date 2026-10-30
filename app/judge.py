"""Compiles and runs submissions against stdin/stdout test cases.

Each run happens in a fresh temporary directory, in its own process group, with a wall-clock
timeout and (on Linux) CPU, memory and file-size limits. This is good for a classroom or a
private deployment. For a public site, run this module inside a locked-down container
(no network, read-only filesystem, unprivileged user) or swap `execute` for a sandbox service.
"""
import os
import shutil
import signal
import subprocess
import tempfile
import time

try:
    import resource
except ImportError:  # Windows
    resource = None

CACHE_DIR = os.path.join(tempfile.gettempdir(), "codequest-judge-cache")

# name, file, compile command, run command, whether to apply an address-space limit
# (JVM, V8, Go and Mono reserve large virtual ranges, so they get heap flags instead).
LANGS = {
    "python": {"label": "Python 3", "file": "main.py", "compile": None,
               "run": ["python3", "main.py"], "as_limit": True, "needs": "python3", "mode": "python"},
    "c": {"label": "C (gcc)", "file": "main.c", "compile": ["gcc", "-O2", "-std=c17", "main.c", "-o", "main", "-lm"],
          "run": ["./main"], "as_limit": True, "needs": "gcc", "mode": "text/x-csrc"},
    "cpp": {"label": "C++17 (g++)", "file": "main.cpp", "compile": ["g++", "-O2", "-std=c++17", "main.cpp", "-o", "main"],
            "run": ["./main"], "as_limit": True, "needs": "g++", "mode": "text/x-c++src"},
    "java": {"label": "Java", "file": "Main.java", "compile": ["javac", "Main.java"],
             "run": ["java", "-Xmx256m", "-Xss64m", "-XX:+UseSerialGC", "-cp", ".", "Main"], "as_limit": False,
             "needs": "javac", "mode": "text/x-java"},
    "csharp": {"label": "C# (Mono)", "file": "Main.cs", "compile": ["mcs", "-optimize+", "-out:main.exe", "Main.cs"],
               "run": ["mono", "main.exe"], "as_limit": False, "needs": "mcs", "mode": "text/x-csharp"},
    "javascript": {"label": "JavaScript (Node)", "file": "main.js", "compile": None,
                   "run": ["node", "--max-old-space-size=256", "main.js"], "as_limit": False, "needs": "node",
                   "mode": "javascript"},
    "go": {"label": "Go", "file": "main.go", "compile": ["go", "build", "-o", "main", "main.go"],
           "run": ["./main"], "as_limit": False, "needs": "go", "mode": "text/x-go"},
    "php": {"label": "PHP", "file": "main.php", "compile": None, "run": ["php", "main.php"], "as_limit": True,
            "needs": "php", "mode": "text/x-php"},
    "rust": {"label": "Rust", "file": "main.rs", "compile": ["rustc", "-O", "-o", "main", "main.rs"],
             "run": ["./main"], "as_limit": True, "needs": "rustc", "mode": "text/x-rustsrc"},
}

TEMPLATES = {
    "python": "import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    # write your solution here\n\n\nmain()\n",
    "c": "#include <stdio.h>\n\nint main(void) {\n    // read from stdin with scanf, print with printf\n    return 0;\n}\n",
    "cpp": "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    // read from cin, print with cout\n    return 0;\n}\n",
    "java": "import java.util.*;\nimport java.io.*;\n\npublic class Main {\n    public static void main(String[] args) throws IOException {\n        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n        // read input, print with System.out.println\n    }\n}\n",
    "csharp": "using System;\nusing System.Linq;\n\npublic class Program {\n    public static void Main() {\n        // read with Console.ReadLine(), print with Console.WriteLine()\n    }\n}\n",
    "javascript": "const data = require('fs').readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);\n// write your solution here\n",
    "go": "package main\n\nimport (\n\t\"bufio\"\n\t\"fmt\"\n\t\"os\"\n)\n\nfunc main() {\n\treader := bufio.NewReader(os.Stdin)\n\t_ = reader\n\tfmt.Println()\n}\n",
    "php": "<?php\n$data = preg_split('/\\s+/', trim(stream_get_contents(STDIN)));\n// write your solution here\n",
    "rust": "use std::io::{self, Read};\n\nfn main() {\n    let mut input = String::new();\n    io::stdin().read_to_string(&mut input).unwrap();\n    let mut it = input.split_whitespace();\n    let _ = it.next();\n}\n",
}


def available():
    return {k: v for k, v in LANGS.items() if shutil.which(v["needs"])}


def _limits(cpu_s, mem_mb, as_limit):
    def apply():
        if resource is None:
            return
        resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_s) + 1, int(cpu_s) + 2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
        if as_limit:
            b = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
    return apply


def _run(cmd, cwd, stdin, timeout, mem_mb, as_limit, env):
    start = time.perf_counter()
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, start_new_session=True,
                         preexec_fn=_limits(timeout, mem_mb, as_limit) if os.name == "posix" else None)
    try:
        out, err = p.communicate(stdin.encode(), timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError):
            p.kill()
        out, err = p.communicate()
        timed_out = True
    elapsed = int((time.perf_counter() - start) * 1000)
    if p.returncode in (-signal.SIGXCPU, -signal.SIGKILL) and not timed_out and elapsed >= timeout * 900:
        timed_out = True
    return {"code": p.returncode, "out": out.decode(errors="replace")[:65536],
            "err": err.decode(errors="replace")[-4000:], "ms": elapsed, "timeout": timed_out}


def normalize(text):
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def execute(lang, code, tests, time_limit=3.0, mem_mb=512, stop_on_fail=False):
    """tests: [{"input": str, "output": str | None}]. A None output means "just show me the output".
    Returns {verdict, passed, total, runtime_ms, compile_output, results}."""
    spec = LANGS.get(lang)
    if not spec or not shutil.which(spec["needs"]):
        return {"verdict": "Language not available", "passed": 0, "total": len(tests), "runtime_ms": None,
                "compile_output": f"{lang} is not installed on this server.", "results": []}
    os.makedirs(CACHE_DIR, exist_ok=True)
    work = tempfile.mkdtemp(prefix="cq-")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": work, "LANG": "C.UTF-8",
           "GOCACHE": os.path.join(CACHE_DIR, "go"), "GOPATH": os.path.join(CACHE_DIR, "gopath"),
           "GO111MODULE": "off", "TMPDIR": work,
           "RUSTUP_HOME": os.environ.get("RUSTUP_HOME", os.path.expanduser("~/.rustup")),
           "CARGO_HOME": os.environ.get("CARGO_HOME", os.path.expanduser("~/.cargo"))}
    try:
        with open(os.path.join(work, spec["file"]), "w") as f:
            f.write(code)
        if spec["compile"]:
            c = _run(spec["compile"], work, "", 30, 2048, False, env)
            if c["code"] != 0 or c["timeout"]:
                msg = (c["err"] or c["out"]).replace(work + "/", "")
                return {"verdict": "Compilation Error", "passed": 0, "total": len(tests), "runtime_ms": None,
                        "compile_output": msg[-4000:], "results": []}
        results, passed, worst, verdict = [], 0, 0, "Accepted"
        for t in tests:
            r = _run(spec["run"], work, t["input"], time_limit, mem_mb, spec["as_limit"], env)
            worst = max(worst, r["ms"])
            if r["timeout"]:
                v = "Time Limit Exceeded"
            elif r["code"] != 0:
                v = "Runtime Error"
            elif t.get("output") is None:
                v = "Ran"
            elif normalize(r["out"]) == normalize(t["output"]):
                v = "Accepted"
            else:
                v = "Wrong Answer"
            passed += v in ("Accepted", "Ran")
            results.append({"input": t["input"], "expected": t.get("output"), "output": r["out"],
                            "stderr": r["err"].replace(work + "/", ""), "verdict": v, "ms": r["ms"]})
            if v not in ("Accepted", "Ran") and verdict == "Accepted":
                verdict = v
                if stop_on_fail:
                    break
        return {"verdict": verdict, "passed": passed, "total": len(tests), "runtime_ms": worst,
                "compile_output": "", "results": results}
    finally:
        shutil.rmtree(work, ignore_errors=True)
