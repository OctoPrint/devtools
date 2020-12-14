from __future__ import print_function, unicode_literals, absolute_import

from fabric.api import local, lcd, run, sudo, cd, prompt, get, put, hosts, settings, task
from fabric.utils import abort
from fabric.state import env
from fabric.contrib import files

import datetime
import calendar
import sys
import os
import codecs
import yaml
import time
import requests
import webbrowser
import datetime

from io import StringIO, BytesIO

def env_from_yaml(path):
	import yaml

	with codecs.open(path, errors="replace") as f:
		data = yaml.safe_load(f)

	if not isinstance(data, dict):
		abort("YAML file at {} doesn't contain a dictionary, can't use that for setting env")

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

##~~ Release testing ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@task
def sync_test_repo(force=False):
	"""sync local checkout with testrepo"""
	with lcd(env.octoprint):
		for branch in ("master", "maintenance", "staging/maintenance", "rc/maintenance", "devel", "rc/devel"):
			local("git checkout {}".format(branch))
			if force:
				local("git push --force releasetest {}".format(branch))
			else:
				local("git push releasetest {}".format(branch))

@task
def merge_and_push(branch="master", force=False):
	with lcd(env.octoprint):
		for pushbranch in ("rc/maintenance", "rc/devel", "staging/maintenance", "staging/devel"):
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
	test_branch("rc/maintenance", "staging/maintenance", "maintenance", tag=tag, force=force)

@task
def test_stable(tag=None, force=False):
	"""prep stable release on testrepo"""
	test_rc_maintenance(tag=tag, force=force)
	merge_push_test_repo("master", "rc/maintenance")
	merge_push_test_repo("rc/devel", "rc/maintenance")

@task
def test_hotfix(tag=None, force=False):
	"""prep hotfix release on testrepo"""
	if tag is None:
		tag = env.tag

	if tag is None:
		abort("Tag needs to be set")

	merge_tag_push_test_repo("master", "staging/hotfix", tag, force=force)

def merge_tag_push_test_repo(push_branch, merge_branch, tag=None, force=False):
	# merge, tag and push to testrepo
	if tag is None:
		tag = env.tag

	if tag is None:
		abort("Tag needs to be set")

	with lcd(env.octoprint):
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

		local("{} -m virtualenv --python={} {}".format(env.python37, getattr(env, python), venv))
		if target == "wheel":
			local("{} -m pip install dist/OctoPrint-{}-py2.py3-none-any.whl".format(venv_executable(venv, "python"), tag))
		elif target == "sdist":
			local("{} -m pip install dist/OctoPrint-{}.tar.gz".format(venv_executable(venv, "python"), tag))

		local("{} serve --debug --basedir {} --port 5001".format(venv_executable(venv, "octoprint"), basedir))

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
	return "/dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_{}-0:0".format(format_serial(serial))

def boot_part_device(serial):
	return "/dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_{}-0:0-part1".format(format_serial(serial))

@task
@hosts('pi@flashhost.lan')
def flashhost_release_lock():
	"""release flash lock if left set for some reason"""
	lock = env.flashhost["flashlock"]
	sudo("rm -rf {}".format(lock))

@task
@hosts('pi@flashhost.lan')
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

	sudo("flock -w300 {} dd bs=4M if={} of={} status=progress conv=fsync".format(lockfile, imagefile, targetdev))

@task
@hosts('pi@flashhost.lan')
def flashhost_provision(target=None):
	"""provisions target with wifi, hostname and password"""
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	serial = env.targets[target]["serial"]
	hostname = env.targets[target]["hostname"]
	password = env.password

	boot = boot_part_device(serial)
	mount = "{}/{}".format(env.flashhost["mounts"], target)

	if not files.exists(mount):
		run("mkdir -p {}".format(mount))

	if not files.exists(mount + "/cmdline.txt"):
		sudo("mount {} {}".format(boot, mount))
	files.upload_template("octopi-wpa-supplicant.txt", 
	                      mount + "/octopi-wpa-supplicant.txt", 
	                      context=dict(ssid=env.wifi_ssid, psk=env.wifi_psk), 
	                      use_jinja=True, 
	                      template_dir="templates", 
	                      backup=False,
	                      keep_trailing_newline=True,
	                      use_sudo=True)
	files.upload_template("octopi-network.txt", 
	                      mount + "/octopi-network.txt", 
	                      context=dict(ssid=env.wifi_ssid, psk=env.wifi_psk), 
	                      use_jinja=True, 
	                      template_dir="templates", 
	                      backup=False,
	                      keep_trailing_newline=True,
	                      use_sudo=True)
	files.upload_template("octopi-hostname.txt", 
	                      mount + "/octopi-hostname.txt", 
	                      context=dict(hostname=hostname), 
	                      use_jinja=True, 
	                      template_dir="templates", 
	                      backup=False,
	                      keep_trailing_newline=True,
	                      use_sudo=True)
	files.upload_template("octopi-password.txt", 
	                      mount + "/octopi-password.txt", 
	                      context=dict(password=password), 
	                      use_jinja=True, 
	                      template_dir="templates", 
	                      backup=False,
	                      keep_trailing_newline=True,
	                      use_sudo=True)
	sudo("umount {}".format(mount))

@task
@hosts('pi@flashhost.lan')
def flashhost_host(target=None):
	"""switches target to Host mode (powered off & USB-SD-MUX Host)"""
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	usbport = env.targets[target]["usbport"]
	serial = env.targets[target]["serial"]
	
	sudo("{} -d {}".format(env.flashhost["ykush"], usbport))
	sudo("{} /dev/usb-sd-mux/id-{} host".format(env.flashhost["usbsdmux"], format_serial(serial)))

@task
@hosts('pi@flashhost.lan')
def flashhost_dut(target=None):
	"""switches target to DUT mode (USB-SD-MUX DUT & powered on)"""
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	usbport = env.targets[target]["usbport"]
	serial = env.targets[target]["serial"]
	
	sudo("{} /dev/usb-sd-mux/id-{} dut".format(env.flashhost["usbsdmux"], format_serial(serial)))
	sudo("{} -u {}".format(env.flashhost["ykush"], usbport))

@task
@hosts('pi@flashhost.lan')
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

@task
@hosts('pi@flashhost')
def flashhost_flash_and_provision(version, target=None):
	"""runs flash & provision cycle on target for specified OctoPi version"""
	if target is None:
		target = env.target
	flashhost_host(target=target)
	flashhost_flash(version, target=target)
	print("Flashing done, giving the system a bit to recover...")
	time.sleep(5.0)
	print("... done")
	flashhost_provision(target=target)
	flashhost_dut(target=target)

##~~ OctoPi ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def release_patch(key, tag, repo, additional_repos=None, branch="master", prerelease=False, pip=None):
	# generate release patch
	now = datetime.datetime.utcnow().replace(microsecond=0).isoformat(' ')

	tag_name = "{} (release candidate)" if prerelease else "{} (stable)"
	tag_name = tag_name.format(tag)

	if additional_repos is None:
		additional_repos = []

	checks = dict()
	if pip is not None:
		checks[key] = dict(pip=pip)

	release = dict(draft=False,
					html_url="https://github.com/{}/releases/tag/{}".format(repo, tag),
					name=tag_name,
					prerelease=prerelease,
					published_at=now,
					tag_name=tag,
					target_commitish=branch)
	
	releases = dict()
	releases[repo] = [release,]
	for repo in additional_repos:
		releases[repo] = [release,]

	config = dict(plugins=dict(github_release_patcher=dict(releases=releases),
	                           softwareupdate=dict(checks=checks)))

	return config

def release_patch_octoprint(tag, branch, prerelease):
	return release_patch("octoprint", tag, "OctoPrint/OctoPrint", 
	                     additional_repos=["foosel/OctoPrint",], 
	                     branch=branch, 
	                     prerelease=prerelease, 
	                     pip="{}/archive/{{target_version}}.zip".format(env.releasetest_repo))

def release_patch_filecheck(tag, branch="master"):
	return release_patch("file_check", tag, "OctoPrint/OctoPrint-FileCheck",
	                     branch=branch,
	                     pip="https://github.com/OctoPrint/OctoPrint-FileCheck/archive/{}.zip".format(branch))

def release_patch_firmwarecheck(tag, branch="master"):
	return release_patch("firmware_check", tag, "OctoPrint/OctoPrint-FirmwareCheck",
	                     branch=branch,
	                     pip="https://github.com/OctoPrint/OctoPrint-FirmwareCheck/archive/{}.zip".format(branch))

@task
def octopi_octoservice(command):
	"""run service command"""
	sudo("service octoprint {}".format(command))

def octopi_standardrepo():
	"""set standard repo"""
	if files.exists("~/OctoPrint/.git"):
		run("cd ~/OctoPrint && git remote set-url origin https://github.com/OctoPrint/OctoPrint")

def octopi_releasetestrepo():
	"""set releasetest repo"""
	if files.exists("~/OctoPrint/.git"):
		run("cd ~/OctoPrint && git remote set-url origin {}".format(env.releasetest_repo))

@task
def octopi_releasetestplugin_github_release_patcher():
	"""install release patcher"""
	if not files.exists("~/.octoprint/plugins/github_release_patcher.py"):
		put("files/github_release_patcher.py", "~/.octoprint/plugins/github_release_patcher.py")

@task
def octopi_install(url):
	"""install something inside OctoPrint venv"""
	run("~/oprint/bin/pip install {}".format(url))

@task
def octopi_tailoctolog():
	"""tail octoprint.log"""
	run("tail -f ~/.octoprint/logs/octoprint.log")

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
			remote = run("date +\"%Y%m%d\"").strip()
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

		print(".", end='')
		time.sleep(10.0)

@task
def octopi_provision(config, version, release_channel=None, restart=True):
	"""provisions instance: start version, config, release channel, release patcher"""
	octopi_octoservice("stop")
	if version is not None:
		octopi_install("OctoPrint=={}".format(version))

	with codecs.open(os.path.join(config, "config.yaml"), mode="r", encoding="utf-8", errors="replace") as f:
		new_config = yaml.safe_load(f)

	if release_channel is not None:
		if release_channel in ("maintenance", "devel"):
			release_config = dict(plugins=dict(softwareupdate=dict(checks=dict(octoprint=dict(prerelease=True,
			                                                                                  prerelease_channel="rc/{}".format(release_channel))))))
		else:
			release_config = dict(plugins=dict(softwareupdate=dict(checks=dict(octoprint=dict(prerelease=False,
			                                                                                  prerelease_channel="stable")))))

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
def octopi_test_simplepip(tag=None, target=None):
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
		octopi_octoservice("restart")

		octopi_await_server()
		webbrowser.open("http://{}".format(env.host))
		octopi_tailoctolog()

@task
def octopi_test_clean(version, target=None):
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
		octopi_octoservice("stop")
		if version is not None:
			octopi_install("OctoPrint=={}".format(version))
		octopi_octoservice("restart")

		octopi_await_server()
		webbrowser.open("http://{}".format(env.host))
		octopi_tailoctolog()

def octopi_test_update(version, channel, tag, branch, prerelease, config, target):
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
		octopi_provision(config, version, release_channel=channel, restart=False)
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
def octopi_test_update_devel(channel, tag=None, version=None, config="configs/with_acl", target=None):
	"""tests update procedure for devel RCs"""
	octopi_test_update(version, channel, tag, "rc/devel", True, config, target)

@task
def octopi_test_update_maintenance(channel, tag=None, version=None, config="configs/with_acl", target=None):
	"""tests update procedure for maintenance RCs"""
	octopi_test_update(version, channel, tag, "rc/maintenance", True, config, target)

@task
def octopi_test_update_stable(channel, tag=None, version=None, config="configs/with_acl", target=None):
	"""tests update procedure for stable releases"""
	octopi_test_update(version, channel, tag, "master", False, config, target)
