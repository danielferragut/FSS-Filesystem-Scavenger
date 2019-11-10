import sys
import struct
import itertools
from math import ceil
from math import log
# There is not a clear definition if segments can be made of only one block
# Therefore, if segments are 2 or more blocks, set this flag to True
SEGMENTS_ARE_2_OR_MORE_BLOCKS = False


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

    # # Info about the block bitmap and what not
    # if block_size == 1024:
    #     block_descriptor = base_offset + (2 * block_size)
    # else:
    #     block_descriptor = base_offset + block_size
    total_free_segments = 0
    total_allocated_inodes_segments = 0
    total_groups = ceil(block_count/blocks_per_group)
    for i in range(total_groups):
        block_number = blocks_per_group * i
        inode_base_number = inodes_per_group * i
        if has_superblock(i):
            block_descriptor = (block_number + 1) * block_size
            bg_block_bitmap = read_filesystem(filepath, block_descriptor, 4) + block_number
            bg_inode_bitmap = read_filesystem(filepath, block_descriptor + 4, 4) + block_number
            bg_inode_table = read_filesystem(filepath, block_descriptor + 8, 4) + block_number

            block_bitmap = read_block_bitmap(filepath, bg_block_bitmap, block_size)
            inode_bitmap = read_block_bitmap(filepath, bg_inode_bitmap, block_size)
        else:
            block_bitmap = read_block_bitmap(filepath, block_number, block_size)
            inode_bitmap = read_block_bitmap(filepath, block_number + 1, block_size)

        group_free_blocks = get_free_blocks(block_bitmap)
        allocated_inodes = get_allocated_inodes(inode_bitmap)

        for i, block in enumerate(group_free_blocks):
            group_free_blocks[i] = block + block_number
        for i, inode in enumerate(allocated_inodes):
            allocated_inodes[i] = inode + inode_base_number


        free_segments = list(interval_extract(group_free_blocks))
        allocated_inodes_segments = list(interval_extract(allocated_inodes))

        # Cleaning segments of 1 block, if config flag is set (start of the code)
        if SEGMENTS_ARE_2_OR_MORE_BLOCKS:
            for i, segment in enumerate(free_segments):
                if segment[0] == segment[1]:
                    del free_segments[i]
            for i, segment in enumerate(allocated_inodes_segments):
                if segment[0] == segment[1]:
                    del free_segments[i]

        total_free_segments += len(free_segments)
        total_allocated_inodes_segments += len(allocated_inodes_segments)

    used_blocks = block_count - free_blocks
    disk_space_kb = (free_blocks * block_size) / 1024
    disk_used_kb = (used_blocks * block_size) / 1024
    disk_total_kb = block_count * block_size / 1024
    disk_space_readable, disk_space_unit = parse_disk_space(disk_space_kb)
    disk_used_readable, disk_used_unit = parse_disk_space(disk_used_kb)
    disk_total_readable, disk_total_unit = parse_disk_space(disk_total_kb)

    print('============ Basic Filesystem Info ============')
    print('Filesytem being scavenged: {}'.format(filepath))
    print('Filesystem size: {:0.2f} {}'.format(disk_total_readable, disk_total_unit))
    print('Allocated space: {:0.2f} {}'.format(disk_used_readable, disk_used_unit))
    print('Free space available: {:0.2f} {}'.format(disk_space_readable, disk_space_unit))
    print('============ Advanced Filesystem Info ============')
    print('Free Fragments: {} KB/segm'.format(disk_space_kb // total_free_segments))
    print('Allocated Fragments: {} KB/segm'.format(disk_used_kb//total_allocated_inodes_segments))
    print('Inode Fragments: {:0.2f} '.format(total_allocated_inodes_segments/total_inodes))


def read_block_bitmap(filepath, offset, size):
    offset = offset * size
    bytes_read = []
    bits_list = []
    with open(filepath, 'rb') as f:
        f.seek(offset, 0)
        for i in range(size):
            bytes_read.append(struct.unpack('B', f.read(1))[0])
        for byte in bytes_read:
            bits_list.append(byte >> 0 & 1)
            bits_list.append(byte >> 1 & 1)
            bits_list.append(byte >> 2 & 1)
            bits_list.append(byte >> 3 & 1)
            bits_list.append(byte >> 4 & 1)
            bits_list.append(byte >> 5 & 1)
            bits_list.append(byte >> 6 & 1)
            bits_list.append(byte >> 7 & 1)

        return bits_list


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


def parse_disk_space(disk_space):
    if disk_space > 1024:
        if disk_space > 1024 * 1024:
            disk_space = disk_space / (1024 * 1024)
            unit = 'GB'
        else:
            disk_space = disk_space / 1024
            unit = 'MB'
    else:
        unit = 'KB'
    return disk_space, unit


def get_free_blocks(block_bitmap):
    free_blocks = []
    for i, bit in enumerate(block_bitmap):
        if bit == 0:
            free_blocks.append(i)
    return free_blocks


def get_allocated_inodes(inodes_bitmap):
    inodes = []
    for i, bit in enumerate(inodes_bitmap):
        if bit == 1:
            inodes.append(i + 1)
    return inodes


def interval_extract(iterable):
    iterable = sorted(set(iterable))
    for key, group in itertools.groupby(enumerate(iterable),
                                        lambda t: t[1] - t[0]):
        group = list(group)
        yield [group[0][1], group[-1][1]]

def has_superblock(i):
    if i == 0 or i == 1:
        return True
    if log(i, 3).is_integer() or log(i,5).is_integer() or log(i,7).is_integer():
        return True
    return False
if __name__ == '__main__':
    main()
