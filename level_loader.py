from __future__ import with_statement

from svg_paths import linearize_path, path_area, reverse_path, path_points, triangulate_path, split_paths

import copy
import re
from contextlib import nested
from xml.dom import minidom, Node

# Utils

class LabelStack(object):
    def __init__(self):
        self.stack = [{}]

    def push(self, label):
        self.stack.append(copy.copy(self.stack[-1]))
        self.stack[-1].update(label)
        return self

    def pop(self):
        self.stack.pop()

    def __call__(self):
        return self.stack[-1]

    def __enter__(self):
        return self
    
    def __exit__(self, *exc_info):
        self.pop()

class Transform(object):
    def __init__(self, height):
        self.height = height
        self.stack = [(0.0, 0.0)]

    def push(self):
        self.stack.append(self.stack[-1])

    def pop(self):
        self.stack.pop()

    def translate(self, t):
        self.push()
        x0, y0 = self.stack[-1]
        x, y = t
        self.stack[-1] = x0 + x, y0 + y
        return self

    def __call__(self, p):
        x, y = p
        tx, ty = self.stack[-1]
        return x + tx, self.height - (y + ty)

    def __enter__(self):
        return self
    
    def __exit__(self, *exc_info):
        self.pop()

def str_to_dict(s, pair_sep=';', key_value_sep=':'):
    def true_tuple(k, v=True):
        return (k, v)
    return dict(true_tuple(*attr.split(key_value_sep)) 
                for attr in s.split(pair_sep) if attr != '')

def label_dict(e):
    label = e.getAttribute('inkscape:label')
    label = str_to_dict(label, ' ', '=')
    return label

def element_common(e):
    id = e.getAttribute('id')
    label = label_dict(e)
    return id, label

def shape_common(e):
    #id = e.getAttribute('id')
    #label = label_dict(e)
    id, label = element_common(e)
    sd = str_to_dict(e.getAttribute('style'))
    return id, label, sd

def get_transform(e):
    t_attr = e.getAttribute('transform')
    re_translate = r'translate\((.+),(.+)\)'
    m = re.match(re_translate, t_attr)
    if m:
        return float(m.group(1)), float(m.group(2))
    else:
        return 0.0, 0.0
        
def get_winning_condition(node):
    wc_attr = node.getAttribute('winning_condition')
    return [signal.strip() for signal in wc_attr.split(',') if signal != '']
  
# Node handlers

def handle_node_g(node, header, bodies, transform, label):
    id, l = element_common(node)
    t = get_transform(node)
    with nested(label.push(l), transform.translate(t)):
        if 'multishape' in label():
            mbodies = []
            parse_children(node, header, mbodies, transform, label)
            bodies.append((id, label(),
                           [shapes[0] for _, _, shapes in mbodies]))
        else:
            parse_children(node, header, bodies, transform, label)

def handle_node_svg(node, header, bodies, transform, label):
    header.update(width=float(node.getAttribute('width')), 
                  height=float(node.getAttribute('height')),
                  winning_condition=get_winning_condition(node))
    transform = Transform(header['height'])
    parse_children(node, header, bodies, transform, label)

def handle_node_namedview(node, header, bodies, transform, label):
    bodies.append(('pagecolor', node.getAttribute('pagecolor')))
    parse_children(node, header, bodies, transform, label)

def handle_node_rect(node, header, bodies, transform, label):
    id, l, sd = shape_common(node)
    with label.push(l):
        x, y, w, h = [float(node.getAttribute(n))
                      for n in ['x', 'y', 'width', 'height']]
        bodies.append((id, label(), [('rect', id, label(), sd,
                                      (transform((x, y + h)), (w, h)))]))

def handle_node_path(node, header, bodies, transform, label):
    id, l, sd = shape_common(node)
    t = get_transform(node)
    with nested(label.push(l), transform.translate(t)):
        if node.getAttribute('sodipodi:type') == 'arc':
            x, y, rx, ry = [float(node.getAttribute('sodipodi:'+n))
                            for n in ['cx', 'cy', 'rx', 'ry']]
            bodies.append((id, label(), [('circle', id, label(), sd,
                                          (transform((x, y)), (rx, ry)))]))
        else:
            path = node.getAttribute('d')
            path = linearize_path(path)
            # Make sure that closed paths are defined counter clockwise
            if path.split()[-1] == 'z' and path_area(path) > 0.0:
                path = reverse_path(path)
            is_polygon = path.split()[-1] == 'z'
            name = 'polygon' if is_polygon else 'path'
            if is_polygon and 'triangulate' in label():
                convex_path = triangulate_path(path)
                paths = split_paths(convex_path)
            else:
                paths = [path]
            parts = []
            for path in paths:
                points = path_points(path)
                points = [transform((x,y)) for x, y in points]
                parts.append((name, id, label(), sd, points))
            bodies.append((id, label(), parts))

def handle_node_default(node, header, bodies, transform, label):
    parse_children(node, header, bodies, transform, label)

# Level parser

def parse_children(node, header, bodies, transform, label):
    for child in node.childNodes:
        parse_subtree(child, header, bodies, transform, label)

def parse_subtree(node, header, bodies, transform, label):
    handlers = {
            'g': handle_node_g, 
            'svg': handle_node_svg, 
            'path': handle_node_path, 
            'rect': handle_node_rect, 
            'sodipodi:namedview': handle_node_namedview
            }
    handlers.get(node.nodeName, handle_node_default)(node, header,
                                                     bodies, transform, label)

def read_level(file):
    root = minidom.parse(file)
    header = {}
    bodies = []
    label = LabelStack()

    parse_subtree(root, header, bodies, None, label)
    
    return header, bodies


def main(argv):
    import pprint
    with open(argv[1]) as f:
        header, bodies = read_level(f)
    pprint.pprint(header)
    pprint.pprint(list(bodies))


if __name__ == '__main__':
    import sys
    main(sys.argv)
