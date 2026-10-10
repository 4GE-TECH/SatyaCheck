"""Item 18b: loading ECAPA must not break any later model load in the same process.

Root cause, measured on this machine (speechbrain 1.1.0, Windows, Python 3.14):

`import speechbrain` registers seven `DeprecatedModuleRedirect` entries in `sys.modules`
— lazy aliases for old import paths such as `speechbrain.k2_integration`. Anything that
later calls `inspect.getmodule` walks `sys.modules` and touches them; importing
`torch.distributed.tensor` does, through torch's op registration, and `transformers`
imports that. Touching `speechbrain.k2_integration` tries to import `k2`, which is not
installed, and raises `ImportError`.

speechbrain means to suppress exactly this: `LazyModule.ensure_module` raises the
harmless `AttributeError` when the caller is `inspect.py`. But it tests
`filename.endswith("/inspect.py")`, and on Windows the path ends `\\inspect.py`. The
guard never fires, so BGE-m3 — and the whole intent branch — fails to load whenever
ECAPA loaded first.

`audio_ml.embed` now drops the *unloaded* redirect aliases right after importing
speechbrain. This repo never imports any of the old paths.

Run in subprocesses: inside one pytest session `sys.modules` already holds whatever
earlier tests imported, and the collision would not reproduce.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import config

ECAPA = config.MODELS_DIR / "ecapa"
BGE = config.MODELS_DIR / "bge-m3"


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        cwd=str(config.REPO_ROOT), timeout=300,
        env={**__import__("os").environ, "HF_HUB_OFFLINE": "1"},
    )


# Files, not directories: a failed speechbrain load leaves an empty models/ecapa/ behind.
@pytest.mark.skipif(not ((ECAPA / "embedding_model.ckpt").is_file() and (BGE / "config.json").is_file()), reason="needs models/ecapa and models/bge-m3")
def test_bge_m3_loads_after_ecapa_in_the_same_process():
    result = _run(
        "import config\n"
        "from audio_ml import embed\n"
        "assert embed._load_ecapa_model(embed.ECAPA_MODEL_PATH) is not None\n"
        "from nlp_rag.embed import load_encoder\n"
        "assert load_encoder() is not None, 'BGE-m3 failed after ECAPA'\n"
        "print('OK')\n"
    )
    assert "OK" in result.stdout, result.stderr[-2000:]


def test_no_unloaded_redirects_remain_after_import():
    result = _run(
        "import sys, config\n"
        "from audio_ml import embed\n"
        "embed._import_speechbrain_encoder()\n"
        "from speechbrain.utils.importutils import DeprecatedModuleRedirect\n"
        "left = [k for k, v in sys.modules.items()\n"
        "        if isinstance(v, DeprecatedModuleRedirect) and v.lazy_module is None]\n"
        "assert left == [], left\n"
        "print('OK')\n"
    )
    assert "OK" in result.stdout, result.stderr[-2000:]


def test_the_repo_never_imports_a_deprecated_speechbrain_path():
    """Dropping the aliases is only safe while nothing here uses the old paths."""
    import re

    # Imports only: audio_ml/embed.py names these paths in prose to explain the fix.
    old = re.compile(
        r"^\s*(from|import)\s+speechbrain\.(pretrained|k2_integration|wordemb|lobes\.models\."
        r"(huggingface_transformers|spacy|flair)|nnet\.loss\.transducer_loss)\b",
        re.MULTILINE,
    )
    hits = []
    for folder in ("audio_ml", "nlp_rag", "server", "scripts"):
        for path in (config.REPO_ROOT / folder).rglob("*.py"):
            if old.search(path.read_text(encoding="utf-8", errors="replace")):
                hits.append(str(path))
    assert hits == []
