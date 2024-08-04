import argparse
import os
import platform
import re
import subprocess
import sys

def parse_command_line():
    print("parse_command_line")
    args_parser = argparse.ArgumentParser(description="Script description", conflict_handler='resolve')
    args_parser.add_argument("-h", "--help", action="help", help="Show this help message and exit")
    args_parser.add_argument("--config", type=str, help="Configuration file")
    args_parser.add_argument("-v", "--version", type=str, help="Version")
    args_parser.add_argument("-d", "--charts-dir", type=str, help="Charts directory")
    args_parser.add_argument("-o", "--owner", type=str, required=True, help="Owner")
    args_parser.add_argument("-r", "--repo", type=str, required=True, help="Repo")
    args_parser.add_argument("-n", "--install-dir", type=str, help="Install directory")
    args_parser.add_argument("-i", "--install-only", action="store_true", help="Install only")
    args_parser.add_argument("-s", "--skip-packaging", action="store_true", help="Skip packaging")
    args_parser.add_argument("-u", "--skip-update-index", action="store_true", help="Skip update index")

    args = args_parser.parse_args()

    # Handle required arguments and defaults
    if not args.install_dir:
        arch = platform.machine()
        tool_cache = os.environ['RUNNER_TOOL_CACHE']
        args.install_dir = f"{tool_cache}/cr/{args.version}/{arch}"

    if args.install_only:
        print("Will install cr tool and not run it...")
        # Replace with your install_chart_releaser function
        #install_chart_releaser()
        sys.exit(0)

    return args

def install_chart_releaser(version):
    """
    Installs the chart-releaser tool.
    Args:
        version (str): The version of chart-releaser to install.
    """

    cache_dir = os.environ.get('RUNNER_TOOL_CACHE')
    if not cache_dir or not os.path.isdir(cache_dir):
        print(f"Cache directory '{cache_dir}' does not exist", file=sys.stderr)
        sys.exit(1)

    install_dir = os.path.join(cache_dir, 'cr', version)
    if not os.path.isdir(install_dir):
        os.makedirs(install_dir, exist_ok=True)
        print(f"Installing chart-releaser on {install_dir}")
        url = f"https://github.com/helm/chart-releaser/releases/download/{version}/chart-releaser_{version[1:]}_linux_amd64.tar.gz"
        subprocess.run(['curl', '-sSLo', 'cr.tar.gz', url], check=True)
        subprocess.run(['tar', '-xzf', 'cr.tar.gz', '-C', install_dir], check=True)
        os.remove('cr.tar.gz')
        subprocess.run(['ls'], check=True)

    # Add cr directory to PATH (consider environment variables instead of modifying PATH directly)
    print('Adding cr directory to PATH...')
    os.environ['PATH'] = f"{install_dir}:{os.environ['PATH']}"  # Not recommended

def lookup_latest_tag():
    """
    Looks up the latest tag using git.
    Returns:
        str: The latest tag or commit hash if no tags exist.
    """

    subprocess.run(['git', 'fetch', '--tags'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return subprocess.check_output(['git', 'describe', '--tags', '--abbrev=0']).decode().strip()
    except subprocess.CalledProcessError:
        return subprocess.check_output(['git', 'rev-list', '--max-parents=0', '--first-parent', 'HEAD']).decode().strip()

def filter_charts(charts_dir):
    """
    Filters charts from a directory, checking for existence and Chart.yaml.
    Args:
        charts_dir (str): The directory containing charts.
    returns:
        str: Path to a valid Helm chart directory.
    """
    for chart_dir in os.listdir(charts_dir):
        print(f"chart_dir: {chart_dir}")
        chart_path = os.path.join(charts_dir, chart_dir)
        chart_file = os.path.join(chart_path, 'Chart.yaml')
        if os.path.isfile(chart_file):
            yield chart_path
        else:
            print(f"WARNING: {chart_file} is missing, assuming that '{chart_dir}' is not a Helm chart dir. Skipping.", file=sys.stderr)

def lookup_changed_charts(commit, charts_dir):
    """
    Looks up charts changed in a specific git commit.
    Args:
        commit (str): The git commit hash.
        charts_dir (str): The directory containing charts.
    Returns:
        list: List of paths to changed charts.
    """

    depth = len(re.findall(r'[^\/]', charts_dir)) + 1
    fields = f"1-{depth}"

    try:
        changed_files = subprocess.check_output(['git', 'diff', '--find-renames', '--name-only', commit, charts_dir]).decode().strip()
    except subprocess.CalledProcessError:
        changed_files = ""

    return [os.path.join(charts_dir, f) for f in set(re.split(r'/', changed_files)) if f]

def package_chart(chart, config=None):
    """
    Packages a Helm chart using cr.
    Args:
        chart (str): Path to the chart directory.
        config (str, optional): Path to a configuration file. Defaults to None.
    """

    args = ['cr', 'package', chart, '--package-path', '.cr-release-packages']
    if config:
        args.extend(['--config', config])


def release_charts(owner, repo, config=None):
    """Releases charts using cr.

    Args:
        owner (str): The chart owner.
        repo (str): The chart repository.
        config (str, optional): Path to a configuration file. Defaults to None.
    """

    args = ["cr", "upload", "-o", owner, "-r", repo, "-c", subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()]
    if config:
        args.extend(["--config", config])

    print("Releasing charts...")
    subprocess.run(args, check=True)

def update_index(owner, repo, config=None):
    """Updates the charts repo index using cr.
    Args:
        owner (str): The chart owner.
        repo (str): The chart repository.
        config (str, optional): Path to a configuration file. Defaults to None.
    """
    args = ["cr", "index", "-o", owner, "-r", repo, "--push"]
    if config:
        args.extend(["--config", config])
    print("Updating charts repo index...")
    subprocess.run(args, check=True)

def main():
    args = parse_command_line()
    version = args.version
    config = args.config
    charts_dir = args.charts_dir
    owner = args.owner
    repo = args.repo
    skip_packaging = args.skip_packaging
    skip_update_index = args.skip_update_index

    # Check for required environment variable
    cr_token = os.environ.get("CR_TOKEN")
    if not cr_token:
        print("Environment variable CR_TOKEN must be set", file=sys.stderr)
        sys.exit(1)

    # Change to repo root
    repo_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
    os.chdir(repo_root)

    if not skip_packaging:
        print('Looking up latest tag...')
        latest_tag = lookup_latest_tag()
        print(f"Discovering changed charts since '{latest_tag}'...")
        changed_charts = lookup_changed_charts(latest_tag, charts_dir)

        print(f"changed charts: {changed_charts}")
        if changed_charts:
            install_chart_releaser(version=version)  # Replace with actual version if needed
            cwd = os.getcwd()
            print(f"current dir: {cwd}")

            os.makedirs(".cr-release-packages", exist_ok=True)
            os.makedirs(".cr-index", exist_ok=True)

            for chart in changed_charts:
                if os.path.isdir(chart):
                    package_chart(chart, config)
                else:
                    print(f"Chart '{chart}' no longer exists in repo. Skipping it...")

            release_charts(owner, repo, config)
            if not skip_update_index:
                update_index(owner, repo, config)
        else:
            print("Nothing to do. No chart changes detected.")
    else:
        install_chart_releaser(version)  # Replace with actual version if needed
        os.makedirs(".cr-index", exist_ok=True)
        release_charts(owner, repo, config)
        if not skip_update_index:
            update_index(owner, repo, config)

if __name__ == "__main__":
    main()