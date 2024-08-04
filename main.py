import argparse
import os
import re
import subprocess
import sys

def parse_command_line():
    parser = argparse.ArgumentParser(description="Script description")
    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit")
    parser.add_argument("--config", type=str, help="Configuration file")
    parser.add_argument("-v", "--version", type=str, help="Version")
    parser.add_argument("-d", "--charts-dir", type=str, help="Charts directory")
    parser.add_argument("-o", "--owner", type=str, required=True, help="Owner")
    parser.add_argument("-r", "--repo", type=str, required=True, help="Repo")
    parser.add_argument("-n", "--install-dir", type=str, help="Install directory")
    parser.add_argument("-i", "--install-only", action="store_true", help="Install only")
    parser.add_argument("-s", "--skip-packaging", action="store_true", help="Skip packaging")
    parser.add_argument("-u", "--skip-update-index", action="store_true", help="Skip update index")

    args = parser.parse_args()

    # Handle required arguments and defaults
    if not args.install_dir:
        arch = os.uname()[4]  # Assuming uname returns a tuple
        args.install_dir = f"{os.environ['RUNNER_TOOL_CACHE']}/cr/{args.version}/{arch}"

    if args.install_only:
        print("Will install cr tool and not run it...")
        # Replace with your install_chart_releaser function
        install_chart_releaser()
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

        print(f"Installing chart-releaser on {install_dir}...")
        url = f"https://github.com/helm/chart-releaser/releases/download/{version}/chart-releaser_{version[1:]}_linux_amd64.tar.gz"
        subprocess.run(['curl', '-sSLo', 'cr.tar.gz', url], check=True)
        subprocess.run(['tar', '-xzf', 'cr.tar.gz', '-C', install_dir], check=True)
        os.remove('cr.tar.gz')

    # Add cr directory to PATH (consider environment variables instead of modifying PATH directly)
    print('Adding cr directory to PATH...')
    # os.environ['PATH'] = f"{install_dir}:{os.environ['PATH']}"  # Not recommended

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

def filter_charts(chart_dir):
    """
    Filters charts from a directory, checking for existence and Chart.yaml.
    Args:
        chart_dir (str): The directory containing charts.
    Yields:
        str: Path to a valid Helm chart directory.
    """

    for chart in os.listdir(chart_dir):
        chart_path = os.path.join(chart_dir, chart)
        if not os.path.isdir(chart_path):
            continue
        chart_file = os.path.join(chart_path, 'Chart.yaml')
        if os.path.isfile(chart_file):
            yield chart_path
        else:
            print(f"WARNING: {chart_file} is missing, assuming that '{chart}' is not a Helm chart. Skipping.", file=sys.stderr)

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

