'''
This script downloads an Azurelinux aarch64 ISO image, extracts it.
Then it downloads a Raspberry Pi 4 firmware and kernel,
and combines them into an SD bootable image for Raspberry Pi 4.
It uses `genisoimage` to create the ISO and `shutil` for file operations.
It requires root privileges to mount the ISO file.
'''
import os
import subprocess
import sys
import urllib.request
import shutil
import tempfile
import time
import random
from passlib.hash import sha512_crypt

def download_file(url, dest):
    print(f"Downloading {url} to {dest}...")
    if not os.path.exists(dest):
        urllib.request.urlretrieve(url, dest)
        print("Download complete.")
    else:
        print(f"{dest} already exists, skipping download.")

def combine_images(raspbian, azurelinux):
    '''
    Uses the raspbian image as a base and combines it with the Azurelinux files,
    keeping the raspbian kernel and firmware while replacing the root filesystem with Azurelinux.
    Before copying, chroot into the Azurelinux root, run tdnf update and tdnf install systemd.
    :param raspbian: Path to the Raspberry Pi SD image.
    :param azurelinux: Path to the directory containing the extracted Azurelinux files.
    :return: None
    '''
    # Bind mount /dev, /proc, /sys for chroot environment
    for fs in ['dev', 'proc', 'sys']:
        target = os.path.join(azurelinux, fs)
        os.makedirs(target, exist_ok=True)
        subprocess.run(['sudo', 'mount', '--bind', f'/{fs}', target], check=True)

    # Copy resolv.conf for network access in chroot
    resolv_src = '/etc/resolv.conf'
    resolv_dst = os.path.join(azurelinux, 'etc', 'resolv.conf')
    subprocess.run(['sudo', 'cp', resolv_src, resolv_dst], check=True)
    # Create a minimal fstab for root as rw
    fstab_path = os.path.join(azurelinux, 'etc', 'fstab')
    with open(fstab_path, 'w') as fstab:
        fstab.write("proc /proc proc defaults 0 0\n/dev/mmcblk0p2 / ext4 defaults,rw 0 1\n/dev/mmcblk0p1 /boot/firmware vfat defaults,rw,nofail 0 1\n")
    # Create a minimal hostname file
    hostname_path = os.path.join(azurelinux, 'etc', 'hostname')
    with open(hostname_path, 'w') as hostname_file:
        hostname_file.write("azurelinux\n")

    try:
        # Run tdnf update and install systemd inside chroot
        subprocess.run(['sudo', 'chroot', azurelinux, 'tdnf', '-y', 'update'], check=True)
        subprocess.run(['sudo', 'chroot', azurelinux, 'tdnf', '-y', 'install',
                        'systemd', 'shadow-utils', 'openssh', 'iproute',
                        'sudo', 'procps-ng', 'less', 'vim', 'vim-extra',
                        'man-pages', 'man-db', 'which', 'wpa_supplicant',
                        'file', 'bash-completion', 'chrony', 'dhcpcd'], check=True)
        
        password_salt = random.getrandbits(64).to_bytes(8, 'big').hex()
        password_hash = sha512_crypt.using(salt=password_salt, rounds=5000).hash('azl')
        subprocess.run(['sudo', 'chroot', azurelinux, 'usermod', '-p', password_hash, 'root'], check=True)
    finally:
        # Remove resolv.conf from chroot
        subprocess.run(['sudo', 'rm', '-f', resolv_dst], check=True)
        # Unmount bind mounts
        for fs in ['dev', 'proc', 'sys']:
            target = os.path.join(azurelinux, fs)
            subprocess.run(['sudo', 'umount', target], check=True)

    loop_device = subprocess.check_output(
        ['sudo', 'losetup', '--find', '--show', '-P', raspbian],
        text=True
    ).strip()

    # Run dosfsck on partition 1 (boot, vfat)
    subprocess.run(['sudo', 'dosfsck', '-a', f'{loop_device}p1'], check=True)
    # Run fsck on partition 2 (root, ext4)
    subprocess.run(['sudo', 'fsck.ext4', '-y', f'{loop_device}p2'], check=True)

    boot_mount = tempfile.mkdtemp(prefix="mnt_boot_")
    root_mount = tempfile.mkdtemp(prefix="mnt_root_")

    try:
        subprocess.run(['sudo', 'mount', f'{loop_device}p1', boot_mount], check=True)
        subprocess.run(['sudo', 'mount', f'{loop_device}p2', root_mount], check=True)

        #modules_backup = os.path.join(root_mount, 'modules_backup')
        #modules_dir = os.path.join(root_mount, 'lib', 'modules')
        #if os.path.exists(modules_dir):
        #    subprocess.run(['sudo', 'mkdir', '-p', modules_backup], check=True)
        #    subprocess.run(['sudo', 'mv', modules_dir, modules_backup], check=True)

        # Backup important Raspbian directories before cleaning
        backup_tar = os.path.join(root_mount, "raspbian_preserve.tar")
        backup_tar_tmp = "/tmp/raspbian_preserve.tar"
        dirs_to_backup = []
        if os.path.exists(os.path.join(root_mount, "usr/lib/modules")):
            print("Backing up /usr/lib/modules...")
            dirs_to_backup.append("usr/lib/modules")
        else:
            print("No /usr/lib/modules found, skipping backup.")
        if os.path.exists(os.path.join(root_mount, "usr/src")):
            print("Backing up /usr/src...")
            dirs_to_backup.append("usr/src")
        else:
            print("No /usr/src found, skipping backup.")

        if os.path.exists(os.path.join(root_mount, "usr/lib/firmware")):
            dirs_to_backup.append("usr/lib/firmware")
        usr_lib = os.path.join(root_mount, "usr/lib")
        for entry in os.listdir(usr_lib):
            if entry.startswith("rasp"):
                dirs_to_backup.append(f"usr/lib/{entry}")
        if dirs_to_backup:
            subprocess.run(
                ["sudo", "tar", "cf", backup_tar] + dirs_to_backup,
                cwd=root_mount,
                check=True
            )
            # Move the tar to /tmp/ so it survives the cleanup
            subprocess.run(['sudo', 'mv', backup_tar, backup_tar_tmp], check=True)

        # Clean root partition except for /boot, then copy Azurelinux files
        for entry in os.listdir(root_mount):
            if entry == 'boot':
                continue
            entry_path = os.path.join(root_mount, entry)
            if os.path.isdir(entry_path):
                subprocess.run(['sudo', 'rm', '-rf', entry_path], check=True)
            else:
                subprocess.run(['sudo', 'rm', '-f', entry_path], check=True)

        # Copy Azurelinux files into root partition
        for entry in os.listdir(azurelinux):
            src = os.path.join(azurelinux, entry)
            dst = os.path.join(root_mount, entry)
            if os.path.isdir(src):
                subprocess.run(['sudo', 'cp', '-a', src, dst], check=True)
            else:
                subprocess.run(['sudo', 'cp', src, dst], check=True)

        # Restore the preserved directories from the tar archive
        if os.path.exists(backup_tar_tmp):
            print(f"Restoring preserved directories from {backup_tar_tmp}...")
            subprocess.run(
                ["sudo", "tar", "xf", backup_tar_tmp, "-C", root_mount],
                check=True
            )
            subprocess.run(['sudo', 'rm', '-f', backup_tar_tmp], check=True)
        else:
            print(f"No preserved directories found in {backup_tar_tmp}, skipping restoration.")

        ## Ensure 'rw' is present at the end of /boot/cmdline.txt
        #cmdline_path = os.path.join(azurelinux, 'boot', 'firmware', 'cmdline.txt')
        #if os.path.exists(cmdline_path):
        #    subprocess.run(['sudo', 'sed', '-i', r's/$/ rw/', cmdline_path], check=True)

        print("Combined image created successfully.")

    finally:
        time.sleep(5)  # Ensure all operations are complete before unmounting
        subprocess.run(['sudo', 'umount', boot_mount], check=True)
        subprocess.run(['sudo', 'umount', root_mount], check=True)
        subprocess.run(['sudo', 'losetup', '-d', loop_device], check=True)
        shutil.rmtree(boot_mount)
        shutil.rmtree(root_mount)

def cleanup():
    '''
    It cleans up the azurelinux_extracted folder as root,
    the uncompressed RaspiOS image, and compresses the final AzureLinux image.
    :return: None
    '''
    extract_to = "azurelinux_extracted"
    raspbian_sd_image_extracted_img = "2025-05-13-raspios-bookworm-arm64-lite.img"
    azurelinux_image = "azl-pi.img"
    
    # Rename the combined image to azl-pi.img
    if os.path.exists(raspbian_sd_image_extracted_img) and not os.path.exists(azurelinux_image):
        shutil.move(raspbian_sd_image_extracted_img, azurelinux_image)
        print(f"Renamed {raspbian_sd_image_extracted_img} to {azurelinux_image}")
    # Remove the extracted Azurelinux directory
    if os.path.exists(extract_to):
        subprocess.run(['sudo', 'rm', '-rf', extract_to], check=True)
        print(f"Removed {extract_to}")
    # Remove the uncompressed Raspberry Pi SD image
    if os.path.exists(raspbian_sd_image_extracted_img):
        os.remove(raspbian_sd_image_extracted_img)
        print(f"Removed {raspbian_sd_image_extracted_img}")
    # Compress the final AzureLinux image
    if os.path.exists(azurelinux_image):
        nproc = int(subprocess.check_output(['nproc'], text=True).strip())
        subprocess.run(['zstd', f'-v9T', azurelinux_image], check=True)
        print(f"Compressed {azurelinux_image} to {azurelinux_image}.zst")
    else:
        print(f"{azurelinux_image} does not exist, skipping compression.")


def main():
    subprocess.run(['sudo', 'losetup', '-D'], check=True)
    # Docker image for Azurelinux
    azurelinux_docker_image = "mcr.microsoft.com/azurelinux/base/core:3.0"
    extract_to = "azurelinux_extracted"
    raspbian_sd_image_url = "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2025-05-13/2025-05-13-raspios-bookworm-arm64-lite.img.xz"
    raspbian_sd_image_path = "2025-05-13-raspios-bookworm-arm64-lite.img.xz"
    raspbian_sd_image_extracted_path = "2025-05-13-raspios-bookworm-arm64-lite.img"

    # Pull the Azurelinux Docker image
    subprocess.run(['podman', 'pull', azurelinux_docker_image], check=True)

    # Create a container from the image (but do not start it)
    container_id = subprocess.check_output(
        ['podman', 'create', azurelinux_docker_image],
        text=True
    ).strip()

    # Copy files from the container to the extract_to directory
    if os.path.exists(extract_to):
        shutil.rmtree(extract_to)
    os.makedirs(extract_to, exist_ok=True)
    subprocess.run(['podman', 'cp', f'{container_id}:/', extract_to], check=True)

    # Remove the container
    subprocess.run(['podman', 'rm', container_id], check=True)

    # Download the Raspberry Pi SD image
    download_file(raspbian_sd_image_url, raspbian_sd_image_path)

    # Extract the Raspberry Pi SD image
    if not os.path.exists(raspbian_sd_image_path):
        raise FileNotFoundError(f"Raspberry Pi SD image {raspbian_sd_image_path} does not exist.")
    print(f"Extracting {raspbian_sd_image_path}...")
    if not os.path.exists(raspbian_sd_image_path.replace('.xz', '')):
        # Use xz to decompress the image
        print("Decompressing Raspberry Pi SD image...")    
        subprocess.run(['xz', '-dk', raspbian_sd_image_path], check=True)

    # Mount the extracted Raspberry Pi SD image
    raspbian_sd_image_extracted_path = raspbian_sd_image_path.replace('.xz', '')
    if not os.path.exists(raspbian_sd_image_extracted_path):
        raise FileNotFoundError(f"Extracted Raspberry Pi SD image {raspbian_sd_image_extracted_path} does not exist.")
    combine_images(raspbian_sd_image_extracted_path, extract_to)
    
    print("Bootable SD image for Raspberry Pi created successfully.")
    cleanup()

if __name__ == "__main__":
    main()
