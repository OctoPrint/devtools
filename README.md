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

    fab flashhost_flash_and_provision:pi3,0.17.0

### Test update for maintenance RC

Release channel maintenance, start version 1.4.1rc2, fake release 1.4.1rc3

    fab -H pi@octopi3.lan octopi_test_update_maintenance:maintenance,1.4.1rc3,version=1.4.1rc2

### Combined

    fab -H pi@octopi3.lan flashhost_flash_and_provision:pi3,0.17.0 octopi_test_update_maintenance:maintenance,1.4.1rc3,version=1.4.1rc2

## Testrig

Testrig files available in `./testrig`.
