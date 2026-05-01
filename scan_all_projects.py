import os
import sys
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def is_karate_project(path: Path) -> bool:
    """Check if a directory is a Karate project."""
    if not path.is_dir():
        return False
    # Check for config files
    if list(path.glob("**/karate-config*.js")):
        return True
    # Check for standard structure
    if (path / "src/test/java").exists() or (path / "features").exists():
        return True
    return False

def find_karate_projects(paths):
    projects = []
    for p_str in paths:
        base_path = Path(p_str)
        if not base_path.exists():
            logger.error(f"Path not found: {p_str}")
            continue
            
        # If the path itself is a project, add it
        if is_karate_project(base_path):
            projects.append(base_path)
        else:
            # Otherwise, search subdirectories
            for item in base_path.iterdir():
                if is_karate_project(item):
                    projects.append(item)
                
    return sorted(list(set(projects))) # Deduplicate and sort

def scan_all(input_paths):
    projects = find_karate_projects(input_paths)
    
    if not projects:
        logger.warning(f"No Karate projects found in the provided paths")
        return

    logger.info(f"Found {len(projects)} projects: {[p.name for p in projects]}")
    
    for project_path in projects:
        project_name = project_path.name
        output_name = f"MultiScan_{project_name}"
        
        logger.info(f"\n" + "="*50)
        logger.info(f"SCANNING PROJECT: {project_name} ({project_path})")
        logger.info("="*50)
        
        cmd = [
            sys.executable, 
            "scan_project.py", 
            str(project_path.absolute()), 
            output_name
        ]
        
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        env["PYTHONIOENCODING"] = "utf-8"
        
        try:
            subprocess.run(cmd, check=True, env=env)
            logger.info(f"✅ Successfully scanned {project_name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to scan {project_name}: {e}")

if __name__ == "__main__":
    # Support multiple paths as arguments
    input_paths = sys.argv[1:] if len(sys.argv) > 1 else ["."]
    scan_all(input_paths)
