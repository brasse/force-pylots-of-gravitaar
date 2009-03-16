
import re

def main():
    path = "M 262.85714,266.6479 C 339.86994,315.42528 317.14286,172.36218 411.42857,258.07647"
    path = 'M 23.128643,300.00104 L 74.827962,315.64688 C 74.827962,315.64688 79.589741,238.77816 103.39864,277.55265 C 127.20754,316.32714 127.88779,357.14239 157.81897,274.15138'
    path = 'M 469.3754,192.52087 L 519.03396,139.46104 C 519.03396,139.46104 575.49506,120.41392 567.33201,182.99731 C 559.16895,245.5807 488.42252,244.90044 488.42252,244.90044 L 455.09006,228.57434 C 455.09006,228.57434 463.25311,220.41129 469.3754,192.52087 z'
    path = 'M 92.099638,57.108572 C 92.099638,57.108572 96.525478,51.628959 102.4266,51.418205 C 108.32772,51.207451 107.90621,58.162343 113.80733,58.373097 C 119.70845,58.583852 131.29994,54.790274 134.88276,60.902149 C 138.46559,67.014025 142.04841,75.444197 133.82899,80.713055 C 125.60957,85.981913 120.55147,69.332322 113.80733,72.704391 C 107.06319,76.07646 108.74923,83.663616 102.21584,80.291547 C 95.682461,76.919478 79.454378,67.435533 79.454378,67.435533'
    print linearize_path(path)

def linearize_path(path):
    """
    Creates a path with only M and L. 
    In path can contain M, L and C. 
    """
    new_path = []
    for type, cs in get_path(path):
        if type == 'M':
            last_p = cs.next()
            new_path.append('M %f,%f' % (last_p))
        elif type == 'L':
            last_p = cs.next()
            new_path.append('L %f,%f' % (last_p))
        elif type == 'C':
            control_points = [last_p] + list(cs)
            for p in bezier_points(control_points):
                new_path.append('L %f,%f' % (p))
            last_p = control_points[-1]
        elif type == 'z':
            new_path.append('z')
    return ' '.join(new_path)

def bezier_points(p, steps = 10):
    class SimpleVector(object):
        def __init__(self, x, y):
            self.x = x
            self.y = y

        def __add__(self, other):
            return self.__class__(self.x + other.x, self.y + other.y)

        def __sub__(self, other):
            return self.__class__(self.x - other.x, self.y - other.y)

        def __mul__(self, k):
            return self.__class__(k * self.x, k * self.y)

        def __iadd__(self, other):
            self.x += other.x
            self.y += other.y
            return self

        def __isub__(self, other):
            self.x -= other.x
            self.y -= other.y
            return self

        __rmul__ = __mul__
    
    def bezier_iter(p, steps):
        """
        http://www.niksula.cs.hut.fi/~hkankaan/Homepages/bezierfast.html
        """
        t = 1.0 / steps
        t2 = t*t
    
        p0, p1, p2, p3 = p
        f = p0
        fd = 3 * (p1 - p0) * t
        fdd_per_2 = 3 * (p0 - 2 * p1 + p2) * t2
        fddd_per_2 = 3 * (3 * (p1 - p2) + p3 - p0) * t2 * t
    
        fddd = fddd_per_2 + fddd_per_2
        fdd = fdd_per_2 + fdd_per_2
        fddd_per_6 = fddd_per_2 * (1.0 / 3)
    
        for x in xrange(steps):
            f += fd + fdd_per_2 + fddd_per_6
            yield f
            fd += fdd + fddd_per_2
            fdd += fddd
            fdd_per_2 += fddd_per_2

    p = [SimpleVector(*t) for t in p]
    return ((p.x, p.y) for p in bezier_iter(p, steps))

def get_path(path):
    regex = re.compile('([MLCz])([-\d., ]*)')
    return ((match.group(1),
            (tuple(float(c) for c in p.split(','))
             for p in match.group(2).split()))
             for match in regex.finditer(path))

def split_paths(path):
    return ['M%s' % p for p in s.split('M')[1:]]

def reverse_path(path):
    new_type = 'M'
    closed = False
    new_path = []
    for type, cs in reversed(list(get_path(path))):
        if type == 'z':
            closed = True
        else:
            x, y = cs.next()
            new_path.append('%s %f,%f' % (new_type, x, y))
            new_type = 'L'
    if closed:
        new_path.append('z')
    return ' '.join(new_path)


def path_area(path):
    """
    http://local.wasp.uwa.edu.au/~pbourke/geometry/clockwise/
    """
    a = 0
    for type, cs in get_path(path):
        if type == 'M':
            last_p = cs.next()
        elif type == 'L':
            p = cs.next()
            lx, ly = last_p
            x, y = p
            a += lx * y - x * ly
            last_p = p
        elif type == 'z':
            pass
        else:
            assert False
    return a / 2.0


if __name__ == '__main__':
    main()
