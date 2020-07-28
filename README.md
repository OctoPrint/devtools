# 👷‍♀️ OctoPrint devtools

Various development & release tools for OctoPrint, powered by [Fabric](https://docs.fabfile.org/en/1.14/).

Provided as-is for documentationational purposes.

## Usage examples

### Pre-release maintenance RC on test repo (test prep)

    fab sync_test_repo test_rc_maintenance:1.4.1rc3

### Local test install

    fab test_wheel:1.4.1rc3,python3.7

### Flash & provision one of the test pis

Target pi3, OctoPi 0.17.0

    fab flashhost_flash_and_provision:0.17.0,pi3

or

    fab --set target=pi3 flashhost_flash_and_provision:0.17.0

### Test update for maintenance RC

Target pi3, release channel maintenance, start version 1.4.1rc2, fake release 1.4.1rc3

    fab --set target=pi3 octopi_test_update_maintenance:maintenance,1.4.1rc3,version=1.4.1rc2

### Combined

Target pi3, OctoPi 0.17.0, release channel maintenance, start version 1.4.1rc2, fake release 1.4.1rc3

    fab --set target=pi3 flashhost_flash_and_provision:0.17.0 octopi_test_update_maintenance:maintenance,1.4.1rc3,version=1.4.1rc2

## Testrig

Testrig files available in `./testrig`.
