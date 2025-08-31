#!/usr/bin/env python3
"""
Setup script for Ask Dr. Chaffee project.
Handles initial project configuration and dependency installation.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def run_command(command, cwd=None, check=True):
    """Run a shell command and return the result"""
    print(f"Running: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd, 
            check=check,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        if check:
            sys.exit(1)
        return e

def check_dependencies():
    """Check if required dependencies are available"""
    print("Checking dependencies...")
    
    # Check Docker
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        print("[OK] Docker is available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERROR] Docker is not available or not installed")
        print("Please install Docker Desktop: https://www.docker.com/products/docker-desktop/")
        return False
    
    # Check Python
    try:
        version = subprocess.run(
            [sys.executable, "--version"], 
            check=True, 
            capture_output=True, 
            text=True
        ).stdout.strip()
        print(f"[OK] Python is available: {version}")
    except subprocess.CalledProcessError:
        print("[ERROR] Python is not available")
        return False
    
    # Check Node.js
    try:
        version = subprocess.run(
            ["node", "--version"], 
            check=True, 
            capture_output=True, 
            text=True
        ).stdout.strip()
        print(f"[OK] Node.js is available: {version}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERROR] Node.js is not available or not installed")
        print("Please install Node.js: https://nodejs.org/")
        return False
    
    return True

def setup_environment():
    """Set up environment file"""
    print("Setting up environment...")
    
    if not os.path.exists('.env'):
        if os.path.exists('.env.example'):
            shutil.copy('.env.example', '.env')
            print("[OK] Created .env file from template")
        else:
            print("[ERROR] .env.example not found")
    else:
        print("[OK] .env file already exists")

def install_backend_dependencies():
    """Install Python backend dependencies"""
    print("Installing backend dependencies...")
    
    backend_dir = Path("backend")
    if not backend_dir.exists():
        print("[ERROR] Backend directory not found")
        return False
    
    # Create virtual environment if it doesn't exist
    venv_dir = backend_dir / "venv"
    if not venv_dir.exists():
        run_command(f"{sys.executable} -m venv venv", cwd=backend_dir)
        print("[OK] Created Python virtual environment")
    
    # Install dependencies
    if os.name == 'nt':  # Windows
        pip_path = venv_dir / "Scripts" / "pip.exe"
        python_path = venv_dir / "Scripts" / "python.exe"
    else:  # Linux/Mac
        pip_path = venv_dir / "bin" / "pip"
        python_path = venv_dir / "bin" / "python"
    
    if pip_path.exists():
        # Use absolute path and proper Windows path handling
        pip_command = str(pip_path.absolute())
        run_command(f'"{pip_command}" install -r requirements.txt', cwd=backend_dir)
        print("[OK] Installed Python dependencies")
        return True
    else:
        print("[ERROR] Could not find pip in virtual environment")
        # Alternative: use the virtual environment's Python with -m pip
        if python_path.exists():
            python_command = str(python_path.absolute())
            run_command(f'"{python_command}" -m pip install -r requirements.txt', cwd=backend_dir)
            print("[OK] Installed Python dependencies (using python -m pip)")
            return True
        return False

def install_frontend_dependencies():
    """Install Node.js frontend dependencies"""
    print("Installing frontend dependencies...")
    
    frontend_dir = Path("frontend")
    if not frontend_dir.exists():
        print("[ERROR] Frontend directory not found")
        return False
    
    run_command("npm install", cwd=frontend_dir)
    print("[OK] Installed Node.js dependencies")
    return True

def setup_database():
    """Set up the database using Docker"""
    print("Setting up database...")
    
    # Start database
    run_command("docker-compose up -d postgres")
    print("[OK] Database container started")
    
    # Wait a moment for database to be ready
    import time
    print("Waiting for database to be ready...")
    time.sleep(10)
    
    print("[OK] Database setup complete")

def main():
    """Main setup function"""
    print("=== Ask Dr. Chaffee Setup ===\n")
    
    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies and run setup again.")
        sys.exit(1)
    
    print("\n" + "="*40)
    
    # Setup environment
    setup_environment()
    
    print("\n" + "="*40)
    
    # Install dependencies
    backend_success = install_backend_dependencies()
    frontend_success = install_frontend_dependencies()
    
    if not (backend_success and frontend_success):
        print("\n[ERROR] Some dependencies failed to install")
        sys.exit(1)
    
    print("\n" + "="*40)
    
    # Setup database
    setup_database()
    
    print("\n" + "="*40)
    print("\n[OK] Setup complete!")
    print("\nNext steps:")
    print("1. Edit .env file with your API keys and configuration")
    print("2. Run 'make ingest-youtube' to start ingesting YouTube transcripts")
    print("3. Run 'cd frontend && npm run dev' to start the web interface")
    print("\nFor help, see README.md or run 'make help'")

if __name__ == "__main__":
    main()
