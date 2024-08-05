import argparse
import os
import platform
import re
import subprocess
import sys
import yaml


def parse_command_line():
    print("parse_command_line")
    args_parser = argparse.ArgumentParser(description="Script description", conflict_handler='resolve')
    args_parser.add_argument("-h", "--help", action="help", help="Show this help message and exit")
    args_parser.add_argument("--config", type=str, help="Configuration file")
    args_parser.add_argument("-v", "--version", type=str, help="cr tool version")
    args_parser.add_argument("-d", "--charts-dir", type=str, help="Charts directory")
    args_parser.add_argument("-o", "--owner", type=str, required=True, help="Owner")
    args_parser.add_argument("-r", "--repo", type=str, required=True, help="Repo")
    args_parser.add_argument("-n", "--install-dir", type=str, help="Install directory")
    args_parser.add_argument("-i", "--install-only", action="store_true", help="Install only")
    args_parser.add_argument("-s", "--skip-packaging", action="store_true", help="Skip packaging")
    args_parser.add_argument("--skip-upload", action="store_true", help="Skip upload")
    args_parser.add_argument("-u", "--skip-update-index", action="store_true", help="Skip update index")

    args = args_parser.parse_args()

    # Handle required arguments and defaults
    if not args.install_dir:
        arch = platform.machine()
        tool_cache = os.environ['RUNNER_TOOL_CACHE']
        args.install_dir = f"{tool_cache}/cr/{args.version}/{arch}"

    if args.install_only:
        print("Will install cr tool and not run it...")
        install_chart_releaser(args.version)
        sys.exit(0)

    return args


def install_chart_releaser(version):
    """
    Installs the chart-releaser tool.
    :param version: The version of chart-releaser to install.
    :return: path to installed chart-releaser
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
    return install_dir


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
        return subprocess.check_output(
            ['git', 'rev-list', '--max-parents=0', '--first-parent', 'HEAD']).decode().strip()


def filter_charts(charts_dir):
    """
    Filters charts from a directory, checking for existence and Chart.yaml.
    Args:
        charts_dir (str): The directory containing charts.
    returns:
        str: Path to a valid Helm chart directory.
    """
    result = []
    for chart_dir in os.listdir(charts_dir):
        chart_path = os.path.join(charts_dir, chart_dir)
        chart_file = os.path.join(chart_path, 'Chart.yaml')
        if os.path.isfile(chart_file):
            result.append(chart_path)
        else:
            print(f"WARNING: {chart_file} is missing, assuming that '{chart_dir}' is not a Helm chart dir. Skipping.",
                  file=sys.stderr)
    return result


def lookup_changed_charts(commit, charts_dir):
    """
    Looks up charts changed in a specific git commit.
    Args:
        commit (str): The git commit hash.
        charts_dir (str): The directory containing charts.
    Returns:
        list: List of paths to changed charts.
    """

    result = []
    all_charts = filter_charts(charts_dir)
    for chart in all_charts:
        with open(f"{chart}/Chart.yaml", 'r') as stream:
            chart_yaml = yaml.safe_load(stream)
            version = chart_yaml['version']
            c = os.path.basename(chart)
            chart_full = f"{c}-{version}"
            tag = subprocess.check_output(["git", "tag", "-l", chart_full]).decode().strip()
            if tag == chart_full:
                # tag/release already exist
                print(f"Skipping chart {chart_full}, tag already exists")
            else:
                print(f"Chart {chart_full} doesn't have a tag")
                result.append(c)
    return result


def package_chart(cr_install_dir, chart_path, config=None):
    """
    Packages a Helm chart using cr.
    Args:
    :param cr_install_dir:
    :type chart_path: Path to the chart directory.
    :param config:  Path to a configuration file. Defaults to None.
    """
    args = [f'{cr_install_dir}/cr', 'package', chart_path, '--package-path', '.cr-release-packages']
    if config:
        args.extend(['--config', config])
    result = subprocess.check_output(args).decode().strip()
    print(f"Packaged chart {chart_path}: {result}")


def release_charts(cr_install_dir, owner, repo, config=None):
    """Releases charts using cr.

    Args:
        owner (str): The chart owner.
        repo (str): The chart repository.
        config (str, optional): Path to a configuration file. Defaults to None.
    """

    args = [f'{cr_install_dir}/cr', "upload", "-o", owner, "-r", repo, "-c",
            subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()]
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
    skip_upload = args.skip_upload

    # Check for required environment variable
    cr_token = os.environ.get("CR_TOKEN")
    if not cr_token:
        print("Environment variable CR_TOKEN must be set", file=sys.stderr)
        sys.exit(1)

    if not skip_packaging:
        print('Looking up latest tag...')
        latest_tag = lookup_latest_tag()
        print(f"Discovering changed charts since '{latest_tag}'...")
        changed_charts = lookup_changed_charts(latest_tag, charts_dir)

        print(f"changed charts: {changed_charts}")
        if changed_charts:
            cr_install_dir = install_chart_releaser(version=version)  # Replace with actual version if needed
            cwd = os.getcwd()
            print(f"current dir: {cwd}")
            print(f"list dir: {os.listdir()}")

            os.makedirs(".cr-release-packages", exist_ok=True)
            os.makedirs(".cr-index", exist_ok=True)

            for chart in changed_charts:
                chart_dir = os.path.join(charts_dir, chart)
                if os.path.isdir(chart_dir):
                    package_chart(cr_install_dir, chart_dir, config)
                else:
                    print(f"Chart '{chart}' no longer exists in repo. Skipping it...")

            if not skip_upload:
                release_charts(owner, repo, config)
            if not skip_update_index:
                update_index(owner, repo, config)
        else:
            print("Nothing to do. No chart changes detected.")
    else:
        cr_install_dir = install_chart_releaser(version)  # Replace with actual version if needed
        os.makedirs(".cr-index", exist_ok=True)
        release_charts(owner, repo, config)
        if not skip_update_index:
            update_index(owner, repo, config)


if __name__ == "__main__":
    #lookup_changed_charts("d4161a19", "/home/veziak/projects/geekcard/geekcard-charts/charts")
    main()
