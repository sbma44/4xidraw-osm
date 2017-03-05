#!/usr/bin/env python

'''
4xidraw Inkscape Exporter

-----------------------------------

Copyright (c) 2017 Thomas Lee <thomas.j.lee@gmail.com>
Copyright (C) 2009 Nick Drobchenko, nick@cnc-club.ru
based on gcode.py (C) 2007 hugomatic...
based on addnodes.py (C) 2005,2007 Aaron Spike, aaron@ekips.org
based on dots.py (C) 2005 Aaron Spike, aaron@ekips.org
based on interp.py (C) 2005 Aaron Spike, aaron@ekips.org

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
'''

'''

Changelog 2017-03-01:
* More 4xidraw customization
  - trim unneeded functionality (e.g. laser power settings)
  - optimize path ordering for longer continuous drawing strokes
  - rewrite portions to be more pythonic

Changelog 2016-02-11:
* Adapt for 4xidraw
  - swap strings
  - reorder paths for continuous drawing

Changelog 2015-02-01:
* Beginning of the project. Based on a fork from ShinyLaser(https://github.com/ajfoul/thlaser-inkscape-plugin)

Changelog 2015-02-16:
Added an option to export as Marlin or Smoothie Power levels

Changelog 2015-03-07:
Added capability to pick out power, ppm, feedrate etc from the layer names
Added code to support Pulse Per Minute burning or continuous burning. Will default to continuous.
M649 S100 L300 P10 - Set Laser settings to 100 percent power, pulses are each 300ms, and 10 pulses per mm.
G0 : Move to a new location with the laser off.
G1 : Move to a new location with the laser on.
G2 : Move in a Clockwise Arc
G3 : Move in a Counter Clockwise Arc
Name your layer like 10 [feed=600,ppm=40] for 10% power, 600mm per minute cut and 40 pulse per millimetre at 60ms duration

Changelog 2015-03-27
Changelog 2015-03-28
Fixed many many bugs, completed the work on exporting objects and images as rasters.
Fixed up as many situations I could find that threw python error messages and replaced them with meaningful notices for the user.

Changelog 2015-03-30
Accounts for strokes on objects. Conditional raster export as some items in inkscape are positioned strangely.

Changelog 2015-04-1
Need to get the 'positioning for all' functionality working as exporting many raster objects is painfully slow.
Updated script to export rasters with top left as the origin or bottom left.

Changelog 2015-04-10
Fixed a bug with exporting paths when the origin was the top left.
Disabled raster horizintal movement optimisation as it has a bug. Rasters will be a little slower but will come out oriented correctly. Search for line : row2 = rowData

Changelog 2015-04-11
Added back in raster optimising, it's not perfect but it's mostly there. Only a little slow parsing white vertical space now.
Found that raster optimisation code seems to be changing the pixel data at the end of the line somewhere. I'm not sure how since it's meant to just be cutting part of the data line out not changing it. will need to investigate further.
Added option to the menu for users to disable raster optimisations.

Changelog 2015-05-09
Spent a day stuffing around with the exporter and marlin firmware to figure out why pronterface was throwing checksum errors when
sending lots of G02 and G03 arc vector cuts. It turns out that with too much precision in the cuts marlin's buffer fills up and it's
unable to receive any more serial data. I resolved this by reducing the float point precision down to 3 decimal places and shifting
power and pulse settings to the G00 move command that comes before a set of G01, G02 and G03 commands to limit data that's needed to
be sent over the wire.

Changelog 2015-05-255
Updated GCodes to optimise when it sends PPM and laser power info.
Added a Pronterface option which is enabled by default to allow rasters to be printed with pronterface.
Added M80 command for Tim from LMN

I also fixed up the part of the exporter to allow the offset and scaling functions to work. Though I found that looking at the scaling
code it will only scale from the original 0,0 coordinate, it doesn't scale based on a centre point.
'''

###
###        Gcode tools
###

import inkex, simplestyle, simplepath
import cubicsuperpath, simpletransform, bezmisc

import os, os.path
import math
import bezmisc
import re
import copy
import sys
import time
import json
import tempfile

# Image processing for rastering
import base64
from PIL import Image
from PIL import ImageOps
import subprocess
import simplestyle

import getopt
from io import BytesIO

import logging
logger = logging.getLogger('4xidraw')
hdlr = logging.FileHandler('/tmp/4xidraw.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.INFO)

################################################################################
###
###        Constants
###
################################################################################

VERSION = '1.1.0'

STRAIGHT_TOLERANCE = 0.0001
STRAIGHT_DISTANCE_TOLERANCE = 0.0001
PEN_DOWN = 'M3 S0\n'
PEN_UP = 'M3 S100\nG4P0.1\n'

# Inkscape group tag
SVG_GROUP_TAG = inkex.addNS('g', 'svg')
SVG_PATH_TAG = inkex.addNS('path','svg')
SVG_IMAGE_TAG = inkex.addNS('image', 'svg')
SVG_TEXT_TAG = inkex.addNS('text', 'svg')
SVG_LABEL_TAG = inkex.addNS('label', 'inkscape')

GCODE_EXTENSION = 'gcode'

options = {}

################################################################################
###
###        Common functions
###
################################################################################


###
###        Point (x,y) operations
###
## Pretty much what it sounds like: defines some arithmetic functions that can be applied to points.
class P:
    def __init__(self, x, y=None):
        if not y==None:
            self.x, self.y = float(x), float(y)
        else:
            self.x, self.y = float(x[0]), float(x[1])
    def __add__(self, other): return P(self.x + other.x, self.y + other.y)
    def __sub__(self, other): return P(self.x - other.x, self.y - other.y)
    def __neg__(self): return P(-self.x, -self.y)
    def __mul__(self, other):
        if isinstance(other, P):
            return self.x * other.x + self.y * other.y
        return P(self.x * other, self.y * other)
    __rmul__ = __mul__
    def __div__(self, other): return P(self.x / other, self.y / other)
    def mag(self): return math.hypot(self.x, self.y)
    def unit(self):
        h = self.mag()
        if h: return self / h
        else: return P(0,0)
    def dot(self, other): return self.x * other.x + self.y * other.y
    def rot(self, theta):
        c = math.cos(theta)
        s = math.sin(theta)
        return P(self.x * c - self.y * s,  self.x * s + self.y * c)
    def angle(self): return math.atan2(self.y, self.x)
    def __repr__(self): return '%f,%f' % (self.x, self.y)
    def pr(self): return '%.2f,%.2f' % (self.x, self.y)
    def to_list(self): return [self.x, self.y]


###
###        Functions to operate with CubicSuperPath
###

def csp_at_t(sp1,sp2,t):
    bez = (sp1[1][:],sp1[2][:],sp2[0][:],sp2[1][:])
    return     bezmisc.bezierpointatt(bez,t)

def cspbezsplit(sp1, sp2, t = 0.5):
    s1,s2 = bezmisc.beziersplitatt((sp1[1],sp1[2],sp2[0],sp2[1]),t)
    return [ [sp1[0][:], sp1[1][:], list(s1[1])], [list(s1[2]), list(s1[3]), list(s2[1])], [list(s2[2]), sp2[1][:], sp2[2][:]] ]

def cspbezsplitatlength(sp1, sp2, l = 0.5, tolerance = 0.01):
    bez = (sp1[1][:],sp1[2][:],sp2[0][:],sp2[1][:])
    t = bezmisc.beziertatlength(bez, l, tolerance)
    return cspbezsplit(sp1, sp2, t)

def cspseglength(sp1,sp2, tolerance = 0.001):
    bez = (sp1[1][:],sp1[2][:],sp2[0][:],sp2[1][:])
    return bezmisc.bezierlength(bez, tolerance)

def csplength(csp):
    total = 0
    lengths = []
    for sp in csp:
        for i in xrange(1,len(sp)):
            l = cspseglength(sp[i-1],sp[i])
            lengths.append(l)
            total += l
    return lengths, total


###
###        Distance calculattion from point to arc
###

def between(c,x,y):
        return x-STRAIGHT_TOLERANCE<=c<=y+STRAIGHT_TOLERANCE or y-STRAIGHT_TOLERANCE<=c<=x+STRAIGHT_TOLERANCE

def distance_from_point_to_arc(p, arc):
    P0,P2,c,a = arc
    dist = None
    p = P(p)
    r = (P0-c).mag()
    if r>0 :
        i = c + (p-c).unit()*r
        alpha = ((i-c).angle() - (P0-c).angle())
        if a*alpha<0:
            if alpha>0:    alpha = alpha-2*math.pi
            else: alpha = 2*math.pi+alpha
        if between(alpha,0,a) or min(abs(alpha),abs(alpha-a))<STRAIGHT_TOLERANCE :
            return (p-i).mag(), [i.x, i.y]
        else :
            d1, d2 = (p-P0).mag(), (p-P2).mag()
            if d1<d2 :
                return (d1, [P0.x,P0.y])
            else :
                return (d2, [P2.x,P2.y])

def get_distance_from_csp_to_arc(sp1,sp2, arc1, arc2, tolerance = 0.001 ): # arc = [start,end,center,alpha]
    n, i = 10, 0
    d, d1, dl = (0,(0,0)), (0,(0,0)), 0
    while i<1 or (abs(d1[0]-dl[0])>tolerance and i<2):
        i += 1
        dl = d1*1
        for j in range(n+1):
            t = float(j)/n
            p = csp_at_t(sp1,sp2,t)
            d = min(distance_from_point_to_arc(p,arc1), distance_from_point_to_arc(p,arc2))
            d1 = max(d1,d)
        n=n*2
    return d1[0]

def distance_between_paths(p1, p2, reverse=False):
    p1_end = p1['data'][0][-1][0]
    p2_start = p2['data'][0][0][0]
    if reverse:
        p2_start = p2['data'][0][-1][0]
    return math.sqrt((p2_start[0] - p1_end[0])**2 + (p2_start[1] - p1_end[1])**2)

def reverse_path(p):
    p['data'][0] = list(reversed(p['data'][0]))
    return p

################################################################################
###
###        Biarc function
###
###        Calculates biarc approximation of cubic super path segment
###        splits segment if needed or approximates it with straight line
###
################################################################################


def biarc(sp1, sp2, z1, z2, depth=0,):
    def biarc_split(sp1,sp2, z1, z2, depth):
        if depth<options.biarc_max_split_depth:
            sp1,sp2,sp3 = cspbezsplit(sp1,sp2)
            l1, l2 = cspseglength(sp1,sp2), cspseglength(sp2,sp3)
            if l1+l2 == 0 : zm = z1
            else : zm = z1+(z2-z1)*l1/(l1+l2)
            return biarc(sp1,sp2,depth+1,z1,zm)+biarc(sp2,sp3,depth+1,z1,zm)
        else: return [ [sp1[1],'line', 0, 0, sp2[1], [z1,z2]] ]

    P0, P4 = P(sp1[1]), P(sp2[1])
    TS, TE, v = (P(sp1[2])-P0), -(P(sp2[0])-P4), P0 - P4
    tsa, tea, va = TS.angle(), TE.angle(), v.angle()
    if TE.mag()<STRAIGHT_DISTANCE_TOLERANCE and TS.mag()<STRAIGHT_DISTANCE_TOLERANCE:
        # Both tangents are zerro - line straight
        return [ [sp1[1],'line', 0, 0, sp2[1], [z1,z2]] ]
    if TE.mag() < STRAIGHT_DISTANCE_TOLERANCE:
        TE = -(TS+v).unit()
        r = TS.mag()/v.mag()*2
    elif TS.mag() < STRAIGHT_DISTANCE_TOLERANCE:
        TS = -(TE+v).unit()
        r = 1/( TE.mag()/v.mag()*2 )
    else:
        r=TS.mag()/TE.mag()
    TS, TE = TS.unit(), TE.unit()
    tang_are_parallel = ((tsa-tea)%math.pi<STRAIGHT_TOLERANCE or math.pi-(tsa-tea)%math.pi<STRAIGHT_TOLERANCE )
    if ( tang_are_parallel  and
                ((v.mag()<STRAIGHT_DISTANCE_TOLERANCE or TE.mag()<STRAIGHT_DISTANCE_TOLERANCE or TS.mag()<STRAIGHT_DISTANCE_TOLERANCE) or
                    1-abs(TS*v/(TS.mag()*v.mag()))<STRAIGHT_TOLERANCE)    ):
                # Both tangents are parallel and start and end are the same - line straight
                # or one of tangents still smaller then tollerance

                # Both tangents and v are parallel - line straight
        return [ [sp1[1],'line', 0, 0, sp2[1], [z1,z2]] ]

    c,b,a = v*v, 2*v*(r*TS+TE), 2*r*(TS*TE-1)
    if v.mag()==0:
        return biarc_split(sp1, sp2, z1, z2, depth)
    asmall, bsmall, csmall = abs(a)<10**-10,abs(b)<10**-10,abs(c)<10**-10
    if         asmall and b!=0:    beta = -c/b
    elif     csmall and a!=0:    beta = -b/a
    elif not asmall:
        discr = b*b-4*a*c
        if discr < 0:    raise ValueError, (a,b,c,discr)
        disq = discr**.5
        beta1 = (-b - disq) / 2 / a
        beta2 = (-b + disq) / 2 / a
        if beta1*beta2 > 0 :    raise ValueError, (a,b,c,disq,beta1,beta2)
        beta = max(beta1, beta2)
    elif    asmall and bsmall:
        return biarc_split(sp1, sp2, z1, z2, depth)
    alpha = beta * r
    ab = alpha + beta
    P1 = P0 + alpha * TS
    P3 = P4 - beta * TE
    P2 = (beta / ab)  * P1 + (alpha / ab) * P3

    def calculate_arc_params(P0,P1,P2):
        D = (P0+P2)/2
        if (D-P1).mag()==0: return None, None
        R = D - ( (D-P0).mag()**2/(D-P1).mag() )*(P1-D).unit()
        p0a, p1a, p2a = (P0-R).angle()%(2*math.pi), (P1-R).angle()%(2*math.pi), (P2-R).angle()%(2*math.pi)
        alpha =  (p2a - p0a) % (2*math.pi)
        if (p0a<p2a and  (p1a<p0a or p2a<p1a))    or    (p2a<p1a<p0a) :
            alpha = -2*math.pi+alpha
        if abs(R.x)>1000000 or abs(R.y)>1000000  or (R-P0).mag<options.min_arc_radius :
            return None, None
        else :
            return  R, alpha
    R1,a1 = calculate_arc_params(P0,P1,P2)
    R2,a2 = calculate_arc_params(P2,P3,P4)
    if R1==None or R2==None or (R1-P0).mag()<STRAIGHT_TOLERANCE or (R2-P2).mag()<STRAIGHT_TOLERANCE    : return [ [sp1[1],'line', 0, 0, sp2[1], [z1,z2]] ]

    d = get_distance_from_csp_to_arc(sp1,sp2, [P0,P2,R1,a1],[P2,P4,R2,a2])
    if d > options.biarc_tolerance and depth<options.biarc_max_split_depth     : return biarc_split(sp1, sp2, z1, z2, depth)
    else:
        if R2.mag()*a2 == 0 : zm = z2
        else : zm  = z1 + (z2-z1)*(R1.mag()*a1)/(R2.mag()*a2+R1.mag()*a1)
        return [    [ sp1[1], 'arc', [R1.x,R1.y], a1, [P2.x,P2.y], [z1,zm] ], [ [P2.x,P2.y], 'arc', [R2.x,R2.y], a2, [P4.x,P4.y], [zm,z2] ]        ]



################################################################################
###
###        Inkscape helper functions
###
################################################################################

# Returns true if the given node is a layer
def is_layer(node):
    return (node.tag == SVG_GROUP_TAG and
            node.get(inkex.addNS('groupmode', 'inkscape')) == 'layer')

def get_layers(document):
    layers = []
    root = document.getroot()
    for node in root.iterchildren():
        if (is_layer(node)):
            # Found an inkscape layer
            layers.append(node)
    return layers

################################################################################
###
###        Gcode tools class
###
################################################################################

class Gcode_tools(inkex.Effect):

    def __init__(self):
        inkex.Effect.__init__(self)

        outdir = os.getenv('HOME') or os.getenv('USERPROFILE')
        if (outdir):
            outdir = os.path.join(outdir, 'Desktop')
        else:
            outdir = os.getcwd()

        self.last_pos = None

        self.RE_COORD = re.compile(r'([XY])(\-?\d+(\.\d+)?)')

        self.OptionParser.add_option("", "--tab", action="store", type="string", dest="tab", default="", help="Means nothing right now. Notebooks Tab.")
        self.OptionParser.add_option('-d', '--directory', action='store', type='string', dest='directory', default=outdir, help='Directory for gcode file')
        self.OptionParser.add_option('-u', '--Xscale', action='store', type='float', dest='Xscale', default='1.0', help='Scale factor X')
        self.OptionParser.add_option('-v', '--Yscale', action='store', type='float', dest='Yscale', default='1.0', help='Scale factor Y')
        self.OptionParser.add_option('-x', '--Xoffset', action='store', type='float', dest='Xoffset', default='0.0', help='Offset along X')
        self.OptionParser.add_option('-y', '--Yoffset', action='store', type='float', dest='Yoffset', default='0.0', help='Offset along Y')
        self.OptionParser.add_option('', '--biarc-tolerance', action='store', type='float', dest='biarc_tolerance', default='1', help='Tolerance used when calculating biarc interpolation.')
        self.OptionParser.add_option('', '--biarc-max-split-depth', action='store', type='int', dest='biarc_max_split_depth', default='4', help='Defines maximum depth of splitting while approximating using biarcs.')
        self.OptionParser.add_option('', '--min-arc-radius', action='store', type='float', dest='min_arc_radius', default='0.0005', help='All arc having radius less than minimum will be considered as straight line')

    def parse_curve(self, path):
        xs,ys = 1.0,1.0
        if(path['type'] ==  'vector') :
            lst = {}
            lst['type'] = 'vector'
            lst['data'] = []
            for subpath in path['data']:
                lst['data'].append(
                    [[subpath[0][1][0]*xs, subpath[0][1][1]*ys], 'move', 0, 0]
                )
                for i in range(1,len(subpath)):
                    sp1 = [  [subpath[i-1][j][0]*xs, subpath[i-1][j][1]*ys] for j in range(3)]
                    sp2 = [  [subpath[i  ][j][0]*xs, subpath[i  ][j][1]*ys] for j in range(3)]
                    lst['data'] += biarc(sp1,sp2,0,0)

                lst['data'].append(
                    [[subpath[-1][1][0]*xs, subpath[-1][1][1]*ys], 'end', 0, 0]
                )
            return lst
        # Raster image data, cut/burn left to right, drop down a line, repeat in reverse until completed.
        else:
            return path

    def check_dir(self):
        if not os.path.isdir(self.options.directory):
            inkex.errormsg(('Directory specified for output gcode does not exist! Please create it.'))
            return False
        return True

    # Turns a list of arguments into gcode-style parameters (eg (1, 2, 3) -> 'X1 Y2 Z3'),
    # taking scaling, offsets and the 'parametric curve' setting into account
    def make_args(self, c):
        c = [c[i] if i < len(c) else None for i in range(6)]
        while len(c) < 6:
            c.append(None)
        if c[5] == 0:
            c[5] = None

        m = [
                self.options.Xscale,
                -self.options.Yscale,
                1,
                self.options.Xscale,
                -self.options.Yscale,
                1
            ]
        a = [self.options.Xoffset, self.options.Yoffset, 0, 0, 0, 0]

        args = []
        for (i, axis) in enumerate(('X', 'Y', 'Z', 'I', 'J', 'K')):
            if c[i] is not None:
                value = self.unitScale*((c[i] * m[i]) + a[i])
                args.append('%s%.3f' % (axis,value))
        return ' '.join(args)

    def generate_gcode(self, curve):
        gcode = ''

        cwArc = 'G02'
        ccwArc = 'G03'

        # The 'laser on' and 'laser off' m-codes get appended to the GCODE generation
        lg = 'G00'
        firstGCode = False

        for i in range(1,len(curve['data'])):
            s, si = curve['data'][i-1], curve['data'][i]

            #G00 : Move with the laser off to a new point
            if s[1] == 'move':
                dist = 999
                if self.last_pos is not None:
                    dist = math.sqrt((si[0][0] - self.last_pos[0])**2 + (si[0][1] - self.last_pos[1])**2)
                if dist > 1.0: # don't bother with moves <1mm
                    # Pull up the pen if it was down previously.
                    if not gcode.endswith(PEN_UP):
                        gcode += PEN_UP
                        self.pen_is_down = False
                        gcode += '; PEN UP\n'
                    gcode += 'G00 ' + self.make_args(si[0]) + ' F12000\n'
                    lg = 'G00'
                    firstGCode = False

            elif s[1] == 'end':
                lg = 'G00'

            #G01 : Move with the laser turned on to a new point
            elif s[1] == 'line':
                if not firstGCode and not self.pen_is_down: #Include the ppm values for the first G01 command in the set.
                    gcode += PEN_DOWN + 'G01 ' + self.make_args(si[0]) +'\n'
                    gcode += '; PEN DOWN\n'
                    self.pen_is_down = True
                    firstGCode = True
                else:
                    gcode += 'G01 ' + self.make_args(si[0]) + '\n'
                lg = 'G01'

            #G02 and G03 : Move in an arc with the laser turned on.
            elif s[1] == 'arc':
                dx = s[2][0]-s[0][0]
                dy = s[2][1]-s[0][1]
                if abs((dx**2 + dy**2)*self.options.Xscale) > self.options.min_arc_radius:
                    r1 = P(s[0])-P(s[2])
                    r2 = P(si[0])-P(s[2])
                    if abs(r1.mag() - r2.mag()) < 0.001:
                        if not firstGCode and not self.pen_is_down:
                            gcode += PEN_DOWN
                            gcode += '; PEN DOWN\n'
                            self.pen_is_down = True

                        if (s[3] > 0):
                            gcode += cwArc
                        else:
                            gcode += ccwArc

                        gcode += ' ' + self.make_args(si[0] + [None, dx, dy, None]) + '\n'
                        firstGCode = True

                    else:
                        r = (r1.mag()+r2.mag())/2
                        if (s[3] > 0):
                            gcode += cwArc
                        else:
                            gcode += ccwArc

                        if not firstGCode and not self.pen_is_down: #Include the ppm values for the first G01 command in the set.
                            gcode += PEN_DOWN + self.make_args(si[0]) + ' R%f' % (r*self.options.Xscale) + 'S%.2f '
                            gcode += '; PEN DOWN\n'
                            self.pen_is_down = True
                            firstGCode = True
                        else:
                            gcode += ' ' + self.make_args(si[0]) + ' R%f' % (r*self.options.Xscale) + '\n'

                    lg = cwArc
                #The arc is less than the minimum arc radius, draw it as a straight line.
                else:
                    if not firstGCode and not self.pen_is_down: #Include the ppm values for the first G01 command in the set.
                        gcode += PEN_DOWN + 'G01 ' + self.make_args(si[0]) +'\n'
                        gcode += '; PEN DOWN\n'
                        self.pen_is_down = True
                        firstGCode = True
                    else:
                        gcode += 'G01 ' + self.make_args(si[0]) + '\n'

                    lg = 'G01'

            self.last_pos = si[0]

        return gcode

    ################################################################################
    ###
    ###        Curve to Gcode
    ###
    ################################################################################
    def compile_paths(self, parent, node, trans):
        # Apply the object transform, along with the parent transformation
        mat = node.get('transform', None)
        path = {}

        if mat:
            mat = simpletransform.parseTransform(mat)
            trans = simpletransform.composeTransform(trans, mat)

        if node.tag == SVG_PATH_TAG:
            # This is a path object
            if (not node.get('d')):
                return []
            csp = cubicsuperpath.parsePath(node.get('d'))

            path['type'] = 'vector'
            path['id'] = node.get('id')
            path['data'] = []

            if trans:
                simpletransform.applyTransformToPath(trans, csp)
                path['data'] = csp

            # flip vertically
            csp = path['data']
            simpletransform.applyTransformToPath(([1.0, 0.0, 0], [0.0, -1.0, 0]), csp)
            path['data'] = csp

            return path

        elif node.tag == SVG_GROUP_TAG:
            # This node is a group of other nodes
            pathsGroup = []
            for child in node.iterchildren():
                data = self.compile_paths(parent, child, trans)
                #inkex.errormsg(str(data))
                if type(data) is not list:
                    pathsGroup.append(data.copy())
                else:
                    pathsGroup += data
            return pathsGroup

        else :
            # Raster the results.
            if node.get('x') > 0:
                tmp = tempfile.gettempdir()
                bgcol = '#ffffff' #White
                curfile = curfile = self.args[-1] #The current inkscape project we're exporting from.
                command='inkscape --export-dpi 270 -i %s --export-id-only -e \'%stmpinkscapeexport.png\' -b \'%s\' %s' % (node.get('id'),tmp,bgcol,curfile)

                p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return_code = p.wait()
                f = p.stdout
                err = p.stderr

                # Fetch the image Data
                filename = '%stmpinkscapeexport.png' % (tmp)
                im = Image.open(filename).transpose(Image.FLIP_TOP_BOTTOM).convert('L')
                img = ImageOps.invert(im)

                # Get the image size
                imageDataWidth, imageDataheight = img.size

                # Compile the pixels.
                pixels = list(img.getdata())
                pixels = [pixels[i * (imageDataWidth):(i + 1) * (imageDataWidth)] for i in xrange(imageDataheight)]

                path['type'] = 'raster'
                path['width'] = imageDataWidth
                path['height'] = imageDataheight

                if not hasattr(parent, 'glob_nodePositions'):
                    # Get the XY position of all elements in the inkscape job.
                    command='inkscape -S %s' % (curfile)
                    p5 = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    dataString = str(p5.communicate()[0]).replace('\r', '').split('\n')
                    # Remove the final array element since the last item has a \r\n which creates a blank array element otherwise.
                    del dataString[-1]
                    elementList = dict((item.split(',',1)[0],item.split(',',1)[1]) for item in dataString)
                    parent.glob_nodePositions = elementList

                # Lookup the xy coords for this node.
                elementData = parent.glob_nodePositions[node.get('id')].split(',')
                x_position = float(elementData[0])
                y_position = float(elementData[1])*-1+self.pageHeight

                # Don't flip the y position.
                y_position = float(elementData[1])

                # Convert from pixels to mm
                path['x'] = float(str('%.3f') % (self.unitScale * x_position))
                path['y'] = float(str('%.3f') % (self.unitScale * y_position))

                # Do not permit being < 0
                path['x'] = max(path['x'], 0)
                path['y'] = max(path['y'], 0)

                path['id'] = node.get('id')
                path['data'] = pixels

                return path
            else:
                inkex.errormsg('Unable to generate raster for object ' + str(node.get('id'))+' as it does not have an x-y coordinate associated.')

        inkex.errormsg('skipping node ' + str(node.get('id')))
        self.skipped += 1
        return []

    def get_gcode_extents(self, gcode):
        extent = [None, None, None, None]
        for line in gcode.split('\n'):
            line_parts = line.split(' ')
            if line_parts[0] not in ('G00', 'G01'):
                continue
            for line_part in line_parts[1:]:
                m = self.RE_COORD.match(line_part)
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

    def translate_gcode(self, gcode, x_offset, y_offset):
        out = ''
        for line in gcode.split('\n'):
            for (i, line_part) in enumerate(line.split(' ')):
                if i > 0:
                    out += ' '
                m = self.RE_COORD.match(line_part)
                if m is None:
                    out += line_part
                else:
                    offset = x_offset
                    if m.group(1) == 'Y':
                        offset = y_offset
                    out += m.group(1)
                    out += '{:.3f}'.format(float(m.group(2)) + offset)
            out += '\n'
        return out

    def effect(self):
        global options
        options = self.options
        selected = self.selected.values()

        root = self.document.getroot()

        # check if the user has the document setup in mm or pixels.
        try:
            self.pageHeight = float(root.get('height', None))
        except:
            inkex.errormsg(('Please change your inkscape project units to be in pixels, not inches or mm. In Inkscape press ctrl+shift+d and change \'units\' on the page tab to px. The option \'default units\' can be set to mm or inch, these are the units displayed on your rulers.'))
            return

        logger.info('4xiDraw export script started')
        logger.info('output directory: %s' % self.options.directory)

        if len(selected)<=0:
            inkex.errormsg('This extension requires at least one selected path.')
            return

        dirExists = self.check_dir()
        if (not dirExists):
            return

        gcode = ''

        # use millimeters
        self.unitScale = 0.282222222222

        selected = list(selected)

        # Recursively compiles a list of paths that are decendant from the given node
        self.skipped = 0

        # Compile a list of layers in this document. We compile a list of only the layers
        # we need to use, so we can know ahead of time whether to put tool change
        # operations between them.
        layers = []
        for layer in reversed(get_layers(self.document)):
            for node in layer.iterchildren():
                if (node in selected):
                    layers.append(layer)
                    break

        layers = list(reversed(get_layers(self.document)))

        # Loop over the layers and objects
        gcode_output = {}
        for layer in layers:
            gcode = ''
            gcode_raster = ''

            logger.info('layer: %s' % layer.attrib['id'])

            gcode += '; STARTING LAYER %s\n' % layer.attrib['id']

            pathList = []

            # Apply the layer transform to all objects within the layer
            trans = layer.get('transform', None)
            trans = simpletransform.parseTransform(trans)

            for node in layer.iterchildren():
                if (node in selected):
                    # Vector path data, cut from x to y in a line or curve
                    logger.info('node %s' % str(node.tag))
                    selected.remove(node)

                    try:
                        newPath = self.compile_paths(self, node, trans).copy()
                        pathList.append(newPath)
                        inkex.errormsg('Built gcode for '+str(node.get('id'))+' - will be cut as %s.' % (newPath['type']) )
                    except:
                        for objectData in self.compile_paths(self, node, trans):
                            inkex.errormsg('Built gcode for group '+str(node.get('id'))+', item %s - will be cut as %s.' % (objectData['id'], objectData['type']) )
                            pathList.append(objectData)
                else:
                    logger.info('skipping node %s' % node)

            if (not pathList):
                logger.info('no objects in layer')
                continue

            # reorder paths
            left_most = pathList[0]
            for path in pathList:
                if path['data'][0][0][0] < left_most['data'][0][0][0]:
                    left_most = path
            pathList.remove(path)
            ordered_path_list = [left_most]
            while len(pathList) > 0:
                last_path = ordered_path_list[-1]
                min_dist = None
                closest_path = None
                needs_reverse = False
                for path in pathList:
                    d = distance_between_paths(last_path, path)
                    rev_d = distance_between_paths(last_path, path, reverse=True)
                    if min_dist is None or d < min_dist or rev_d < min_dist:
                        if rev_d < d:
                            needs_reverse = True
                            min_dist = rev_d
                        else:
                            needs_reverse = False
                            min_dist = d
                        closest_path = path
                if needs_reverse:
                    ordered_path_list.append(reverse_path(closest_path))
                else:
                    ordered_path_list.append(closest_path)
                pathList.remove(closest_path)

            logger.info('found %d paths in layer %s' % (len(ordered_path_list), layer.attrib['id']))

            # Fetch the vector or raster data and turn it into GCode
            for (i, objectData) in enumerate(ordered_path_list):
                curve = self.parse_curve(objectData)
                header_data = ''

                # always put the pen up at the start of the layer
                if i == 0:
                    header_data += PEN_UP
                    self.pen_is_down = False
                else:
                    # only bother putting the pen up for the gap between
                    # paths that are >1mm from each other
                    if distance_between_paths(ordered_path_list[i-1], objectData) > 1:
                        header_data += PEN_UP
                        self.pen_is_down = False

                # Generate the gcode for this layer
                if curve['type'] == 'vector':
                    gcode += header_data + self.generate_gcode(curve)
                elif curve['type'] == 'raster':
                    gcode_raster += header_data + self.generate_raster_gcode(curve)

            gcode += PEN_UP
            self.pen_is_down = False
            gcode += '; ORDERED PATH LIST END / PEN UP\n'

            gcode_output[layer.attrib['id']] = '\n\n'.join(['G21 ; All units in mm', gcode_raster, gcode])

        # calculate origin offset for generated gcode
        extents = None
        for layer_id in gcode_output:
            file_extents = self.get_gcode_extents(gcode_output[layer_id])
            if extents is None:
                extents = file_extents
            else:
                for i in range(0, 4):
                    compare = i < 2 and min or max
                    extents[i] = compare(file_extents[i], extents[i])

        logger.info('extents: %s' % str(extents))

        # translate gcode by shared offset, write file(s)
        for layer_id in gcode_output:
            try:
                fn = os.path.normpath('%s/%s.%s' % (self.options.directory, layer_id, GCODE_EXTENSION))
                with open(fn, 'w') as f:
                    f.write(self.translate_gcode(gcode_output[layer_id], -1 * extents[0], -1 * extents[1]))
            except:
                inkex.errormsg('Cannot write to %s file.' % fn)
                return

        if (self.skipped > 0):
            inkex.errormsg('Warning: skipped %d object(s) because they were not paths (Vectors) or images (Raster). Please convert them to paths using the menu \'Path->Object To Path\'' % self.skipped)

e = Gcode_tools()
e.affect()
inkex.errormsg('Finished processing.')
