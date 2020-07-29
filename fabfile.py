from __future__ import print_function, unicode_literals, absolute_import

from fabric.api import local, lcd, run, sudo, cd, prompt, get, put, hosts, settings
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

def sync_test_repo(force=False):
	# sync local checkout with testrepo
	with lcd(env.octoprint):
		for branch in ("master", "maintenance", "staging/maintenance", "rc/maintenance", "devel", "rc/devel"):
			local("git checkout {}".format(branch))
			if force:
				local("git push --force releasetest {}".format(branch))
			else:
				local("git push releasetest {}".format(branch))

def test_rc_devel(tag, force=False):
	# prep devel rc on testrepo
	if tag.endswith("rc1"):
		merge_tag_push_test_repo("rc/devel", "devel", tag, force=force)
	else:
		merge_tag_push_test_repo("rc/devel", "staging/devel", tag, force=force)

def test_rc_maintenance(tag, force=False):
	# prep maintenance rc on testrepo
	if tag.endswith("rc1"):
		merge_tag_push_test_repo("rc/maintenance", "maintenance", tag, force=force)
	else:
		merge_tag_push_test_repo("rc/maintenance", "staging/maintenance", tag, force=force)

def test_stable(tag, force=False):
	# prep stable release on testrepo
	test_rc_maintenance(tag, force=force)
	merge_push_test_repo("master", "rc/maintenance")
	merge_push_test_repo("rc/devel", "rc/maintenance")

def tag_push_test_repo(push_branch, tag, force=False):
	# push src and tags to test repo
	with lcd(env.octoprint):
		local("git checkout {}".format(push_branch))

		if force:
			local("git tag -d {}".format(tag))
		local("git tag {}".format(tag))

		local("git push --tags releasetest {}".format(tag))

def merge_tag_push_test_repo(push_branch, merge_branch, tag, force=False):
	# merge, tag and push to testrepo
	with lcd(env.octoprint):
		local("git checkout {}".format(push_branch))
		local("git merge {}".format(merge_branch))

		if force:
			local("git tag -d {}".format(tag))
		local("git tag {}".format(tag))

		local("git push --tags releasetest {}".format(tag))

def merge_push_test_repo(push_branch, merge_branch):
	# merge and push to testrepo
	with lcd(env.octoprint):
		local("git checkout {}".format(push_branch))

		local("git merge {}".format(merge_branch))

		local("git push releasetest {}".format(push_branch))

##~~ Local install testing ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def test_install(tag, python, target="wheel"):
	# test local install of tag against python version and wheel/sdist
	basedir = "testconf-dist"
	venv = "venv-dist"

	with lcd(env.octoprint):
		if not os.path.exists("dist\\OctoPrint-{}.tar.gz".format(tag)):
			local("{} setup.py sdist bdist_wheel".format(sys.executable))
		
		local("rm -rf {} || true".format(venv))
		local("rm -rf {} || true".format(basedir))

		local("{} -m virtualenv --python={} {}".format(env.python37, getattr(env, python), venv))
		if target == "wheel":
			local("{}\\Scripts\\python.exe -m pip install dist/OctoPrint-{}-py2.py3-none-any.whl".format(venv, tag))
		elif target == "sdist":
			local("{}\\Scripts\\python.exe -m pip install dist/OctoPrint-{}.tar.gz".format(venv, tag))

		local("{}\\Scripts\\octoprint.exe serve --debug --basedir {} --port 5001".format(venv, basedir))

def test_sdist(tag, python):
	# test sdist install of tag against python version
	test_install(tag, python, target="sdist")

def test_wheel(tag, python):
	# test wheel install of tag against python version
	test_install(tag, python, target="wheel")

##~~ FlashHost ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def format_serial(serial):
	return "0" * (12 - len(serial)) + serial

def disk_device(serial):
	return "/dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_{}-0:0".format(format_serial(serial))

def boot_part_device(serial):
	return "/dev/disk/by-id/usb-LinuxAut_sdmux_HS-SD_MMC_{}-0:0-part1".format(format_serial(serial))

@hosts('pi@flashhost.lan')
def flashhost_flash(version, target=None):
	# flashes target with OctoPi image of provided version using dd
	imagefile = "{}/octopi-{}.img".format(env.flashhost["images"], version)

	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	if not files.exists(imagefile):
		abort("Image not available: {}".format(imagefile))
	serial = env.targets[target]["serial"]
	targetdev = disk_device(serial)

	sudo("dd bs=4M if={} of={} status=progress conv=fsync".format(imagefile, targetdev))

@hosts('pi@flashhost.lan')
def flashhost_provision(target=None):
	# provisions target with wifi, hostname and password
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	serial = env.targets[target]["serial"]
	hostname = env.targets[target]["hostname"]
	password = env.password

	boot = boot_part_device(serial)
	mount = "{}/{}".format(env.flashhost["mounts"], target)

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

@hosts('pi@flashhost.lan')
def flashhost_host(target=None):
	# switches target to Host mode (powered off & USB-SD-MUX Host)
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	usbport = env.targets[target]["usbport"]
	serial = env.targets[target]["serial"]
	
	sudo("{} -d {}".format(env.flashhost["ykush"], usbport))
	sudo("{} /dev/usb-sd-mux/id-{} host".format(env.flashhost["usbsdmux"], format_serial(serial)))

@hosts('pi@flashhost.lan')
def flashhost_dut(target=None):
	# switches target to DUT mode (USB-SD-MUX DUT & powered on)
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	usbport = env.targets[target]["usbport"]
	serial = env.targets[target]["serial"]
	
	sudo("{} /dev/usb-sd-mux/id-{} dut".format(env.flashhost["usbsdmux"], format_serial(serial)))
	sudo("{} -u {}".format(env.flashhost["ykush"], usbport))

@hosts('pi@flashhost.lan')
def flashhost_reboot(target=None):
	# powers target off and on again
	if target is None:
		target = env.target
	if not target in env.targets:
		abort("Unknown target: {}".format(target))
	usbport = env.targets[target]["usbport"]
	
	sudo("{} -d {}".format(env.flashhost["ykush"], usbport))
	time.sleep(1.0)
	sudo("{} -u {}".format(env.flashhost["ykush"], usbport))

@hosts('pi@flashhost')
def flashhost_flash_and_provision(version, target=None):
	# runs flash & provision cycle on target for specified OctoPi version
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

def release_patch(tag, branch, prerelease):
	# generate release patch
	now = datetime.datetime.utcnow().replace(microsecond=0).isoformat(' ')

	tag_name = "{} (release candidate)" if prerelease else "{} (stable)"
	tag_name = tag_name.format(tag)

	release = dict(draft=False,
				   html_url="https://github.com/OctoPrint/OctoPrint/releases/tag/{}".format(tag),
				   name=tag_name,
				   prerelease=prerelease,
				   published_at=now,
				   tag_name=tag,
				   target_commitish=branch)

	config = dict(plugins=dict(github_release_patcher=dict(releases=dict()),
	                           softwareupdate=dict(checks=dict(octoprint=dict(pip="{}/archive/{{target_version}}.zip".format(env.releasetest_repo))))))
	config["plugins"]["github_release_patcher"]["releases"]["OctoPrint/OctoPrint"] = [release,]
	config["plugins"]["github_release_patcher"]["releases"]["foosel/OctoPrint"] = [release,]

	return config

def octopi_octoservice(command):
	# run service command
	sudo("service octoprint {}".format(command))

def octopi_standardrepo():
	# set standard repo
	run("cd ~/OctoPrint && git remote set-url origin https://github.com/OctoPrint/OctoPrint")

def octopi_releasetestrepo():
	# set releasetest repo
	run("cd ~/OctoPrint && git remote set-url origin {}".format(env.releasetest_repo))

def octopi_releasetestplugin_github_release_patcher():
	# install release patcher
	run("cd ~/.octoprint/plugins && wget -Ogithub_release_patcher.py https://gist.githubusercontent.com/foosel/1e6e9c97acb7c2f36d4510ba69097c4d/raw/32e251e407336b1cd81a9d3942e739f354b2e037/github_release_patcher.py")

def octopi_checkout(branch, committish=None):
	# git checkout specified branch and committish
	if not files.exists("~/OctoPrint/.git"):
		abort("No git checkout available")

	with cd("~/OctoPrint"):
		run("git fetch")
		run("git checkout {}".format(branch))
		run("git pull")
		if committish is not None:
			run("git reset --hard {}".format(committish))
		run("~/oprint/bin/python setup.py clean && ~/oprint/bin/pip install .")
	octopi_octoservice("restart")

def octopi_install(url):
	# install something inside OctoPrint venv
	run("~/oprint/bin/pip install {}".format(url))

def octopi_tailoctolog():
	# tail octoprint.log
	run("tail -f ~/.octoprint/logs/octoprint.log")

def octopi_test_releasepatch(tag, branch, prerelease):
	# creates & applies release patch
	config = release_patch(tag, branch, bool(prerelease))
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

def octopi_await_server(timeout=None):
	# waits for the server to come up, with optional timeout
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

def octopi_provision(config, version, release_channel=None, restart=True):
	# provisions instance: start version, config, release channel, release patcher
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

def octopi_test_simplepip(tag=None, target=None):
	# tests simple pip install of tag
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
		octopi_await_server()
		url = "{}/archive/{}.zip".format(env.releasetest_repo, tag)
		octopi_install(url)
		octopi_octoservice("restart")

		octopi_await_server()
		webbrowser.open("http://{}".format(env.host))
		octopi_tailoctolog()

def octopi_test_update(version, channel, tag, branch, prerelease, config, target):
	# generic update test prep: wait for server, provision, apply
	# release patch, restart, open browser and tail log
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
		octopi_await_server()
		octopi_provision(config, version, release_channel=channel, restart=False)
		octopi_test_releasepatch(tag, branch, prerelease)
		octopi_octoservice("restart")

		octopi_await_server()
		webbrowser.open("http://{}".format(env.host))
		octopi_tailoctolog()

def octopi_test_update_devel(channel, tag=None, version=None, config="configs/with_acl", target=None):
	# tests update procedure for devel RCs
	octopi_test_update(version, channel, tag, "rc/devel", True, config, target)

def octopi_test_update_maintenance(channel, tag=None, version=None, config="configs/with_acl", target=None):
	# tests update procedure for maintenance RCs
	octopi_test_update(version, channel, tag, "rc/maintenance", True, config, target)

def octopi_test_update_stable(channel, tag=None, version=None, config="configs/with_acl", target=None):
	# tests update procedure for stable releases
	octopi_test_update(version, channel, tag, "master", False, config, target)
