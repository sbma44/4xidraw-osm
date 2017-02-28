import re
import glob
import sys
import os.path

RE_COORD = re.compile(r'([XY])(\d+(\.\d+)?)')

def get_gcode_files():
    for arg in sys.argv[1:]:
        for fn in glob.iglob(arg):
            if fn:
                yield fn

def get_file_extents(gcode_file):
    extent = [None, None, None, None]
    with open(gcode_file) as f:
        for line in f:
            line_parts = line.split(' ')
            if line_parts[0] not in ('G00', 'G01'):
                continue
            for line_part in line_parts[1:]:
                m = RE_COORD.match(line_part)
                if m is None:
                    continue
                modifier = 0
                if m.group(1) == 'Y':
                    modifier = 1
                for (compare, offset) in ((min, modifier), (max, 2 + modifier)):
                    if extent[offset] is None:
                        extent[offset] = float(m.group(2))
                    else:
                        extent[offset] = compare(extent[offset], float(m.group(2)))
    return extent

def translate_gcode_file(gcode_file, x_offset, y_offset):
    out_file = open('.'.join(os.path.basename(gcode_file).split('.')[:-1]) + '.translated.g', 'w')
    with open(gcode_file) as f:
        for line in f:
            for (i, line_part) in enumerate(line.split(' ')):
                if i > 0:
                    out_file.write(' ')
                m = RE_COORD.match(line_part)
                if m is None:
                    out_file.write(line_part)
                else:
                    offset = x_offset
                    if m.group(1) == 'Y':
                        offset = y_offset
                    out_file.write(m.group(1))
                    out_file.write('{:.3f}'.format(float(m.group(2)) + offset))
            out_file.write('\n')
    out_file.close()

if __name__ == '__main__':
    extents = None
    for gcode_file in get_gcode_files():
        file_extents = get_file_extents(gcode_file)
        if extents is None:
            extents = file_extents
        else:
            for i in range(0, 4):
                compare = i < 2 and min or max
                extents[i] = compare(file_extents[i], extents[i])
    for gcode_file in get_gcode_files():
        translate_gcode_file(gcode_file, -1 * extents[0], -1 * extents[1])