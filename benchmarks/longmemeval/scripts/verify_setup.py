#!/usr/bin/env python3
"""
MFlow LongMemEval Benchmark - Environment Verification Script

This script verifies that all prerequisites are met before running the benchmark.
Run this first to ensure your environment is correctly configured.

Usage:
    python verify_setup.py
"""

import os
import sys
from pathlib import Path

# ============================================================================
# Setup paths
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
MFLOW_ROOT = SCRIPT_DIR.parent.parent
WORKSPACE_ROOT = MFLOW_ROOT.parent.parent

# Add MFlow to path
sys.path.insert(0, str(MFLOW_ROOT))


def print_header(title: str) -> None:
    """Print section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_check(name: str, status: bool, details: str = "") -> bool:
    """Print check result"""
    icon = "✓" if status else "✗"
    print(f"  {icon} {name}: {details}")
    return status


def check_python_version() -> bool:
    """Check Python version"""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    ok = version.major == 3 and version.minor >= 10
    return print_check("Python version", ok, f"{version_str} (need 3.10+)")


def check_mflow_installation() -> bool:
    """Check if MFlow is installed"""
    try:
        import m_flow
        version = getattr(m_flow, '__version__', 'unknown')
        return print_check("MFlow installation", True, f"v{version}")
    except ImportError as e:
        return print_check("MFlow installation", False, f"Not found: {e}")


def check_env_file() -> bool:
    """Check .env file exists"""
    env_path = MFLOW_ROOT / '.env'
    if env_path.exists():
        return print_check(".env file", True, str(env_path))
    return print_check(".env file", False, "Not found")


def check_openai_api_key() -> bool:
    """Check OpenAI API key is configured"""
    # Load from .env
    env_path = MFLOW_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith('OPENAI_API_KEY'):
                    key = line.split('=', 1)[1].strip().strip('"').strip("'")
                    if key and len(key) > 10:
                        masked = key[:8] + '...' + key[-4:]
                        return print_check("OpenAI API key", True, masked)
    
    # Check environment variable
    key = os.environ.get('OPENAI_API_KEY', '')
    if key and len(key) > 10:
        masked = key[:8] + '...' + key[-4:]
        return print_check("OpenAI API key", True, f"{masked} (from env)")
    
    return print_check("OpenAI API key", False, "Not configured")


def check_embedding_config() -> bool:
    """Check embedding configuration"""
    env_path = MFLOW_ROOT / '.env'
    dims = None
    model = None
    
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if 'EMBEDDING_DIMENSIONS' in line:
                    dims = line.split('=', 1)[1].strip()
                if 'EMBEDDING_MODEL' in line:
                    model = line.split('=', 1)[1].strip().strip('"')
    
    if dims and model:
        return print_check("Embedding config", True, f"{model} ({dims} dims)")
    return print_check("Embedding config", False, "Not properly configured")


def check_data_file() -> bool:
    """Check LongMemEval data file exists"""
    # Try multiple paths
    possible_paths = [
        SCRIPT_DIR.parent / "data" / "longmemeval_oracle.json",
        SCRIPT_DIR / "data" / "longmemeval_oracle.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            # Count questions
            import json
            with open(path) as f:
                questions = json.load(f)
            return print_check("LongMemEval data", True, f"{len(questions)} questions at {path.name}")
    
    return print_check("LongMemEval data", False, "Not found. See README for data setup.")


def check_database_directory() -> bool:
    """Check MFlow database directory"""
    db_path = MFLOW_ROOT / 'm_flow/.m_flow_system/databases'
    if db_path.exists():
        # Count files
        files = list(db_path.glob('*'))
        return print_check("Database directory", True, f"{len(files)} files/dirs")
    return print_check("Database directory", True, "Will be created on first run")


def check_nltk_data() -> bool:
    """Check NLTK data is available"""
    try:
        import nltk
        nltk.data.find('tokenizers/punkt')
        return print_check("NLTK punkt tokenizer", True, "Available")
    except LookupError:
        # Try to download
        try:
            import nltk
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
            return print_check("NLTK punkt tokenizer", True, "Downloaded")
        except Exception:
            return print_check("NLTK punkt tokenizer", False, "Not available")


def check_dependencies() -> bool:
    """Check required Python packages"""
    required = ['openai', 'nltk', 'pydantic', 'dotenv', 'kuzu', 'lancedb']
    missing = []
    
    for pkg in required:
        try:
            if pkg == 'dotenv':
                __import__('dotenv')
            else:
                __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if not missing:
        return print_check("Python packages", True, f"All {len(required)} required packages found")
    return print_check("Python packages", False, f"Missing: {', '.join(missing)}")


def test_mflow_retrieval() -> bool:
    """Test MFlow retrieval functionality"""
    try:
        # Load env
        env_path = MFLOW_ROOT / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.strip() and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"')
        
        os.chdir(MFLOW_ROOT)
        
        from m_flow.retrieval.episodic import EpisodicConfig
        config = EpisodicConfig(top_k=5)
        return print_check("MFlow retrieval config", True, "Can create config")
    except Exception as e:
        return print_check("MFlow retrieval config", False, str(e)[:50])


def main() -> int:
    """Run all checks"""
    print("\n" + "="*60)
    print("  MFlow LongMemEval Benchmark - Environment Verification")
    print("="*60)
    print(f"\nMFlow Root: {MFLOW_ROOT}")
    print(f"Workspace:  {WORKSPACE_ROOT}")
    
    all_passed = True
    
    # Core checks
    print_header("Core Requirements")
    all_passed &= check_python_version()
    all_passed &= check_mflow_installation()
    all_passed &= check_dependencies()
    
    # Configuration checks
    print_header("Configuration")
    all_passed &= check_env_file()
    all_passed &= check_openai_api_key()
    all_passed &= check_embedding_config()
    
    # Data checks
    print_header("Data & Storage")
    all_passed &= check_data_file()
    all_passed &= check_database_directory()
    all_passed &= check_nltk_data()
    
    # Functional checks
    print_header("Functionality")
    all_passed &= test_mflow_retrieval()
    
    # Summary
    print_header("Summary")
    if all_passed:
        print("  All checks passed! You can run the benchmark.")
        print("\n  Next steps:")
        print("    1. Run: ./run_benchmark.sh")
        print("    2. Or:  python mflow_ingest.py --max-questions 5  (smoke test)")
        return 0
    else:
        print("  Some checks failed. Please fix the issues above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
