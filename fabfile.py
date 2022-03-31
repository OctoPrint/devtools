from __future__ import print_function, unicode_literals, absolute_import

from fabric.api import (
    local,
    lcd,
    run,
    sudo,
    cd,
    prompt,
    get,
    put,
    hosts,
    settings,
    task,
)
from fabric.utils import abort
from fabric.state import env
from fabric.contrib import files

import datetime
import sys
import os
import codecs
import yaml
import time
import requests
import webbrowser
import datetime
import pkg_resources

from io import StringIO, BytesIO, TextIOWrapper


def env_from_yaml(path):
    import yaml

    with codecs.open(path, errors="replace") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        abort(
            "YAML file at {} doesn't contain a dictionary, can't use that for setting env"
        )

    for key, value in data.items():
        setattr(env, key, value)


env_from_yaml("./fabfile.yaml")
env.disable_known_hosts = True
env.no_keys = True

env.target = os.environ.get("TARGET", None)
env.tag = os.environ.get("TAG", None)


def dict_merge(a, b, leaf_merger=None):
    """
    Recursively deep-merges two dictionaries.

    Taken from https://www.xormedia.com/recursively-merge-dictionaries-in-python/

    Arguments:
        a (dict): The dictionary to merge ``b`` into
        b (dict): The dictionary to merge into ``a``
        leaf_merger (callable): An optional callable to use to merge leaves (non-dict values)

    Returns:
        dict: ``b`` deep-merged into ``a``
    """

    from copy import deepcopy

    if a is None:
        a = dict()
    if b is None:
        b = dict()

    if not isinstance(b, dict):
        return b
    result = deepcopy(a)
    for k, v in b.items():
        if k in result and isinstance(result[k], dict):
            result[k] = dict_merge(result[k], v, leaf_merger=leaf_merger)
        else:
            merged = None
            if k in result and callable(leaf_merger):
                try:
                    merged = leaf_merger(result[k], v)
                except ValueError:
                    # can't be merged by leaf merger
                    pass

            if merged is None:
                merged = deepcopy(v)

            result[k] = merged
    return result


def normalize_version(version):
    if "-" in version:
        version = version[: version.find("-")]

    # Debian has the python version set to 2.7.15+ which is not PEP440 compliant (bug 914072)
    if version.endswith("+"):
        version = version[:-1]

    if version[0].lower() == "v":
        version = version[1:]

    return version.strip()


def get_comparable_version(version_string, cut=None, **kwargs):
    """
    Args:
        version_string: The version string for which to create a comparable version instance
        cut: optional, how many version digits to remove (e.g., cut=1 will turn 1.2.3 into 1.2).
             Defaults to ``None``, meaning no further action. Settings this to 0 will remove
             anything up to the last digit, e.g. dev or rc information.

    Returns:
        A comparable version
    """

    if "base" in kwargs and kwargs.get("base", False) and cut is None:
        cut = 0
    if cut is not None and (cut < 0 or not isinstance(cut, int)):
        raise ValueError("level must be a positive integer")

    version_string = normalize_version(version_string)
    version = pkg_resources.parse_version(version_string)

    if cut is not None:
        # new setuptools
        version = pkg_resources.parse_version(version.base_version)
        if cut is not None:
            parts = version.base_version.split(".")
            if 0 < cut < len(parts):
                reduced = parts[:-cut]
                version = pkg_resources.parse_version(
                    ".".join(str(x) for x in reduced)
                )

    return version

##~~ Release testing ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@task
def sync_test_repo(force=False):
    """sync local checkout with testrepo"""
    with lcd(env.octoprint):
        for branch in (
            "master",
            "maintenance",
            "staging/maintenance",
            "rc/maintenance",
            "devel",
            "rc/devel",
        ):
            local("git checkout {}".format(branch))
            if force:
                local("git push --force releasetest {}".format(branch))
            else:
                local("git push releasetest {}".format(branch))


@task
def merge_and_push(branch="master", force=False):
    with lcd(env.octoprint):
        for pushbranch in (
            "rc/maintenance",
            "rc/devel",
            "staging/maintenance",
            "staging/devel",
        ):
            local("git checkout {}".format(pushbranch))
            local("git merge {}".format(branch))
            if force:
                local("git push --force")
            else:
                local("git push")


def test_branch(release_branch, prep_branch, dev_branch, tag=None, force=False):
    if tag is None:
        tag = env.tag

    if tag is None:
        abort("Tag needs to be set")

    if tag.endswith("rc1"):
        merge_tag_push_test_repo(release_branch, dev_branch, tag, force=force)
    else:
        merge_tag_push_test_repo(release_branch, prep_branch, tag, force=force)


@task
def test_rc_devel(tag=None, force=False):
    """prep devel rc on testrepo"""
    test_branch("rc/devel", "staging/devel", "devel", tag=tag, force=force)


@task
def test_rc_maintenance(tag=None, force=False):
    """prep maintenance rc on testrepo"""
    test_branch(
        "rc/maintenance", "staging/maintenance", "maintenance", tag=tag, force=force
    )


@task
def test_stable(tag=None, force=False):
    """prep stable release on testrepo"""
    test_rc_maintenance(tag=tag, force=force)
    merge_push_test_repo("master", "rc/maintenance")
    merge_push_test_repo("rc/devel", "rc/maintenance")


@task
def test_bugfix(tag=None, force=False):
    """prep bugfix release on testrepo"""
    if tag is None:
        tag = env.tag

    if tag is None:
        abort("Tag needs to be set")

    merge_tag_push_test_repo("master", "staging/bugfix", tag, force=force)


def merge_tag_push_test_repo(push_branch, merge_branch, tag=None, force=False):
    # merge, tag and push to testrepo
    if tag is None:
        tag = env.tag

    if tag is None:
        abort("Tag needs to be set")

    with lcd(env.octoprint):
        local("git fetch --tags -f releasetest")
        local("git checkout {}".format(push_branch))
        local("git merge {}".format(merge_branch))

        if force:
            local("git tag -d {}".format(tag))
        local("git tag {}".format(tag))

        local("git push releasetest {}".format(push_branch))
        local("git push --tags releasetest {}".format(tag))


def merge_push_test_repo(push_branch, merge_branch):
    # merge and push to testrepo
    with lcd(env.octoprint):
        local("git checkout {}".format(push_branch))

        local("git merge {}".format(merge_branch))

        local("git push releasetest {}".format(push_branch))


##~~ Local install testing ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def venv_executable(venv, executable):
    if sys.platform == "win32":
        return "{}\\Scripts\\{}.exe".format(venv, executable)
    else:
        return "{}/bin/{}".format(venv, executable)


def test_install(tag, python, target="wheel"):
    # test local install of tag against python version and wheel/sdist
    if tag is None:
        tag = env.tag

    if tag is None:
        abort("Tag needs to be set")

    basedir = "testconf-dist"
    venv = "venv-dist"

    with lcd(env.octoprint):
        if not os.path.exists(os.path.join("dist", "OctoPrint-{}.tar.gz".format(tag))):
            local("{} setup.py sdist bdist_wheel".format(sys.executable))

        local("rm -rf {} || true".format(venv))
        local("rm -rf {} || true".format(basedir))

        local(
            "{} -m virtualenv --python={} {}".format(
                env.python37, getattr(env, python), venv
            )
        )
        if target == "wheel":
            local(
                "{} -m pip install dist/OctoPrint-{}-py2.py3-none-any.whl".format(
                    venv_executable(venv, "python"), tag
                )
            )
        elif target == "sdist":
            local(
                "{} -m pip install dist/OctoPrint-{}.tar.gz".format(
                    venv_executable(venv, "python"), tag
                )
            )

        local(
            "{} serve --debug --basedir {} --port 5001".format(
                venv_executable(venv, "octoprint"), basedir
            )
        )


@task
def test_sdist(python, tag=None):
    """test sdist install of tag against python version"""
    test_install(tag, python, target="sdist")


@task
def test_wheel(python, tag=None):
    """test wheel install of tag against python version"""
    test_install(tag, python, target="wheel")


##~~ FlashHost ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def format_serial(serial):
    return "0" * (12 - len(serial)) + serial


def disk_device(serial):
    return "/dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_{}-0:0".format(
        format_serial(serial)
    )


def boot_part_device(serial):
    return "/dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_{}-0:0-part1".format(
        format_serial(serial)
    )

def mqtt_annotate(target, text):
    if env.flashhost.get("mqtt_annotation"):
        run("{} {} \"{}\"".format(env.flashhost["mqtt_annotation"], target, text))

def read_file(path):
    fd = BytesIO()
    try:
        get(path, fd)
        fd.seek(0)
        return fd.read()
    finally:
        fd.close()

def write_file(path, data, use_sudo=False):
    fd = BytesIO()
    try:
        fd.write(data)
        fd.seek(0)
        put(fd, path, use_sudo=use_sudo)
    finally:
        fd.close()

def print_file(path):
    print("-" * len(path))
    print(path)
    print("-" * len(path))
    print(read_file(path).decode("utf-8"))

@task
@hosts("pi@flashhost.lan")
def flashhost_release_lock():
    """release flash lock if left set for some reason"""
    lock = env.flashhost["flashlock"]
    sudo("rm -rf {}".format(lock))


@task
@hosts("pi@flashhost.lan")
def flashhost_flash(version, target=None):
    """flashes target with OctoPi image of provided version using dd"""
    lockfile = env.flashhost["flashlock"]
    imagefile = "{}/octopi-{}.img".format(env.flashhost["images"], version)

    if target is None:
        target = env.target
    if not target in env.targets:
        abort("Unknown target: {}".format(target))
    if not files.exists(imagefile):
        abort("Image not available: {}".format(imagefile))
    serial = env.targets[target]["serial"]
    targetdev = disk_device(serial)

    sudo(
        "flock -w600 {} dd bs=4M if={} of={} status=progress conv=fsync".format(
            lockfile, imagefile, targetdev
        )
    )


def flashhost_provision_octopi(target, boot):
    hostname = env.targets[target]["hostname"]
    password = env.password

    files.upload_template(
        "octopi-wpa-supplicant.txt",
        boot + "/octopi-wpa-supplicant.txt",
        context=dict(ssid=env.wifi_ssid, psk=env.wifi_psk, country=env.wifi_country),
        use_jinja=True,
        template_dir="templates",
        backup=False,
        keep_trailing_newline=True,
        use_sudo=True,
    )
    files.upload_template(
        "octopi-network.txt",
        boot + "/octopi-network.txt",
        context=dict(ssid=env.wifi_ssid, psk=env.wifi_psk),
        use_jinja=True,
        template_dir="templates",
        backup=False,
        keep_trailing_newline=True,
        use_sudo=True,
    )
    files.upload_template(
        "octopi-hostname.txt",
        boot + "/octopi-hostname.txt",
        context=dict(hostname=hostname),
        use_jinja=True,
        template_dir="templates",
        backup=False,
        keep_trailing_newline=True,
        use_sudo=True,
    )
    files.upload_template(
        "octopi-password.txt",
        boot + "/octopi-password.txt",
        context=dict(password=password),
        use_jinja=True,
        template_dir="templates",
        backup=False,
        keep_trailing_newline=True,
        use_sudo=True,
    )

def flashhost_provision_firstrun(target, boot):
    from passlib.hash import sha512_crypt

    hostname = env.targets[target]["hostname"]
    user = env.targets[target].get("user", "pi")
    password = env.password

    passwordhash = sha512_crypt.using(rounds=5000).hash(password)

    files.upload_template(
        "firstrun.sh",
        boot + "/firstrun.sh",
        context=dict(
            hostname=hostname,
            user=user,
            passwordhash=passwordhash,
            ssid=env.wifi_ssid,
            psk=env.wifi_psk,
            country=env.wifi_country,
        ),
        use_jinja=True,
        template_dir="templates",
        backup=False,
        keep_trailing_newline=True,
        use_sudo=True,
    )
    print_file(boot + "/firstrun.sh")

    cmdline = read_file(boot + "/cmdline.txt").strip()
    if b"firstrun.sh" not in cmdline:
        cmdline += b" systemd.run=/boot/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target"
        write_file(boot + "/cmdline.txt", cmdline, use_sudo=True)
        print_file(boot + "/cmdline.txt")

@task
@hosts("pi@flashhost.lan")
def flashhost_provision(target=None, firstrun=False):
    """provisions target with wifi, hostname, password and boot_delay"""
    if target is None:
        target = env.target
    if not target in env.targets:
        abort("Unknown target: {}".format(target))

    serial = env.targets[target]["serial"]
    boot = boot_part_device(serial)
    mount = "{}/{}".format(env.flashhost["mounts"], target)

    if not files.exists(mount):
        run("mkdir -p {}".format(mount))

    if not files.exists(mount + "/cmdline.txt"):
        sudo("mount {} {}".format(boot, mount))

    if firstrun:
        flashhost_provision_firstrun(target, mount)
    else:
        flashhost_provision_octopi(target, mount)

    files.append(mount + "/config.txt", "boot_delay=3", use_sudo=True)
    sudo("umount {}".format(mount))


@task
@hosts("pi@flashhost.lan")
def flashhost_host(target=None):
    """switches target to Host mode (powered off & USB-SD-MUX Host)"""
    if target is None:
        target = env.target
    if not target in env.targets:
        abort("Unknown target: {}".format(target))
    usbport = env.targets[target]["usbport"]
    serial = env.targets[target]["serial"]

    sudo("{} -d {}".format(env.flashhost["ykush"], usbport))
    sudo(
        "{} /dev/usb-sd-mux/id-{} host".format(
            env.flashhost["usbsdmux"], format_serial(serial)
        )
    )
    time.sleep(5.0)

    mqtt_annotate(target, "Switched {} to Host mode".format(target))


@task
@hosts("pi@flashhost.lan")
def flashhost_dut(target=None):
    """switches target to DUT mode (USB-SD-MUX DUT & powered on)"""
    if target is None:
        target = env.target
    if not target in env.targets:
        abort("Unknown target: {}".format(target))
    usbport = env.targets[target]["usbport"]
    serial = env.targets[target]["serial"]

    sudo(
        "{} /dev/usb-sd-mux/id-{} dut".format(
            env.flashhost["usbsdmux"], format_serial(serial)
        )
    )
    sudo("{} -u {}".format(env.flashhost["ykush"], usbport))
    if env.targets[target].get("um25c"):
        sudo("systemctl restart {}".format(env.targets[target]["um25c"]))

    mqtt_annotate(target, "Switched {} to DUT mode".format(target))


@task
@hosts("pi@flashhost.lan")
def flashhost_reboot(target=None):
    """powers target off and on again"""
    if target is None:
        target = env.target
    if not target in env.targets:
        abort("Unknown target: {}".format(target))
    usbport = env.targets[target]["usbport"]

    sudo("{} -d {}".format(env.flashhost["ykush"], usbport))
    time.sleep(1.0)
    sudo("{} -u {}".format(env.flashhost["ykush"], usbport))

    mqtt_annotate(target, "Rebooted {}".format(target))


@task
@hosts("pi@flashhost")
def flashhost_flash_and_provision(version, target=None, firstrun=False):
    """runs flash & provision cycle on target for specified OctoPi version"""
    if target is None:
        target = env.target
    flashhost_host(target=target)
    flashhost_flash(version, target=target)
    print("Flashing done, giving the system a bit to recover...")
    time.sleep(5.0)
    print("... done")
    flashhost_provision(target=target, firstrun=firstrun)
    flashhost_dut(target=target)

@task
@hosts("pi@flashhost")
def flashhost_list_images():
    path = env.flashhost["images"]
    print("Available images:")
    for f in run("ls -1 {}".format(path), quiet=True).split("\n"):
        f = f.strip()
        if not f.startswith("octopi-") or not f.endswith(".img"):
            continue
        print("  {}".format(f[len("octopi-"):-len(".img")]))

##~~ OctoPi ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def release_patch(
    key, tag, repo, additional_repos=None, branch="master", prerelease=False, pip=None
):
    # generate release patch
    now = datetime.datetime.utcnow().replace(microsecond=0).isoformat(" ")

    tag_name = "{} (release candidate)" if prerelease else "{} (stable)"
    tag_name = tag_name.format(tag)

    if additional_repos is None:
        additional_repos = []

    checks = dict()
    if pip is not None:
        checks[key] = dict(pip=pip)

    release = dict(
        draft=False,
        html_url="https://github.com/{}/releases/tag/{}".format(repo, tag),
        name=tag_name,
        prerelease=prerelease,
        published_at=now,
        tag_name=tag,
        target_commitish=branch,
    )

    releases = dict()
    releases[repo] = [
        release,
    ]
    for repo in additional_repos:
        releases[repo] = [
            release,
        ]

    config = dict(
        plugins=dict(
            github_release_patcher=dict(releases=releases),
            softwareupdate=dict(checks=checks),
        )
    )

    return config


def release_patch_octoprint(tag, branch, prerelease):
    return release_patch(
        "octoprint",
        tag,
        "OctoPrint/OctoPrint",
        additional_repos=[
            "foosel/OctoPrint",
        ],
        branch=branch,
        prerelease=prerelease,
        pip="{}/archive/{{target_version}}.zip".format(env.releasetest_repo),
    )


def release_patch_filecheck(tag, branch="master"):
    return release_patch(
        "file_check",
        tag,
        "OctoPrint/OctoPrint-FileCheck",
        branch=branch,
        pip="https://github.com/OctoPrint/OctoPrint-FileCheck/archive/{}.zip".format(
            branch
        ),
    )


def release_patch_firmwarecheck(tag, branch="master"):
    return release_patch(
        "firmware_check",
        tag,
        "OctoPrint/OctoPrint-FirmwareCheck",
        branch=branch,
        pip="https://github.com/OctoPrint/OctoPrint-FirmwareCheck/archive/{}.zip".format(
            branch
        ),
    )


@task
def octopi_reboot():
    """reboots the system"""
    sudo("shutdown -r now")


@task
def octopi_octoservice(command):
    """run service command"""
    sudo("service octoprint {}".format(command))


def octopi_standardrepo():
    """set standard repo"""
    if files.exists("~/OctoPrint/.git"):
        run(
            "cd ~/OctoPrint && git remote set-url origin https://github.com/OctoPrint/OctoPrint"
        )


def octopi_releasetestrepo():
    """set releasetest repo"""
    if files.exists("~/OctoPrint/.git"):
        run(
            "cd ~/OctoPrint && git remote set-url origin {}".format(
                env.releasetest_repo
            )
        )


@task
def octopi_releasetestplugin_github_release_patcher():
    """install release patcher"""
    if not files.exists("~/.octoprint/plugins/github_release_patcher.py"):
        put(
            "files/github_release_patcher.py",
            "~/.octoprint/plugins/github_release_patcher.py",
        )


@task
def octopi_install(url):
    """install something inside OctoPrint venv"""
    run('~/oprint/bin/pip install "{}"'.format(url))


@task
def octopi_curl_plugin(url):
    """install a single file plugin from url"""
    if url in env.fixes["plugins"]:
        url = env.fixes["plugins"][url]

    if not files.exists("~/.octoprint/plugins"):
        run("mkdir -p ~/.octoprint/plugins")
    run("cd ~/.octoprint/plugins && curl -L -O '{}'".format(url))


@task
def octopi_tailoctolog():
    """tail octoprint.log"""
    run("tail -f ~/.octoprint/logs/octoprint.log")


@task
def octopi_get_version(target=None):
    if target is None:
        target = env.target

    octopi_version_string = run("cat /etc/octopi_version")
    print("OctoPi version: {}".format(octopi_version_string))
    return octopi_version_string


def octopi_patch_python_env(target=None):
    if target is None:
        target = env.target

    octopi_version_string = octopi_get_version(target=target)
    octopi_version = get_comparable_version(octopi_version_string)

    if octopi_version < get_comparable_version("0.16.0"):
        octopi_install("wrapt==1.12.1")


def octopi_test_releasepatch_octoprint(tag, branch, prerelease):
    # creates & applies release patch
    config = release_patch_octoprint(tag, branch, bool(prerelease))
    octopi_update_config(config)


def octopi_test_releasepatch_filecheck(tag):
    config = release_patch_filecheck(tag)
    octopi_update_config(config)


def octopi_test_releasepatch_firmwarecheck(tag):
    config = release_patch_firmwarecheck(tag)
    octopi_update_config(config)


def octopi_update_config(config):
    # merge config with existing one and write to disk
    fd = BytesIO()
    get(".octoprint/config.yaml", fd)
    fd.seek(0)
    current_config = yaml.safe_load(fd)
    fd.close()

    merged_config = dict_merge(current_config, config)

    fd = StringIO()
    yaml.safe_dump(merged_config, fd)
    fd.seek(0)
    put(fd, ".octoprint/config.yaml")
    fd.close()
    run("cat .octoprint/config.yaml")


@task
def octopi_await_ntp(timeout=300):
    """waits for the server to have ntp synchronized"""
    start = time.monotonic()
    print("Waiting for OctoPi to have its time and date synced from NTP")
    while True:
        if timeout is not None and time.monotonic() > start + timeout:
            abort("Time was not synced after {}s".format(timeout))

        try:
            remote = run('date +"%Y%m%d"').strip()
        except:
            pass
        else:
            local = datetime.date.today().strftime("%Y%m%d")
            if remote == local:
                print("Time has been synced")
                break

        time.sleep(10.0)


@task
def octopi_await_server(timeout=300):
    """waits for the server to come up, with optional timeout"""
    start = time.monotonic()
    print("Waiting for OctoPrint to become responsive at http://{}".format(env.host))
    while True:
        if timeout is not None and time.monotonic() > start + timeout:
            abort("Server wasn't up after {}s".format(timeout))

        try:
            r = requests.get("http://{}/online.txt".format(env.host))
            if r.status_code == 200:
                print("OctoPrint is up at http://{}".format(env.host))
                break
        except:
            pass

        print(".", end="")
        time.sleep(10.0)


@task
def octopi_provision(config, version, release_channel=None, pip=None, packages=None, fixes=None, restart=True):
    """provisions instance: start version, config, release channel, release patcher"""
    octopi_octoservice("stop")
    if version is not None:
        octopi_patch_python_env()
        octopi_install("OctoPrint=={}".format(version))

    if pip is not None:
        octopi_install("pip=={}".format(pip))

    if packages:
        for package in packages.split("|"):
            octopi_install(package)

    if fixes:
        for fix in fixes.split("|"):
            octopi_curl_plugin(fix)

    with codecs.open(
        os.path.join(config, "config.yaml"),
        mode="r",
        encoding="utf-8",
        errors="replace",
    ) as f:
        new_config = yaml.safe_load(f)

    if release_channel is not None:
        if release_channel in ("maintenance", "devel"):
            release_config = dict(
                plugins=dict(
                    softwareupdate=dict(
                        checks=dict(
                            octoprint=dict(
                                prerelease=True,
                                prerelease_channel="rc/{}".format(release_channel),
                            )
                        )
                    )
                )
            )
        else:
            release_config = dict(
                plugins=dict(
                    softwareupdate=dict(
                        checks=dict(
                            octoprint=dict(
                                prerelease=False, prerelease_channel="stable"
                            )
                        )
                    )
                )
            )

        new_config = dict_merge(new_config, release_config)

    octopi_update_config(new_config)
    put(os.path.join(config, "users.yaml"), ".octoprint/users.yaml")

    if files.exists("~/OctoPrint/.git"):
        octopi_releasetestrepo()
    octopi_releasetestplugin_github_release_patcher()

    if restart:
        octopi_octoservice("restart")
        octopi_tailoctolog()


@task
def octopi_wait(target=None):
    if target is None:
        target = env.target

    host_string = env.host_string
    host = env.host
    if target:
        if not target in env.targets:
            abort("Unknown target: {}".format(target))
        host = "{}.lan".format(env.targets[target]["hostname"])
        host_string = "{}@{}".format(env.user, host)

    with settings(host_string=host_string, host=host):
        octopi_await_ntp()
        octopi_await_server()
        webbrowser.open("http://{}".format(env.host))
        octopi_tailoctolog()


@task
def octopi_test_simplepip(tag=None, target=None, pip=None, packages=None, fixes=None):
    """tests simple pip install of tag"""
    if tag is None:
        tag = env.tag

    if tag is None:
        abort("Tag needs to be set")

    if target is None:
        target = env.target

    host_string = env.host_string
    host = env.host
    if target:
        if not target in env.targets:
            abort("Unknown target: {}".format(target))
        host = "{}.lan".format(env.targets[target]["hostname"])
        host_string = "{}@{}".format(env.user, host)

    with settings(host_string=host_string, host=host):
        octopi_await_ntp()
        url = "{}/archive/{}.zip".format(env.releasetest_repo, tag)
        octopi_install(url)
        if pip:
            octopi_install("pip=={}".format(pip))
        if packages:
            for package in packages.split("|"):
                octopi_install(package)
        if fixes:
            for fix in fixes.split("|"):
                octopi_curl_plugin(fix)
        octopi_octoservice("restart")

        octopi_await_server()
        webbrowser.open("http://{}".format(env.host))
        octopi_tailoctolog()


@task
def octopi_test_clean(version=None, target=None, pip=None, packages=None, fixes=None):
    if target is None:
        target = env.target

    host_string = env.host_string
    host = env.host
    if target:
        if not target in env.targets:
            abort("Unknown target: {}".format(target))
        host = "{}.lan".format(env.targets[target]["hostname"])
        host_string = "{}@{}".format(env.user, host)

    with settings(host_string=host_string, host=host):
        octopi_await_ntp()
        if version or pip:
            octopi_octoservice("stop")
            if version:
                octopi_install("OctoPrint=={}".format(version))
            if pip:
                octopi_install("pip=={}".format(pip))
            if packages:
                for package in packages.split("|"):
                    octopi_install(package)
            if fixes:
                for fix in fixes.split("|"):
                    octopi_curl_plugin(fix)
            octopi_octoservice("restart")

        octopi_await_server()
        webbrowser.open("http://{}".format(env.host))
        octopi_tailoctolog()


def octopi_test_update(channel, branch, version=None, tag=None, prerelease=False, config="configs/with_acl", target=None, pip=None, packages=None, fixes=None):
    """
    generic update test prep: wait for server, provision, apply
    release patch, restart, open browser and tail log
    """
    if tag is None:
        tag = env.tag

    if tag is None:
        abort("Tag needs to be set")

    if target is None:
        target = env.target

    host_string = env.host_string
    host = env.host
    if target:
        if not target in env.targets:
            abort("Unknown target: {}".format(target))
        host = "{}.lan".format(env.targets[target]["hostname"])
        host_string = "{}@{}".format(env.user, host)

    with settings(host_string=host_string, host=host):
        octopi_await_ntp()
        octopi_provision(config, version, release_channel=channel, pip=pip, packages=packages, fixes=fixes, restart=False)
        octopi_test_releasepatch_octoprint(tag, branch, prerelease)
        octopi_octoservice("restart")

        octopi_await_server()
        webbrowser.open("http://{}".format(env.host))
        octopi_tailoctolog()


@task
def octopi_test_filecheck(tag, target=None):
    """tests update procedure for filecheck plugin"""
    if target is None:
        target = env.target

    host_string = env.host_string
    host = env.host
    if target:
        if not target in env.targets:
            abort("Unknown target: {}".format(target))
        host = "{}.lan".format(env.targets[target]["hostname"])
        host_string = "{}@{}".format(env.user, host)

    with settings(host_string=host_string, host=host):
        octopi_releasetestplugin_github_release_patcher()
        octopi_test_releasepatch_filecheck(tag)
        octopi_octoservice("restart")

        octopi_await_server()
        webbrowser.open("http://{}".format(env.host))
        octopi_tailoctolog()


@task
def octopi_test_firmwarecheck(tag, target=None):
    """tests update procedure for firmwarecheck plugin"""
    if target is None:
        target = env.target

    host_string = env.host_string
    host = env.host
    if target:
        if not target in env.targets:
            abort("Unknown target: {}".format(target))
        host = "{}.lan".format(env.targets[target]["hostname"])
        host_string = "{}@{}".format(env.user, host)

    with settings(host_string=host_string, host=host):
        octopi_releasetestplugin_github_release_patcher()
        octopi_test_releasepatch_firmwarecheck(tag)
        octopi_octoservice("restart")

        octopi_await_server()
        webbrowser.open("http://{}".format(env.host))
        octopi_tailoctolog()


@task
def octopi_test_update_devel(
    channel, tag=None, version=None, pip=None, packages=None, fixes=None, config="configs/with_acl", target=None
):
    """tests update procedure for devel RCs"""
    octopi_test_update(channel, "rc/devel", version=version, tag=tag, prerelease=True, config=config, target=target, pip=pip, packages=packages, fixes=fixes)


@task
def octopi_test_update_maintenance(
    channel, tag=None, version=None, pip=None, packages=None, fixes=None, config="configs/with_acl", target=None
):
    """tests update procedure for maintenance RCs"""
    octopi_test_update(channel, "rc/maintenance", version=version, tag=tag, prerelease=True, config=config, target=target, pip=pip, packages=packages, fixes=fixes)


@task
def octopi_test_update_stable(
    channel, tag=None, version=None, pip=None, packages=None, fixes=None, config="configs/with_acl", target=None
):
    """tests update procedure for stable releases"""
    octopi_test_update(channel, "master", version=version, tag=tag, prerelease=False, config=config, target=target, pip=pip, packages=packages, fixes=fixes)
