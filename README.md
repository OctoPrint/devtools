# 👷‍♀️ OctoPrint devtools

Various development & release tools for OctoPrint, powered by [Fabric](https://docs.fabfile.org/en/1.14/).

Provided as-is for documentationational purposes.

## Usage examples

It is recommended to create terminals for each DUT, and set `TARGET` (= DUT identifier) and `TAG` (= future release to be tested) in them correspondingly via `export`, e.g.

    export TAG=1.4.1rc3
    export TARGET=pi3

### Pre-release RC on test repo (test prep)

    fab sync_test_repo test_rc:1.4.1rc3

or (with `TAG` set)

    fab sync_test_repo test_rc

### Local test install

    fab test_wheel:python3.7,1.4.1rc3

or (with `TAG` set)

    fab test_wheel:python3.7

### Flash & provision one of the test pis

Target pi3, OctoPi 0.17.0

    fab flashhost_flash_and_provision:0.17.0,pi3

or (with `TARGET` set)

    fab flashhost_flash_and_provision:0.17.0

### Test update for RC

Target pi3, release channel `next`, start version 1.4.1rc2, fake release 1.4.1rc3

    fab --set target=pi3 octopi_test_update_rc:next,1.4.1rc3,version=1.4.1rc2

or (with `TARGET` and `TAG` set)

    fab octopi_test_update_rc:next,version=1.4.1rc2

### Combined

Target pi3, OctoPi 0.17.0, release channel `next`, start version 1.4.1rc2, fake release 1.4.1rc3 (`TARGET`
and `TAG` set)

    fab flashhost_flash_and_provision:0.17.0 octopi_test_update_rc:next,version=1.4.1rc2

### Full example

One DUT (`pi3`), target 1.4.1rc4. Release on release test repo, check local sdist/wheel installation,
then run a release test matrix against OctoPi 0.15.0, 0.15.1, 0.16.0, 0.17.0 and various release channel and
start version combinations.

    export TARGET=pi3
    export TAG=1.4.1rc4
    fab sync_test_repo
    fab test_next
    fab test_sdist:python27
    fab test_wheel:python37
    fab flashhost_flash_and_provision:0.15.0 octopi_test_update_rc:stable,version=1.4.0
    fab flashhost_flash_and_provision:0.15.1 octopi_test_simplepip
    fab flashhost_flash_and_provision:0.15.1 octopi_test_update_rc:next,version=1.4.1rc3
    fab flashhost_flash_and_provision:0.16.0 octopi_test_update_rc:next
    fab flashhost_flash_and_provision:0.17.0 octopi_test_update_rc:next
    fab flashhost_flash_and_provision:0.17.0 octopi_test_update_rc:next,version=1.4.1rc3
    fab flashhost_flash_and_provision:0.17.0 octopi_test_update_rc:devel

## Testrig

Testrig files available in `./testrig`.

## License

MIT
