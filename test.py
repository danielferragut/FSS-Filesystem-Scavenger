import sys
import struct

def main():
    filepath = sys.argv[1]
    base_offset = 1024

    # Getting basic info about the filesystem
    total_inodes = read_filesystem(filepath, base_offset, 4)
    block_count = read_filesystem(filepath, base_offset + 4, 4)
    free_blocks = read_filesystem(filepath, base_offset + 12, 4)
    free_inodes = read_filesystem(filepath, base_offset + 16, 4)
    block_size = 1024 << read_filesystem(filepath, base_offset + 24, 4)
    blocks_per_group = read_filesystem(filepath, base_offset + 32, 4)
    inodes_per_group = read_filesystem(filepath, base_offset + 40, 4)

    # Info about the block bitmap and what not
    if block_size == 1024:
        block_descriptor = base_offset + (2 * block_size)
    else:
        block_descriptor = base_offset + block_size
    block_descriptor = 4096

    bg_block_bitmap = read_filesystem(filepath, block_descriptor, 4)
    bg_inode_bitmap = read_filesystem(filepath, block_descriptor+4, 4)
    bg_inode_table = read_filesystem(filepath, block_descriptor+8, 4)
    print(bg_block_bitmap, bg_inode_bitmap, bg_inode_table)

    disk_space, disk_space_unit = parse_disk_space(free_blocks * block_size)
    print('Filesytem being scavenged: {}'.format(filepath))
    print('Free space available: {:0.2f} {}'.format(disk_space, disk_space_unit))


def read_filesystem(filepath, offset, size):
    with open(filepath, 'rb') as f:
        f.seek(offset, 0)
        if size == 4:
            unpack_char = 'I'
        elif size == 2:
            unpack_char = 'H'
        elif size == 8:
            unpack_char = 'Q'
        bytes_read = struct.unpack(unpack_char, f.read(size))[0]
        return bytes_read

def parse_disk_space(number_of_bytes):
    disk_space =  number_of_bytes / 1024  #Disk space in kB
    if disk_space > 1024:
        if disk_space > 1024*1024:
            disk_space = disk_space / (1024*1024)
            unit = 'gB'
        else:
            disk_space = disk_space / 1024
            unit = 'mB'
    else:
        unit = 'kB'
    return disk_space, unit

if __name__ == '__main__':
    main()
