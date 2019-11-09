import sys

filepath = sys.argv[1]

with open(filepath, 'rb') as f:
    # Given a path to the /proc/[pid]/maps and a offset (and page table entry size)
    # read_entry seeks the files, finds its bytes
    # and retuns
        offset = 1024
        f.seek(offset, 0)
        inodes = struct.unpack('I', f.read(size))[0]
        print('There are {} inodes'.format(inodes))


    


