from __future__ import with_statement

import misc
from level_loader import read_level

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
    if s == 'none':
        return None
    s = s[1:]
    return tuple(int(s[i:i+2], 16)/255.0 for i in xrange(0, 6, 2))

class ContactListener(b2ContactListener):
    def __init__(self, signal_callback):
        super(ContactListener, self).__init__()
        self.signal = signal_callback
        self.ship = None

    def get_ship_collider(self, body1, body2):
        if body1 == self.ship:
            return body2
        elif body2 == self.ship:
            return body1
        else:
            return None
        
    def Add(self, point):
        b1 = point.shape1.GetBody()
        b2 = point.shape2.GetBody()

        # Signals
        c = self.get_ship_collider(b1, b2)
        if c:
            data = c.GetUserData()
            signal = data['ship_triggers']
            if signal:
                self.signal(signal)

        for b in [b1, b2]:
            data = b.GetUserData()
            signal = data['triggers']
            if signal:
                self.signal(signal)

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
    GAME_OVER = object()
    LEVEL_COMPLETED = object()

    def __init__(self, width, height, winning_condition, is_ghost=False):
        self.winning_condition = winning_condition
        self.is_ghost = is_ghost
        self.time_step = 1.0 / 60.0
        self.steps_taken = 0
        self.thrust = False
        self.turn_direction = 0
        self.accumulated_signals = set()
        self.signal_listeners = defaultdict(list)
        self.game_end_status = None

        worldAABB = b2AABB()
        worldAABB.lowerBound.Set(0, 0)
        worldAABB.upperBound.Set(width, height)
        gravity = b2Vec2(0, -5)
        doSleep = True
        self.world = b2World(worldAABB, gravity, doSleep)
        self.contact_listener = ContactListener(self.signal)
        self.world.SetContactListener(self.contact_listener)

    def set_ship_body(self, body):
        self.ship = Ship(body)
        self.contact_listener.ship = body

    def add_shape(self, body, shape_data):
        type, id, label, style, geometry = shape_data
        if type == 'rect':
            (left, lower), (width, height) = geometry
            shape_def = b2PolygonDef()
            position = (left + width / 2, lower + height / 2)
            shape_def.SetAsBox(width / 2, height / 2, position, 0)
        elif type == 'polygon':
            vertices = geometry[:-1] # Remove final point
            shape_def = b2PolygonDef()
            shape_def.setVertices(vertices)
        elif type == 'circle':
            position, (rx, ry) = geometry
            if rx != ry:
                raise Exception('Cannot handle ovals')
            shape_def = b2CircleDef()
            shape_def.radius = rx
            shape_def.localPosition = position
        elif type == 'path':
            vertices = geometry
            shape_def = b2EdgeChainDef()
            if 'flip' in label:
                shape_def.setVertices(list(reversed(vertices)))
            else:
                shape_def.setVertices(vertices)                
            shape_def.isALoop = False
            style['fill'] = style['stroke']
        else:
            return None

        color = parse_hex_color(style['fill'])
        if not color:
            return None

        shape_def.density = float(label.get('density', shape_def.density))
        shape_def.friction = float(label.get('friction', shape_def.friction))
        shape_def.restitution = float(label.get('restitution',
                                                shape_def.restitution))
        if 'sensor' in label:
            shape_def.isSensor = True            
        shape_def.SetUserData(dict(color=color))
        body.CreateShape(shape_def)
        return color

    def signal(self, signal):
        self.emitted_signals.add(signal)
        self.accumulated_signals.add(signal)
        
    def set_up_listeners(self, body, label):
        slots = ['destroyed_by', 'created_by']
        for slot in slots:
            if slot in label:
                self.signal_listeners[label[slot]].append((slot, body))

    def handle_emitted_signals(self):
        for signal in self.emitted_signals:
            listener_list = self.signal_listeners[signal]
            for e in listener_list[:]:
                action, listener = e
                if action == 'destroyed_by':
                    listener_list.remove(e)
                    self.world.DestroyBody(listener)
                elif action == 'created_by':
                    label = listener[1]
                    # If we do not remove the created_by attribute from label,
                    # this object will not be creted by add_object().
                    del label['created_by']
                    listener_list.remove(e)
                    self.add_object(listener)

    def check_game_end_condition(self):
        if 'game_over' in self.accumulated_signals:
            self.game_end_status = self.GAME_OVER
            pyglet.app.exit()
        elif self.winning_condition.issubset(self.accumulated_signals):
            self.game_end_status = self.LEVEL_COMPLETED
            pyglet.app.exit()

    def add_object(self, body_data):
        id, label, shapes = body_data

        if 'created_by' in label:
            # This body should not created now. It will be created when
            # its creation signal is emitted.
            self.set_up_listeners(body_data, label)
            return None

        bodyDef = b2BodyDef()
        body = self.world.CreateBody(bodyDef)
        self.set_up_listeners(body, label)

        for shape in shapes:
            self.add_shape(body, shape)

        body.SetMassFromShapes()
        body.SetUserData(defaultdict(lambda: None, id=id,
                                     triggers=label.get('triggers', None),
                                     ship_triggers=label.get('ship_triggers',
                                                             None)))
        
        return body

    def step(self):
        self.steps_taken += 1
        self.ship.apply_controls()
        self.emitted_signals = set()
        vel_iters, pos_iters = 10, 8
        self.world.Step(self.time_step, vel_iters, pos_iters)
        self.handle_emitted_signals()
        if not self.is_ghost:
            self.check_game_end_condition()
        
def draw_world(world, color_transform=lambda x:x):
    def draw_shape(shape):
        def draw_circle(shape):
            circle = shape.asCircle()
            x, y = circle.GetLocalPosition().tuple()
            glTranslatef(x, y, 0.0)
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
            edge = shape.asEdge()
            glBegin(GL_LINES)
            glVertex2f(*edge.GetVertex1().tuple())
            glVertex2f(*edge.GetVertex2().tuple())
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
        for shape in body:
            color = shape.GetUserData()['color']
            glColor3f(*color_transform(color))
#            glColor3f(*(c * color_damping for c in color))
            draw_shape(shape)
        glPopMatrix()

class SimWindow(pyglet.window.Window):
    WINDOW_SIDE = 400
    GHOST_COLOR_DAMPING = 0.4
    
    def __init__(self, sim, viewport, log_stream=None, replay_stream=None,
                 ghost_sim=None, ghost_stream=None):
        pyglet.window.Window.__init__(self,
                                      width=self.WINDOW_SIDE,
                                      height=self.WINDOW_SIDE,
                                      resizable=True,
                                      caption='sim')
        self.sim = sim
        self.log_stream = log_stream
        self.replay_stream = replay_stream
        self.ghost_sim = ghost_sim
        self.ghost_stream = ghost_stream
        self.time = 0
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
                try:
                    thrust, turn_direction = pickle.load(self.replay_stream)
                    self.sim.ship.thrust = thrust
                    self.sim.ship.turn_direction = turn_direction
                except EOFError:
                    pyglet.app.exit()
                    break
            if self.ghost_stream:
                try:
                    thrust, turn_direction = pickle.load(self.ghost_stream)
                    self.ghost_sim.ship.thrust = thrust
                    self.ghost_sim.ship.turn_direction = turn_direction
                except EOFError:
                    self.ghost_sim.ship.thrust = False
                    self.ghost_sim.ship.turn_direction = 0
            if self.log_stream:
                pickle.dump((self.sim.ship.thrust,
                             self.sim.ship.turn_direction), self.log_stream)
            if self.ghost_sim:
                self.ghost_sim.step()
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
        if self.ghost_sim:
            def damp(color):
                return tuple(c * self.GHOST_COLOR_DAMPING for c in color)
            def gray_scale(color):
                c = sum(color) / 3.0
                return c,c,c
            draw_world(self.ghost_sim.world, gray_scale)
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

def make_sim(file, is_ghost=False):
    header, bodies = read_level(file)
    sim = Sim(header['width'], header['height'],
              set(header['winning_condition']), is_ghost=is_ghost)
    for body in bodies:
        body_id = body[0]
        if body_id == 'viewport':
            viewport = body[2][0][4]
        elif body_id == 'gravity':
            (p1x, p1y), (p2x, p2y) = body[2][0][4]
            x, y = p2x-p1x, p2y-p1y

            sim.world.SetGravity(b2Vec2(x, y))
        else:
            added = sim.add_object(body)
            if body_id == 'ship':
                sim.set_ship_body(added)
    return sim, viewport

def headless(sim, replay_stream):
    try:
        while not sim.game_end_status:
            thrust, turn_direction = pickle.load(replay_stream)
            sim.ship.thrust = thrust
            sim.ship.turn_direction = turn_direction
            sim.step()
    except EOFError:
        pass

def main():
    parser = OptionParser()
    parser.add_option('-l', '--log', dest='log_file', metavar='FILE', 
                      help='Write log to FILE.')
    parser.add_option('-r', '--replay', dest='replay_file', metavar='FILE', 
                      help='Replay moves from FILE.')
    parser.add_option('-g', '--ghost', dest='ghost_file', metavar='FILE', 
                      help='Replay ghost moves from FILE.')
    parser.add_option('-H', '--headless', dest='headless', action='store_true',
                      help='Replay without displaying graphics.')
    options, args = parser.parse_args()

    if options.headless and not options.replay_file:
        parser.error('Headless simulation requires a replay file.')

    if len(args) < 1:
        parser.error('Level file name must be given. ')

    sim, viewport = make_sim(args[0])
    ghost_sim = None
    if (options.ghost_file):
        ghost_sim, _ = make_sim(args[0], is_ghost=True)

    if options.headless:
        with open(options.replay_file) as f:
            headless(sim, f)
    else:
        with nested(misc.open(options.log_file, 'w'),
                    misc.open(options.replay_file),
                    misc.open(options.ghost_file)) as (log, replay, ghost):
            window = SimWindow(sim, viewport, 
                               log_stream=log, replay_stream=replay,
                               ghost_sim=ghost_sim, ghost_stream=ghost)
            pyglet.app.run()

    if sim.game_end_status == Sim.LEVEL_COMPLETED:
        print sim.steps_taken
    elif sim.game_end_status == Sim.GAME_OVER:
        print 'GAME OVER'
    else:
        print 'ABORTED'

if __name__ == '__main__':
    main()
