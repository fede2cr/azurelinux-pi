# azurelinux-pi
Azurelinux for the raspberry pi

## Description

This project merges the userspace from AzureLinux with the kernel from Raspbian to create a funcional AzureLinux for Raspberry Pi image.

## TODO

(these lines will be removed as items get done)
- CI/CD using local actions to build and publish image
- wifi
- regular user instead of root
- raspberry tools and kernel modules (/usr/lib, /lib/modules)
- test if personalizations from Pi Imager, work magically

## Not in scope

The following list is not an objective for the project, at least at this point

- Local kernel build: This is quite easy to do, but not important for now
- Firmware package
- Build scripts in the style of azurelinux, so that the distro can create images automatically. It is ok that this is not an official build, but a hack to combine RaspiOS with AzureLinux.