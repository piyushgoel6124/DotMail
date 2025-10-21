import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta

# --- Configuration ---
BATCH_SIZE = 100

def get_positive_int(prompt, default=20):
    while True:
        try:
            user_input = input(f"{prompt} (default {default}): ")
            if not user_input.strip():
                return default
            value = int(user_input)
            if value > 0:
                return value
            else:
                print("Please enter a positive integer.")
        except ValueError:
            print("Invalid input. Please enter a valid integer.")

def get_repo_path(prompt, default="."):
    while True:
        user_input = input(f"{prompt} (default current directory): ")
        if not user_input.strip():
            return default
        if os.path.isdir(user_input):
            return user_input
        else:
            print("Directory does not exist. Please enter a valid path.")

def get_filename(prompt, default="data.txt"):
    user_input = input(f"{prompt} (default {default}): ")
    if not user_input.strip():
        return default
    return user_input

def get_git_info(repo_path):
    """Retrieve current branch, user name, email, and HEAD SHA."""
    try:
        # Get Branch
        res_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, check=True
        )
        branch = res_branch.stdout.strip()
        
        # Get SHA (might fail if empty repo)
        try:
            res_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path, capture_output=True, text=True, check=True
            )
            sha = res_sha.stdout.strip()
        except subprocess.CalledProcessError:
            sha = None # Empty repo, checking out generic root
        
        # Get User Info
        res_name = subprocess.run(["git", "config", "user.name"], cwd=repo_path, capture_output=True, text=True)
        res_email = subprocess.run(["git", "config", "user.email"], cwd=repo_path, capture_output=True, text=True)
        
        name = res_name.stdout.strip() or "Graph Greener"
        email = res_email.stdout.strip() or "graph@greener.local"
        
        return branch, name, email, sha
    except subprocess.CalledProcessError:
        return None, None, None, None

def random_date_in_last_year():
    today = datetime.now()
    start_date = today - timedelta(days=365)
    random_days = random.randint(0, 364)
    random_seconds = random.randint(0, 23*3600 + 3599)
    commit_date = start_date + timedelta(days=random_days, seconds=random_seconds)
    return commit_date

def run_fast_import_batch(repo_path, branch, name, email, parent_sha, updates):
    """
    Experimental high-speed commit generation.
    Returns (success, new_sha)
    """
    cmd = ["git", "fast-import", "--date-format=raw", "--quiet"]
    
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=repo_path
        )
        
        for i, (date_obj, full_content, filename) in enumerate(updates):
            ts = int(date_obj.timestamp())
            date_str = f"{ts} +0000"
            
            # 1. Commit Command
            proc.stdin.write(f"commit refs/heads/{branch}\n".encode('utf-8'))
            
            # 2. 'from' logic (Start of batch needs to link to parent)
            if i == 0 and parent_sha:
                proc.stdin.write(f"from {parent_sha}\n".encode('utf-8'))
            
            # 3. Committer
            proc.stdin.write(f"committer {name} <{email}> {date_str}\n".encode('utf-8'))
            
            # 4. Message
            msg = f"graph-greener commit {i}"
            proc.stdin.write(f"data {len(msg)}\n{msg}\n".encode('utf-8'))
            
            # 5. File Modify
            proc.stdin.write(f"M 100644 inline {filename}\n".encode('utf-8'))
            proc.stdin.write(f"data {len(full_content)}\n".encode('utf-8'))
            proc.stdin.write(full_content)
            proc.stdin.write(b"\n")
        
        proc.stdin.close()
        return_code = proc.wait()
        
        if return_code != 0:
            err = proc.stderr.read().decode()
            print(f"Fast-import error: {err}")
            return False
            
        return True

    except Exception as e:
        print(f"Fast-import Exception: {e}")
        return False

def run_slow_batch(repo_path, filename, updates):
    """Fallback: Standard git commit loop."""
    full_path = os.path.join(repo_path, filename)
    
    print("  Using standard compatibility mode (slower)...")
    for i, (date_obj, full_content, _) in enumerate(updates):
        # Write file
        with open(full_path, "wb") as f:
            f.write(full_content)
            
        # Add
        subprocess.run(["git", "add", filename], cwd=repo_path, check=True)
        
        # Commit
        env = os.environ.copy()
        date_str = date_obj.strftime("%Y-%m-%dT%H:%M:%S")
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        
        subprocess.run(
            ["git", "commit", "-m", "graph-greener commit"], 
            cwd=repo_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if (i+1) % 10 == 0:
            print(f"  Compat mode: {i+1}/{len(updates)}", end="\r")
    print("")
    return True

def main():
    print("="*60)
    print("🌱 Graph Greener: Hybrid Mode 🌱")
    print("="*60)
    print("Generates contribution graph commits. Tries Turbo mode first, falls back if needed.\n")

    num_commits = get_positive_int("How many commits do you want to make", 100)
    repo_path = get_repo_path("Enter the path to your local git repository", ".")
    filename = get_filename("Enter the filename to modify for commits", "data.txt")
    
    # Git Check
    branch, name, email, current_sha = get_git_info(repo_path)
    if not branch:
        print("❌ Error: Not a valid git repository.")
        return
    print(f"Target: {branch} @ {current_sha[:7] if current_sha else 'NEW'} | {name}")

    # Read content
    full_path = os.path.join(repo_path, filename)
    current_content = b""
    if os.path.exists(full_path):
        try:
            with open(full_path, "rb") as f:
                current_content = f.read()
        except: pass

    # Execution Loop
    use_fast_import = True
    total_processed = 0
    start_time = time.time()

    while total_processed < num_commits:
        batch_size = min(BATCH_SIZE, num_commits - total_processed)
        print(f"\nProcessing batch: {total_processed+1} to {total_processed+batch_size}...")
        
        # 1. Prepare Data for Batch
        batch_updates = []
        # Simulate the content growth for this batch
        temp_content = current_content
        for i in range(batch_size):
            commit_date = random_date_in_last_year()
            log_line = f"Commit {total_processed + i + 1} at {commit_date.isoformat()}\n".encode('utf-8')
            temp_content += log_line
            batch_updates.append((commit_date, temp_content, filename))
        
        # 2. Try Fast Import
        success = False
        if use_fast_import:
            if run_fast_import_batch(repo_path, branch, name, email, current_sha, batch_updates):
                success = True
                # Sync working directory after successful fast-import
                try:
                    with open(full_path, "wb") as f:
                        f.write(temp_content)
                    subprocess.run(["git", "reset", "--quiet"], cwd=repo_path)
                except:
                    print("Warning: Index sync failed.")
            else:
                print("⚠️ Fast-import failed. Switching to compatibility mode.")
                use_fast_import = False
        
        # 3. Fallback to Slow Mode
        if not success:
            # Slow mode writes to disk directly, so we use that
            run_slow_batch(repo_path, filename, batch_updates)
            
        # 4. Update State
        current_content = temp_content
        total_processed += batch_size
        
        # 5. Push & Update SHA
        print("Pushing batch...")
        try:
            subprocess.run(["git", "push"], cwd=repo_path, check=True)
            # Fetch new SHA for next fast-import batch
            _, _, _, current_sha = get_git_info(repo_path)
        except:
            print("⚠️ Push failed. Continuing anyway...")

    elapsed = time.time() - start_time
    print(f"\n✅ Done! {num_commits} commits in {elapsed:.2f}s.")

if __name__ == "__main__":
    main()