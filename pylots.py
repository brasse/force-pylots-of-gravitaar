from __future__ import with_statement

import misc
from iterable_level_loader import read_level

import math
import pickle
import sys
from collections import defaultdict
from contextlib import nested
from optparse import OptionParser

from Box2D import *
import pyglet
from pyglet.gl import *

def parse_hex_color(s):
    s = s[1:]
    return tuple(int(s[i:i+2], 16)/255.0 for i in xrange(0, 6, 2))

class ContactListener(b2ContactListener):
    def __init__(self, collectible_callback, ship_death_callback):
        super(ContactListener, self).__init__()
        self.collectible = collectible_callback
        self.ship_death = ship_death_callback

    @staticmethod
    def get_body(body1, body2, type):
        if body1.GetUserData()['type'] == type:
            return body1
        assert(body2.GetUserData()['type'] == type)
        return body2
    
    def Add(self, point):
        b1 = point.shape1.GetBody()
        b2 = point.shape2.GetBody()
        type_pair = set([b1.GetUserData()['type'],
                         b2.GetUserData()['type']])
        if type_pair == set(['ship', 'collectible']):
            self.collectible(self.get_body(b1, b2, 'collectible'))
        elif type_pair == set(['ship', 'terminal']):
            self.ship_death()

    def Persist(self, point):
        pass

    def Remove(self, point):
        pass

    def Result(self, point):
        pass

class Ship(object):
    def __init__(self, body):
        self.body = body
        self.turn_speed = 2
        local_mass_center_x, _ = body.GetLocalCenter().tuple()
        self.acceleration_force = (local_mass_center_x, 1500)
        self.thrust = False
        self.turn_direction = 0

    @property
    def position(self):
        return self.body.GetWorldCenter().tuple()
    
    @property
    def velocity(self):
        return self.body.GetLinearVelocity().tuple()

    def apply_controls(self):
        self.apply_thrust()
        self.apply_turn()

    def apply_thrust(self):
        if self.thrust:
            f = self.body.GetWorldVector(self.acceleration_force)
            p = self.body.GetWorldCenter()
            self.body.ApplyForce(f, p)

    def apply_turn(self):
        self.body.SetAngularVelocity(self.turn_speed * self.turn_direction)

class Sim(object):
    def __init__(self, width, height):
        self.time_step = 1.0 / 60.0
        self.total_time = 0.0
        self.thrust = False
        self.turn_direction = 0
        self.collectibles = set()
        self.remove_body_list = set()
        self.game_over = False

        worldAABB = b2AABB()
        worldAABB.lowerBound.Set(0, 0)
        worldAABB.upperBound.Set(width, height)
        gravity = b2Vec2(0, -5)
        doSleep = True
        self.world = b2World(worldAABB, gravity, doSleep)
        self.contact_listener = ContactListener(self.collect, self.ship_death)
        self.world.SetContactListener(self.contact_listener)

    def set_ship_body(self, body):
        body.GetUserData()['type'] = 'ship'
        self.ship = Ship(body)

    def add_object(self, body_data):
        type, id, label, style, geometry = body_data

        if type == 'rect':
            (left, lower), (width, height) = geometry
            shape_def = b2PolygonDef()
            shape_def.SetAsBox(width / 2, height / 2)
            position = (left + width / 2, lower + height / 2)
        elif type == 'polygon':
            vertices = geometry[:-1] # Remove final point
            shape_def = b2PolygonDef()
            shape_def.setVertices(vertices)
            position = (0, 0)
        elif type == 'circle':
            position, (rx, ry) = geometry
            if rx != ry:
                raise Exception('Cannot handle ovals')
            shape_def = b2CircleDef()
            shape_def.radius = rx
            shape_def.position = position
        elif type == 'path':
            vertices = geometry
            shape_def = b2EdgeChainDef()
            if 'flip' in label:
                shape_def.setVertices(list(reversed(vertices)))
            else:
                shape_def.setVertices(vertices)                
            shape_def.isALoop = False
            position = (0, 0)
            style['fill'] = style['stroke']
        else:
            return

        color = parse_hex_color(style['fill'])
        density = float(label.get('density', '0.0'))

        def get_object_type():
            types = ['collectible', 'terminal']
            for t in types:
                if t in label:
                    return t
            return None
        object_type = get_object_type()

        bodyDef = b2BodyDef()
        bodyDef.position.Set(*position)
        body = self.world.CreateBody(bodyDef)

        if object_type == 'collectible':
            shape_def.isSensor = True
            self.collectibles.add(body)

        shape_def.density = density
        body.CreateShape(shape_def)
        body.SetMassFromShapes()
        body.SetUserData(defaultdict(lambda: None,
                                     color=color, type=object_type))
        return body

    def collect(self, body):
        self.remove_body_list.add(body)
        self.collectibles.discard(body)

    def ship_death(self):
        self.game_over = True

    def step(self):
        self.total_time += self.time_step
        self.ship.apply_controls()
        vel_iters, pos_iters = 10, 8
        self.world.Step(self.time_step, vel_iters, pos_iters)
        for body in self.remove_body_list:
            self.world.DestroyBody(body)
        self.remove_body_list = set()
        if len(self.collectibles) == 0 or self.game_over:
            pyglet.app.exit()

def draw_world(world):
    def draw_shape(shape):
        def draw_circle(shape):
            circle = shape.asCircle()
            glBegin(GL_TRIANGLE_FAN)
            steps = 100
            radius = circle.GetRadius()
            for i in xrange(steps + 1):
                f = i / float(steps) * 2 * math.pi
                glVertex2f(math.cos(f) * radius, math.sin(f) * radius)
            glEnd()

        def draw_polygon(shape):
            polygon = shape.asPolygon()
            glBegin(GL_TRIANGLE_FAN)
            vertices = polygon.getVertices_tuple()
            for x, y in vertices:
                glVertex2f(x, y)
            glEnd()

        def draw_edge(shape):
            # An edge chain that is a loop will cause this code to hang.
            edge = shape.asEdge()
            glBegin(GL_LINES)
            while edge:
                glVertex2f(*edge.GetVertex1().tuple())
                glVertex2f(*edge.GetVertex2().tuple())
                edge = edge.GetNextEdge()
            glEnd()

        draw_function = \
            {
                e_polygonShape: draw_polygon,
                e_circleShape: draw_circle,
                e_edgeShape: draw_edge,
            }
        draw_function[shape.GetType()](shape)

    for body in world:
        x, y = body.GetPosition().tuple()
        angle = body.GetAngle()
        body_data = body.GetUserData()
        glPushMatrix()
        glTranslatef(x, y, 0.0)
        glRotatef(math.degrees(angle), 0.0, 0.0, 1.0)
        color = body_data['color'] if body_data else (1.0, 1.0, 1.0)
        glColor3f(*color)
        for shape in body:
            draw_shape(shape)
        glPopMatrix()

class SimWindow(pyglet.window.Window):
    WINDOW_SIDE = 400
 
    def __init__(self, sim, viewport, log_stream=None, replay_stream=None):
        pyglet.window.Window.__init__(self,
                                      width=self.WINDOW_SIDE,
                                      height=self.WINDOW_SIDE,
                                      caption='sim')
        self.sim = sim
        self.log_stream = log_stream
        self.replay_stream = replay_stream
        self.time = 0
        #self.camera_position = sim.ship.position
        (x, y), (w, h) = viewport
        self.camera_position = (x + w/2, y + h/2)
        self.viewport_model_height = h
        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

    def on_resize(self, width, height):
        glViewport(0, 0, width, height)

    def update(self, dt):
        self.time += dt
        while self.time > self.sim.time_step:
            self.time -= self.sim.time_step
            if self.replay_stream:
                thrust, turn_direction = pickle.load(self.replay_stream)
                self.sim.ship.thrust = thrust
                self.sim.ship.turn_direction = turn_direction
            if self.log_stream:
                pickle.dump((self.sim.ship.thrust,
                             self.sim.ship.turn_direction), self.log_stream)
            self.sim.step()

    def update_camera_position(self):
        max_distance = self.viewport_model_height/6
        new_camera = []
        ship = self.sim.ship
        for cam, ship in zip(self.camera_position, ship.position):
            distance = ship - cam
            if distance > max_distance:
                cam += (distance - max_distance)
            elif distance < -max_distance:
                cam += (distance + max_distance)
            new_camera.append(cam)
        self.camera_position = tuple(new_camera)
        
    def on_draw(self):
        self.update_camera_position()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(self.camera_position[0] - self.viewport_model_height/2,
                self.camera_position[0] + self.viewport_model_height/2,
                self.camera_position[1] - self.viewport_model_height/2,
                self.camera_position[1] + self.viewport_model_height/2,
                -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW)

        glClearColor(0.3, 0.3, 0.4, 1.0)
        self.clear()
        draw_world(self.sim.world)

    def on_key_press(self, symbol, modifiers):
        # If not in replay, respond to ship controls.
        if not self.replay_stream:
            if symbol == pyglet.window.key.UP:
                self.sim.ship.thrust = True
            elif symbol == pyglet.window.key.LEFT:
                self.sim.ship.turn_direction = 1
            elif symbol == pyglet.window.key.RIGHT:
                self.sim.ship.turn_direction = -1

    def on_key_release(self, symbol, modifiers):
        # If not in replay, respond to ship controls.
        if not self.replay_stream:
            if symbol == pyglet.window.key.UP:
                self.sim.ship.thrust = False
            elif symbol in [pyglet.window.key.LEFT, pyglet.window.key.RIGHT]:
                self.sim.ship.turn_direction = 0

def make_sim(file):
    header, bodies = read_level(file)
    sim = Sim(header['width'], header['height'])
    for body in bodies:
        body_id = body[1]
        if body_id == 'viewport':
            viewport = body[4]
        else:
            added = sim.add_object(body)
            if body_id == 'ship':
                sim.set_ship_body(added)
    return sim, viewport

def main():
    parser = OptionParser()
    parser.add_option('-l', '--log', dest='log_file', metavar='FILE', 
                      help='Write log to FILE.')
    parser.add_option('-r', '--replay', dest='replay_file', metavar='FILE', 
                      help='Replay moves from FILE.')
    options, args = parser.parse_args()

    sim, viewport = make_sim('level0.svg')
    
    with nested(misc.open(options.log_file, 'w'),
                misc.open(options.replay_file)) as (log, replay):
        window = SimWindow(sim, viewport, 
                           log_stream=log, replay_stream=replay)
        pyglet.app.run()

    if window.sim.game_over:
        print 'GAME OVER'
    else:
        print window.sim.total_time

if __name__ == '__main__':
    main()
