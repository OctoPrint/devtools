#!/bin/bash

set +e

CURRENT_HOSTNAME=`cat /etc/hostname | tr -d " \t\n\r"`
if [ -f /usr/lib/raspberrypi-sys-mods/imager_custom ]; then
   /usr/lib/raspberrypi-sys-mods/imager_custom set_hostname {{ hostname }}
else
   echo {{ hostname }} >/etc/hostname
   sed -i "s/127.0.1.1.*$CURRENT_HOSTNAME/127.0.1.1\t{{ hostname }}/g" /etc/hosts
fi

FIRSTUSER=`getent passwd 1000 | cut -d: -f1`
FIRSTUSERHOME=`getent passwd 1000 | cut -d: -f6`
if [ -f /usr/lib/userconf-pi/userconf ]; then
   /usr/lib/userconf-pi/userconf '{{ user }}' '{{ passwordhash }}'
else
   echo "$FIRSTUSER:"'{{ passwordhash }}' | chpasswd -e
   if [ "$FIRSTUSER" != "{{ user }}" ]; then
      usermod -l "{{ user }}" "$FIRSTUSER"
      usermod -m -d "/home/{{ user }}" "{{ user }}"
      groupmod -n "{{ user }}" "$FIRSTUSER"
      if grep -q "^autologin-user=" /etc/lightdm/lightdm.conf ; then
         sed /etc/lightdm/lightdm.conf -i -e "s/^autologin-user=.*/autologin-user={{ user }}/"
      fi
      if [ -f /etc/systemd/system/getty@tty1.service.d/autologin.conf ]; then
         sed /etc/systemd/system/getty@tty1.service.d/autologin.conf -i -e "s/$FIRSTUSER/{{ user }}/"
      fi
      if [ -f /etc/sudoers.d/010_pi-nopasswd ]; then
         sed -i "s/^$FIRSTUSER /{{ user }} /" /etc/sudoers.d/010_pi-nopasswd
      fi
   fi
fi

if [ -f /usr/lib/raspberrypi-sys-mods/imager_custom ]; then
   /usr/lib/raspberrypi-sys-mods/imager_custom set_wlan '{{ ssid }}' '{{ psk }}' '{{ country }}'
else
   cat >/etc/wpa_supplicant/wpa_supplicant.conf <<'WPAEOF'
country={{ country }}
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
ap_scan=1

update_config=1
network={
	ssid="{{ ssid }}"
	psk={{ psk }}
}

WPAEOF
   chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
   rfkill unblock wifi
   for filename in /var/lib/systemd/rfkill/*:wlan ; do
      echo 0 > $filename
   done
fi

rm -f /boot/firstrun.sh
sed -i 's| systemd.run.*||g' /boot/cmdline.txt
exit 0
