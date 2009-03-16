from __future__ import with_statement

from svg_paths import linearize_path

from xml.dom import minidom, Node

UP = object()
DOWN = object()

def node_iter(node):
    yield node
    yield DOWN
    for child in node.childNodes:
        for cn in node_iter(child):
            yield cn
    yield UP

def element_iter(dom):
    for n in node_iter(dom):
        if n in [UP, DOWN] or n.nodeType == Node.ELEMENT_NODE:
            yield n

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
    t = e.getAttribute('transform')
    if t.startswith('translate'):
        print t
    return [1, 0, 0, 0, 1, 0]

def do_transform(t, ps):
    a, b, c, d, e, f = t
    return [(a * p[0] + c * p[1] + e, 
             b * p[0] + d * p[1] + f)
            for p in ps]

#http://math.univ-lille1.fr/~barraud/Inkscape/pathdeform/simpletransform.py
#http://www.w3.org/TR/SVG/coords.html
#http://apike.ca/prog_svg_transform.html


MULTISHAPE = object()

def get_body(height, e):
    if e.nodeName == 'rect':
        id, label, sd = shape_common(e)
        x, y, w, h = [float(e.getAttribute(n)) for n in ['x', 'y', 'width', 'height']]
        return 'rect', id, label, sd, ((x, height - y - h), (w, h))
    if e.nodeName == 'path':
        if e.getAttribute('sodipodi:type') == 'arc':
            id, label, sd = shape_common(e)
            x, y, rx, ry = [float(e.getAttribute('sodipodi:'+n))
                            for n in ['cx', 'cy', 'rx', 'ry']]
            transform = get_transform(e)
            return 'circle', id, label, sd, ((x, height-y), (rx, ry))
        else:
            id, label, sd = shape_common(e)
            path = e.getAttribute('d')
            path = linearize_path(path)
            points = [tuple(map(float, e.split(',')))
                      for e in path.split() if len(e) > 1]
            points = [(x, height - y) for x, y in points]
            name = 'polygon' if path.split()[-1] == 'z' else 'path'
            return name, id, label, sd, points

def body_iter(height, es):
    #level = 0
    for e in es:
        if e in [UP, DOWN]:
            yield e
        else:
            if e.nodeName == 'g':
                if 'multishape' in label_dict(e):
                    id, label = element_common(e)
                    yield MULTISHAPE, id, label
                    # Update matrix & z-value
            else:
                b = get_body(height, e)
                if b:
                    yield b

def just_bodies(height, es):
    #return (body for body in body_iter(height, es))
    bi = body_iter(height, es)
    for body in bi:
        if body in [UP, DOWN]:
            pass
        elif body[0] == MULTISHAPE:
            _, id, label = body
            subshapes = []
            level = 0
            while True:
                e = bi.next()
                if e is DOWN:
                    level += 1
                elif e is UP:
                    level -= 1
                    if level == 0:
                        break
                else:
                    type, sub_id, sub_label, sd, geometry = e
                    # Is this a good thing? id and label is lost!
                    subshapes.append((type, sub_id, sub_label, sd, geometry))
            yield id, label, subshapes
        else:
            type, id, label, sd, geometry = body
            yield id, label, [(type, id, label, sd, geometry)]

def read_level(file):
    dom = minidom.parse(file)
    i = element_iter(dom)
    svg_node = DOWN
    while svg_node in [UP, DOWN]:
        svg_node = i.next()
    header = dict(width=float(svg_node.getAttribute('width')), 
                  height=float(svg_node.getAttribute('height')))
    return header, just_bodies(header['height'], i)

def main(argv):
    import pprint
    with open(argv[1]) as f:
        header, bodies = read_level(f)
    pprint.pprint(header)
    print
    for b in bodies:
        pprint.pprint(b)

if __name__ == '__main__':
    import sys
    main(sys.argv)