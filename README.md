# azurelinux-pi
Azurelinux for the raspberry pi

## Description

This project merges the userspace from AzureLinux with the kernel from Raspbian to create a funcional AzureLinux for Raspberry Pi image.

## TODO

(these lines will be removed as items get done)
- CI/CD using local actions to build and publish image
- wifi
- regular user instead of root
- test if personalizations from Pi Imager, work magically
- having issues with /boot/firmware mounting properly

## Not in scope

The following list is not an objective for the project, at least at this point

- Local kernel build: This is quite easy to do, but not important for now
- Firmware package
- Build scripts in the style of azurelinux, so that the distro can create images automatically. It is ok that this is not an official build, but a hack to combine RaspiOS with AzureLinux.

## Project notes

This project has been almost entirely coded with VisualCode and the Copilot GPT-4.1 plugin, by asking the chat window to do tasks one by one as I would have done them by hand to create the image, very carefully checking the proposals and sometimes requesting completely different prompts to get code similar to what I would have programmed the old timer way. Some of the initial code was by using an ISO image, and there is still lots of cleanup to do.