# Testrig

Testrig with up to three test Pis (aka DUTs, supported versions are 2, 3 or 4) and one Pi4 as controller/host.

![](testrig.jpg)

## BOM

### Lasercut parts

All to be cut out off 3mm thick Plywood. A3 size should suffice.

  * bottom-plate-3dut.svg
  * power-mount.svg
  * tray-controller.svg
  * 1 x tray-pi-and-sdmux.svg per DUT
  * optional: tray-fan.svg

### 3D printed parts

  * 1 x standoff-sdmux.stl per DUT

### Electronics

  * [Yepkit YKUSH](https://www.yepkit.com/products/ykush)
  * 1 x [USB-SD-MUX](https://shop.linux-automation.com/usb_sd_mux-D02-R01-V02-C00-en) per DUT
  * 5.5x2.5mm female power connector
  * 5V/8A power supply with 5.5x2.5mm male connector
  * USB C power supply 5.1V/3A
  * 1 x RPi 2/3/4 as DUT
  * RPi4 4GB as controller/host
  * passive heatsink for RPi4
  * optional: Noctua 40x10mm 5V fan for RPi4

### Cables

  * 2 x USB A to MicroUSB, 30cm per DUT
  * USB A to MiniUSB, 30cm

### Other

  * 12 x M2.5x6mm standoff
  * 4 x M3x6mm standoff
  * 4 x M3x20mm standoff
    * 8 x M3x20mm if cooling fan for Pi4 is to be mounted
  * various M2.5 and M3 nuts and bolts
