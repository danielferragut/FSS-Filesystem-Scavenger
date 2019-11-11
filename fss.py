#  Authors:
#   Daniel Pereira Ferragut  RA: 169488
#   Lucas Koiti G. Tamanaha  RA: 182579

# Warning: On files with 20 GB or more, this program might take 2 min ~ to run.


# The only external lib that this program needs is a quality of life lib
# This lib makes that there is a progress bar, indicating how much iterations are left
from tqdm import tqdm

# Internal python libs
import sys
import struct
import itertools
from math import ceil
from math import log
from collections import defaultdict

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
    s_log_block_size = read_filesystem(filepath, base_offset + 24, 4)
    block_size = 1024 << s_log_block_size
    blocks_per_group = read_filesystem(filepath, base_offset + 32, 4)
    inodes_per_group = read_filesystem(filepath, base_offset + 40, 4)
    total_groups = ceil(block_count / blocks_per_group)

    # Vars that will assist advanced analysis about the filesystem
    free_blocks_dict = defaultdict(bool)
    inode_allocated_blocks_list = []
    total_free_segments = 0

    # For every group, find its group info, get free block segments and inode info
    for i in tqdm(range(total_groups)):
        block_number = blocks_per_group * i
        inode_base_number = inodes_per_group * i

        # If this block has a superblock or a copy
        if has_superblock(i):
            block_descriptor = (block_number + 1) * block_size
            bg_block_bitmap = read_filesystem(filepath, block_descriptor, 4) + block_number
            bg_inode_bitmap = read_filesystem(filepath, block_descriptor + 4, 4) + block_number
            bg_inode_table = (read_filesystem(filepath, block_descriptor + 8, 4) + block_number) * block_size

            block_bitmap = read_block_bitmap(filepath, bg_block_bitmap, block_size)
            inode_bitmap = read_block_bitmap(filepath, bg_inode_bitmap, block_size)
        else:
            block_bitmap = read_block_bitmap(filepath, block_number, block_size)
            inode_bitmap = read_block_bitmap(filepath, block_number + 1, block_size)
            bg_inode_table = (block_number + 2) * block_size

        group_free_blocks = get_free_blocks(block_bitmap)
        for i, block in enumerate(group_free_blocks):
            group_free_blocks[i] = block + block_number
            free_blocks_dict[block + block_number] = True

        free_segments = list(interval_extract(group_free_blocks))

        # =============== Getting allocated blocks for each inode ================================
        allocated_inodes_segments = 0
        user_inodes_sizes = []
        allocated_inodes = get_allocated_inodes(inode_bitmap, inodes_per_group)
        # For each inode
        #   get its info, check if is user inode(item 5), get the allocated blocks
        for inode in allocated_inodes:
            blocks_used = []
            offset = bg_inode_table + ((inode - 1) * 128)
            i_mode = read_filesystem(filepath, offset, 2)
            i_size = read_filesystem(filepath, offset + 4, -4)
            i_blocks = read_filesystem(filepath, offset + 28, 4)

            # If it is a user inode, store its size
            if i_mode & 0x8000 == 0x8000:
                user_inodes_sizes.append(i_size)
            max_index = i_blocks // (2 << s_log_block_size)

            # Get block ids in i_block
            i_block = []
            for i in range(15):
                block_offset = offset + 40 + (i * 4)
                i_block.append(read_filesystem(filepath, block_offset, 4))
            # Parse each id in i_block find allocated blocks
            for i in range(15):
                if len(blocks_used) >= max_index:
                    break
                current_block_id = i_block[i]
                if i < 12:
                    if current_block_id != 0:
                        blocks_used.append(current_block_id)
                else:
                    if i == 12:
                        blocks_used = blocks_used + parse_block_1st_indirect(current_block_id, filepath, block_size)
                    elif i == 13:
                        blocks_used = blocks_used + parse_block_2nd_indirect(current_block_id, filepath, block_size)
                    elif i == 14:
                        blocks_used = blocks_used + parse_block_3rd_indirect(current_block_id, filepath, block_size)
            if len(blocks_used) != 0:
                inode_allocated_blocks_list.append(blocks_used)

        # Cleaning segments of 1 block, if config flag is set (start of the code)
        if SEGMENTS_ARE_2_OR_MORE_BLOCKS:
            for i, segment in enumerate(free_segments):
                if segment[0] == segment[1]:
                    del free_segments[i]

        total_free_segments += len(free_segments)

    # Check how many allocated segments there are
    allocated_segments_inode = 0
    for i, inode in enumerate(inode_allocated_blocks_list):
        for j, block in enumerate(inode):
            if free_blocks_dict[block] == True:
                del inode[j]
        segments = list(interval_extract(sorted(inode)))
        allocated_segments_inode += len(segments)

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
    print('Total free segments: {}'.format(total_free_segments))
    print('Free Space per segment: {} KB/segm'.format(disk_space_kb // total_free_segments))
    print('Allocated Fragments: {} KB/segm'.format(disk_used_kb // allocated_segments_inode))
    print('Inode Fragments: {:0.2f} '.format(allocated_segments_inode / total_inodes))
    print_tanebaum_table(user_inodes_sizes)


# Read a bitmap and returns a list of bits
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


# Reads a single info on the filepath, given a offset and its size
def read_filesystem(filepath, offset, size):
    with open(filepath, 'rb') as f:
        f.seek(offset, 0)
        if size == 4:
            unpack_char = 'I'
        elif size == -4:
            size = 4
            unpack_char = 'i'
        elif size == 2:
            unpack_char = 'H'
        elif size == 8:
            unpack_char = 'Q'
        bytes_read = struct.unpack(unpack_char, f.read(size))[0]
        return bytes_read

# Parse disk_space so its more readable
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


# Get the free blocks in a block bitmap
def get_free_blocks(block_bitmap):
    free_blocks = []
    for i, bit in enumerate(block_bitmap):
        if bit == 0:
            free_blocks.append(i)
    return free_blocks

# Get the allocated inodes in the inodes bitmap
def get_allocated_inodes(inodes_bitmap, inodes_per_group):
    inodes = []
    for i in range(inodes_per_group):
        bit = inodes_bitmap[i]
        if bit == 1:
            inodes.append(i + 1)
    return inodes

# Find segments in a int list (function taken from the internet)
def interval_extract(iterable):
    iterable = sorted(set(iterable))
    for key, group in itertools.groupby(enumerate(iterable),
                                        lambda t: t[1] - t[0]):
        group = list(group)
        yield [group[0][1], group[-1][1]]

# Check if the current group has a superblock or copy
def has_superblock(i):
    if i == 0 or i == 1:
        return True
    if log(i, 3).is_integer() or log(i, 5).is_integer() or log(i, 7).is_integer():
        return True
    return False

# Print a table like Tanebaum's table
def print_tanebaum_table(user_inodes_sizes):
    sizes_dict = defaultdict(int)
    total_inodes = len(user_inodes_sizes)
    for inode_size in user_inodes_sizes:
        base_size = 128 * 1024 * 1024  # 1 B
        while base_size != 0:
            if inode_size < base_size:
                sizes_dict[base_size] += 1
                base_size = base_size // 2
            else:
                break
    print('LENGHT        ||           EVEREST:')
    base_size = 1  # 1 B
    while base_size != 128 * 1024 * 1024 * 2:
        size, unit = parse_bytes(base_size)
        if len(str(size)) == 1:
            print('{} {}          ||           {:0.1f}%'.format(size, unit, 100 * sizes_dict[base_size] / total_inodes))
        elif len(str(size)) == 2:
            print('{} {}         ||           {:0.1f}%'.format(size, unit, 100 * sizes_dict[base_size] / total_inodes))
        elif len(str(size)) == 3:
            print('{} {}        ||           {:0.1f}%'.format(size, unit, 100 * sizes_dict[base_size] / total_inodes))
        elif len(str(size)) == 4:
            print('{} {}       ||           {:0.1f}%'.format(size, unit, 100 * sizes_dict[base_size] / total_inodes))
        base_size = base_size * 2

# Parse bytes so it is more readable
def parse_bytes(bytes):
    if bytes > 1024:
        bytes = bytes // 1024
        if bytes > 1024:
            bytes = bytes // 1024
            unit = 'MB'
        else:
            unit = 'KB'
    else:
        unit = 'B'
    return bytes, unit

# Deals with the first indirect layer of inode i_block
def parse_block_1st_indirect(current_block_id, filepath, block_size):
    offset = current_block_id * block_size
    blocks_used = [current_block_id]
    block_read = read_block(filepath, current_block_id, block_size)
    for i in range(block_size // 4):
        block_id_read = block_id_read = block_read[offset + (i * 4): offset + (i * 4) + 4]
        if block_id_read == b'':
            break
        block_id_read = struct.unpack('I', block_id_read)[0]
        if block_id_read != 0:
            blocks_used.append(block_id_read)
    return blocks_used

# Deals with the second indirect layer of inode i_block
def parse_block_2nd_indirect(current_block_id, filepath, block_size):
    offset_2nd_block = current_block_id * block_size
    blocks_used = [current_block_id]
    block_read = read_block(filepath, current_block_id, block_size)
    for i in range(block_size // 4):
        indirect_1st_block = block_read[offset_2nd_block + (i * 4): offset_2nd_block + (i * 4) + 4]
        if indirect_1st_block == b'':
            break
        indirect_1st_block = struct.unpack('I', indirect_1st_block)[0]
        if indirect_1st_block != 0:
            blocks_used = blocks_used + parse_block_1st_indirect(indirect_1st_block, filepath, block_size)
    return blocks_used

# Deals with the third indirect layer of inode i_block
def parse_block_3rd_indirect(current_block_id, filepath, block_size):
    offset_3rd_block = current_block_id * block_size
    blocks_used = [current_block_id]
    block_read = read_block(filepath, current_block_id, block_size)
    for i in range(block_size // 4):
        indirect_2nd_block = block_read[offset_3rd_block + (i * 4): offset_3rd_block + (i * 4) + 4]
        if indirect_2nd_block == b'':
            break
        indirect_2nd_block = struct.unpack('I', indirect_2nd_block)[0]
        if indirect_2nd_block != 0:
            blocks_used = blocks_used + parse_block_2nd_indirect(indirect_2nd_block, filepath, block_size)

    return blocks_used

# Reads a whole block from the filesystem, more efficient
def read_block(filepath, block_number, block_size):
    with open(filepath, 'rb') as f:
        f.seek(block_number * block_size)
        bytes_read = f.read(block_size)
    return bytes_read


if __name__ == '__main__':
    main()
