import os
import shutil
import subprocess
import json
import re

REPOSITORIES_PATH = os.path.join(os.path.dirname(__file__), "..", "repositories")
BUGS_PATH = os.path.join(os.path.dirname(__file__), "..", "bugs")
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data")


def get_bug_branches(project_path):
    branches = []
    cmd = "cd %s; git branch -a" % project_path
    output = subprocess.check_output(cmd, shell=True)
    output = output.decode('utf-8') if isinstance(output, bytes) else output
    for line in output.split():
        if "bugs-dot-jar_" in line and line.endswith("_HOTFIX"):
            branches.append(line.replace(")", ""))
    return branches


def extract_bug_id(branch):
    tmp = branch[branch.index("_") + 1::]
    tmp = tmp[tmp.index("-") + 1::]
    remove_hotfix = tmp.rsplit("_HOTFIX", 1)[0]
    return remove_hotfix.split("_")


def create_bug(project_path, branch_name, destination):
    FNULL = open(os.devnull, 'w')

    # Clone the repo to the destination
    repo_url = "https://github.com/carolhanna01/flink.git"
    cmd = "git clone %s %s" % (repo_url, destination)
    print(cmd)
    subprocess.check_call(cmd, shell=True, stdout=FNULL, stderr=FNULL)

    # Checkout the desired branch
    cmd = "cd %s; git checkout %s" % (destination, branch_name)
    print(cmd)
    subprocess.check_call(cmd, shell=True, stdout=FNULL, stderr=FNULL)

    # Filter out test files from the patch
    cmd = "cd %s;  git apply .bugs-dot-jar/developer-patch.diff; git diff --ignore-all-space --minimal --ignore-blank-lines;" % destination

    print(cmd)
    human_patch = subprocess.check_output(cmd, shell=True)
    cmd = "cd %s;  git checkout -- .;" % destination
    print(cmd)
    subprocess.call(cmd, shell=True, stdout=FNULL, stderr=FNULL)
    with open(os.path.join(destination, ".bugs-dot-jar", "developer-patch.diff"), 'w') as fd:
        fd.write(human_patch.decode('utf-8'))


def get_human_patch(bug_path):
    diff_patch = os.path.join(bug_path, ".bugs-dot-jar", "developer-patch.diff")
    with open(diff_patch) as fd:
        return fd.read()

def find_full_class_path(maven_log, class_name):
    """
    Search the Maven log to find the full package path for a given class name.
    Looks for patterns like "in org.apache.flink.streaming.api.operators.OneInputStreamTaskTest"
    """
    # Pattern to find "in full.package.path.ClassName"
    pattern = rf"in\s+([\w\.]+\.{re.escape(class_name)})(?:\s|$)"
    matches = re.findall(pattern, maven_log)
    
    if matches:
        # Return the first (or most common) full path found
        return matches[0]
    
    # Alternative pattern: look for "Tests run: X ... - in full.package.path.ClassName"
    pattern2 = rf"Tests run:.*?-\s+in\s+([\w\.]+\.{re.escape(class_name)})(?:\s|$)"
    matches2 = re.findall(pattern2, maven_log)
    
    if matches2:
        return matches2[0]
    
    # If no full path found, return None
    return None

def get_failing_tests(bug_path):
    tests = []
    diff_patch = os.path.join(bug_path, ".bugs-dot-jar", "test-results.txt")
    total = failure = error = skipped = 0

    with open(diff_patch) as fd:
        maven_log = fd.read()

        # Check for multiple Results patterns
        has_results = ("Results :" in maven_log) or ("Results:" in maven_log)
        if not has_results:
            print("[Error] Test results not found: %s" % bug_path)
            return tests, total, failure, error, skipped
        
        # Extract test summary line - search from bottom by taking the last match
        all_matches = re.findall(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", maven_log)
        if all_matches:
            # Take the last match (from bottom of file)
            last_match = all_matches[-1]
            total = int(last_match[0])
            failure = int(last_match[1])
            error = int(last_match[2])
            skipped = int(last_match[3])
        
        # Try multiple patterns for failing tests extraction
        failed_tests_patterns = [
            # Pattern 1: Original format - "Failed tests:"
            (r"Failed tests:\s*(.*?)(?=\n\s*Tests run:)", "Failed tests:"),
            # Pattern 2: Maven ERROR format with [INFO] before Tests run
            (r"\[ERROR\]\s*Failures:\s*\n(.*?)(?=\[INFO\]\s*\n\[ERROR\]\s*Tests run:)", "[ERROR] Failures with [INFO]:"),
            # Pattern 3: NEW - Maven ERROR format without [INFO] before Tests run
            (r"\[ERROR\]\s*Failures:\s*\n(.*?)(?=\[ERROR\]\s*Tests run:)", "[ERROR] Failures direct:"),
            # Pattern 4: Alternative Maven format
            (r"Failures:\s*(.*?)(?=\n.*Tests run:)", "Failures:"),
        ]
        
        for pattern, description in failed_tests_patterns:
            failed_tests_section = re.search(pattern, maven_log, re.DOTALL)
            print(f"Trying pattern: {description}")
            if failed_tests_section:
                print(f"SUCCESS: Using pattern: {description}")
                content = failed_tests_section.group(1).strip()
                print(f"DEBUG: Captured content: '{content[:200]}...'")  # Debug output
                
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    # Remove ANSI color codes and Maven prefixes
                    line = re.sub(r'\[\[1;3[1-7]m[^]]*\]', '', line)  # Remove ANSI colors
                    line = re.sub(r'^\[ERROR\]\s*', '', line)
                    line = re.sub(r'^\[INFO\]\s*', '', line)
                    
                    if line and not line.startswith("Tests run:"):
                        print(f"DEBUG: Processing line: '{line}'")
                        # Match pattern like: StreamingFileWriterTest.testFailover:94
                        match = re.match(r"(\w+)\.(\w+):\d+", line)
                        if match:
                            class_name = match.group(1)
                            method_name = match.group(2)
                            print(f"DEBUG: Found test - Class: {class_name}, Method: {method_name}")
                            
                            # Search for the full package path in the maven log
                            full_path = find_full_class_path(maven_log, class_name)
                            if full_path:
                                test_name = f"{full_path}.{method_name}"
                            else:
                                test_name = f"{class_name}.{method_name}"
                            
                            # Avoid duplicates
                            if test_name not in tests:
                                tests.append(test_name)
                                print(f"Added failing test: {test_name}")
                break  # Stop trying patterns once we find a match

    return tests, total, failure, error, skipped

project_name = "flink"
project_path = os.path.join(REPOSITORIES_PATH, project_name)
bug_project_path = os.path.join(BUGS_PATH, project_name)
project_data_path = os.path.join(DATA_PATH, project_name)

if not os.path.exists(bug_project_path):
    os.makedirs(bug_project_path)

if not os.path.exists(project_data_path):
    os.makedirs(project_data_path)

branches = get_bug_branches(project_path)

for branch in branches:
    (jira_id, commit) = extract_bug_id(branch)
    bug_path = os.path.join(bug_project_path, commit)
    bug_data_path = os.path.join(project_data_path, commit + ".json")

    if not os.path.exists(bug_path):
        print("[Checkout] %s %s %s" % (project_name, jira_id, commit))
        create_bug(project_path, branch, bug_path)

    bug = {
        "project": project_name,
        "jira_id": jira_id,
        "commit": commit,
        "classification": {}
    }

    # human patch
    bug['patch'] = get_human_patch(bug_path)
    bug['files'] = bug['patch'].count("+++ b/")
    bug['linesAdd'] = bug['patch'].count("\n+") - bug['files']
    bug['linesRem'] = bug['patch'].count("\n-") - bug['files']
    bug["classification"]['singleLine'] = (bug['linesAdd'] == 1 and bug['linesRem'] == 0) or (
        bug['linesAdd'] == 0 and bug['linesRem'] == 1)

    # failing tests
    (tests, total, failure, error, skipped) = get_failing_tests(bug_path)
    bug['failing_tests'] = tests
    bug['nb_test'] = total
    bug['nb_failure'] = failure
    bug['nb_error'] = error
    bug['nb_skipped'] = skipped

    with open(bug_data_path, 'w') as fd:
        json.dump(bug, fd, indent=2)

    with open(os.path.join(bug_path, ".bugs-dot-jar", "info.json"), 'w') as fd:
        json.dump(bug, fd, indent=2)