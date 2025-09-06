#!/usr/bin/env python3
"""
Pre-commit hook to detect secrets like API keys in code.
"""

import os
import re
import sys
import subprocess
from typing import List, Tuple, Dict, Any, Set

# Patterns to detect common API keys and secrets
SECRET_PATTERNS = [
    # Generic API key patterns
    r'api[_-]?key["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
    r'api[_-]?secret["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
    r'access[_-]?key["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
    r'access[_-]?secret["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
    r'password["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{8,})["\']',
    r'secret["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{8,})["\']',
    r'token["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{8,})["\']',
    
    # Specific API key patterns
    r'AIza[0-9A-Za-z\-_]{35}',  # Google API Key
    r'sk-[0-9a-zA-Z]{48}',      # OpenAI API Key
    r'github_pat_[0-9a-zA-Z]{22}_[0-9a-zA-Z]{59}',  # GitHub Personal Access Token
    r'SG\.[0-9a-zA-Z]{22}\.[0-9a-zA-Z]{43}',  # SendGrid API Key
    
    # AWS
    r'AKIA[0-9A-Z]{16}',  # AWS Access Key ID
    r'aws_access_key_id["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{16,})["\']',
    r'aws_secret_access_key["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{32,})["\']',
    
    # Database connection strings
    r'postgres(ql)?:\/\/[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-\.]+:[0-9]+\/[a-zA-Z0-9_\-]+',
    r'mysql:\/\/[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-\.]+:[0-9]+\/[a-zA-Z0-9_\-]+',
    r'mongodb(\+srv)?:\/\/[a-zA-Z0-9_\-]+:[a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-\.]+:[0-9]+\/[a-zA-Z0-9_\-]+',
]

# Files to always ignore
IGNORED_FILES = {
    '.env.example',
    'detect-secrets.py',
    '.gitignore',
    'README.md',
    'CONTRIBUTING.md',
    'LICENSE',
}

# File extensions to check
EXTENSIONS_TO_CHECK = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.yml', '.yaml', 
    '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd', '.html', '.css',
    '.md', '.txt', '.csv', '.xml', '.sql', '.env'
}

def is_file_ignored(filename: str) -> bool:
    """Check if a file should be ignored."""
    basename = os.path.basename(filename)
    if basename in IGNORED_FILES:
        return True
    
    # Skip binary files and certain extensions
    _, ext = os.path.splitext(filename.lower())
    if ext not in EXTENSIONS_TO_CHECK:
        return True
    
    return False

def get_staged_files() -> List[str]:
    """Get list of files staged for commit."""
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
        capture_output=True, text=True
    )
    return result.stdout.strip().split('\n')

def check_file_for_secrets(filename: str) -> List[Tuple[int, str, str]]:
    """Check a file for potential secrets."""
    if not os.path.isfile(filename) or is_file_ignored(filename):
        return []
    
    findings = []
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            for pattern in SECRET_PATTERNS:
                matches = re.search(pattern, line)
                if matches:
                    findings.append((i, pattern, line.strip()))
    
    return findings

def main() -> int:
    """Main function to check for secrets in staged files."""
    staged_files = get_staged_files()
    if not staged_files or staged_files == ['']:
        print("No staged files to check.")
        return 0
    
    all_findings = []
    for filename in staged_files:
        if filename and not is_file_ignored(filename):
            findings = check_file_for_secrets(filename)
            if findings:
                all_findings.append((filename, findings))
    
    if all_findings:
        print("\n🚨 POTENTIAL SECRETS DETECTED IN STAGED FILES 🚨\n")
        for filename, findings in all_findings:
            print(f"File: {filename}")
            for line_num, pattern, line in findings:
                print(f"  Line {line_num}: Potential secret detected")
                print(f"    Pattern: {pattern}")
                print(f"    Content: {line}")
            print()
        
        print("Please remove these secrets and use environment variables instead.")
        print("Example: api_key = os.getenv('API_KEY')")
        return 1
    
    print("✅ No secrets detected in staged files.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
