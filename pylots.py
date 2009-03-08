import math
import sys
from collections import defaultdict

from Box2D import *
import pyglet
from pyglet.gl import *

class ContactListener(b2ContactListener):
    def __init__(self, collectible_callback, ship_death_callback):
        super(ContactListener, self).__init__()
        self.ship = None
        self.collectible = collectible_callback
        self.ship_death = ship_death_callback

    def ship_in_collision(self, point):
        return self.ship in [point.shape1.GetBody(), point.shape2.GetBody()]

    @staticmethod
    def get_body(body1, body2, type):
        if body1.GetUserData()['type'] == type:
            return body1
        assert(body2.GetUserData()['type'] == type)
        return body2
    
    def Add(self, point):
        if self.ship_in_collision(point):
            self.ship.GetUserData()['color'] = (1.0, 0.5, 0.5)
        b1 = point.shape1.GetBody()
        b2 = point.shape2.GetBody()
        type_pair = set([b1.GetUserData()['type'],
                         b2.GetUserData()['type']])
        if type_pair == set(['ship', 'collectible']):
            self.collectible(self.get_body(b1, b2, 'collectible'))
        elif type_pair == set(['ship', 'terminal']):
            self.ship_death()

    def Persist(self, point):
        if self.ship_in_collision(point):
            self.ship.GetUserData()['color'] = (0.1, 0.8, 0.1)

    def Remove(self, point):
        if self.ship_in_collision(point):
            self.ship.GetUserData()['color'] = (0.0, 0.0, 0.0)

    def Result(self, point):
        if self.ship_in_collision(point):
            self.ship.GetUserData()['color'] = (0.6, 0.2, 0.2)

class Ship(object):
    def __init__(self, body):
        self.body = body
        self.turn_speed = 2
        self.acceleration_force = 15
        self.thrust = False
        self.turn_direction = 0

    @property
    def position(self):
        return self.body.GetPosition().tuple()
    
    @property
    def velocity(self):
        return self.body.GetLinearVelocity().tuple()

    def apply_controls(self):
        self.apply_thrust()
        self.apply_turn()

    def apply_thrust(self):
        if self.thrust:
            f = self.body.GetWorldVector((0, self.acceleration_force))
            self.body.ApplyForce(f, self.body.GetPosition())

    def apply_turn(self):
        self.body.SetAngularVelocity(self.turn_speed * self.turn_direction)

class Sim(object):
    def __init__(self, game_end_callback):
        self.game_end = game_end_callback
        self.time_step = 1.0 / 60.0
        self.total_time = 0.0
        self.thrust = False
        self.turn_direction = 0
        self.collectibles = set()
        self.remove_body_list = set()

        worldAABB = b2AABB()
        worldAABB.lowerBound.Set(-100, -100)
        worldAABB.upperBound.Set(100, 100)
        gravity = b2Vec2(0, -5)
        doSleep = True
        self.world = b2World(worldAABB, gravity, doSleep)
        self.contact_listener = ContactListener(self.collect, self.ship_death)
        self.world.SetContactListener(self.contact_listener)

    def init_ship(self, position, angle=0):
        bodyDef = b2BodyDef()
        bodyDef.position.Set(*position)
        bodyDef.angle = angle
        ship = self.world.CreateBody(bodyDef)
        shapeDef = b2PolygonDef()
        shapeDef.density = 1
        for points in [[(0.0, 0.7), (-0.5, -0.7),  (0.0, -0.5)], 
                       [(0.0, 0.7), (0.0, -0.5),  (0.5, -0.7)]]:
            shapeDef.setVertices(points)
            ship.CreateShape(shapeDef)
        ship.SetMassFromShapes()
        ship.SetUserData(defaultdict(lambda: None,
                                     color=(0.0, 0.0, 0.0), type='ship'))
        self.contact_listener.ship = ship
        self.ship = Ship(ship)

    def add_object(self, position, angle=0, density=1, friction=0,
                   shape_def=None, color=(1.0, 1.0, 1.0), type=None):
        bodyDef = b2BodyDef()
        bodyDef.position.Set(*position)
        bodyDef.angle = angle
        body = self.world.CreateBody(bodyDef)
        shape_def.friction = friction
        shape_def.density = density 
        body.CreateShape(shape_def)
        body.SetMassFromShapes()
        body.SetUserData(defaultdict(lambda: None,
                                     color=color, type=type))
        if type == 'collectible':
            self.collectibles.add(body)

    def add_box(self, position, angle=0, extents=(1, 1),
                density=0.0, friction=0.3, color=(1.0, 1.0, 1.0), type=None):
        shape_def = b2PolygonDef()
        shape_def.SetAsBox(*extents)
        self.add_object(position, angle, density, friction, shape_def,
                        color, type)
            
    def add_circle(self, position, angle=0, radius=1, density=0.0,
                   friction=0.3, color=(1.0, 1.0, 1.0), type=None):
        shape_def = b2CircleDef()
        shape_def.radius = radius
        self.add_object(position, angle, density, friction, shape_def,
                        color, type)

    def add_edge(self, position, color):
        shape_def = b2EdgeChainDef()
        vertices = [(1, 0.2), (0, 0), (-1, 0.2)]
        shape_def.setVertices(vertices)
        shape_def.isALoop = False
        self.add_object(position, shape_def=shape_def, color=color)

    def collect(self, body):
        self.remove_body_list.add(body)
        self.collectibles.discard(body)

    def ship_death(self):
        self.game_end(died=True)

    def step(self):
        self.total_time += self.time_step
        self.ship.apply_controls()
        vel_iters, pos_iters = 10, 8
        self.world.Step(self.time_step, vel_iters, pos_iters)
        for body in self.remove_body_list:
            self.world.DestroyBody(body)
        self.remove_body_list = set()
        if len(self.collectibles) == 0:
            self.game_end()

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
    VIEWPORT_HALF_SIDE = 7.5 
 
    def __init__(self):
        pyglet.window.Window.__init__(self,
                                      width=self.WINDOW_SIDE,
                                      height=self.WINDOW_SIDE,
                                      caption='sim')
        self.sim = Sim(self.game_end)
        self.time = 0
        self.camera_position = (7.5, 7.5)
        self.sim.add_box((0, 1), -0.1, (50, 1), color=(0.0, 0.0, 1.0))
        self.sim.add_box((1.8, 9), extents=(.1, .1), color=(0.0, 1.0, 0.0),
                         type='collectible')
        self.sim.add_box((10, 11), extents=(.1, .1), color=(0.0, 1.0, 0.0),
                         type='collectible')
        self.sim.add_box((11, 11), extents=(.1, .1), color=(0.0, 1.0, 0.0),
                         type='collectible')
        self.sim.add_box((16, 1), extents=(.1, .1), color=(0.0, 1.0, 0.0),
                         type='collectible')
        self.sim.add_box((2, 16), 0.5, (1, 1), 1, type='terminal')
        self.sim.add_box((2, 4), 0.5, (1, 1), 1, color=(1.0, 0.0, 0.0),
                         type='terminal')
        self.sim.add_circle((13, 7), density=1, color=(1.0, 1.0, 0.0),
                            type='collectible')
        self.sim.add_edge((13, 5), (0.0, 1.0, 0.0))
        self.sim.init_ship((7,7))
        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

    def game_end(self, died=False):
        if not died:
            print self.sim.total_time
        else:
            print 'GAME_OVER'
        sys.exit(0)

    def on_resize(self, width, height):
        glViewport(0, 0, width, height)

    def update(self, dt):
        self.time += dt
        while self.time > self.sim.time_step:
            self.time -= self.sim.time_step
            self.sim.step()

    def update_camera_position(self):
        MAX_DISTANCE = 2.5
        new_camera = []
        ship = self.sim.ship
        for cam, ship in zip(self.camera_position, ship.position):
            distance = ship - cam
            if distance > MAX_DISTANCE:
                cam += (distance - MAX_DISTANCE)
            elif distance < -MAX_DISTANCE:
                cam += (distance + MAX_DISTANCE)
            new_camera.append(cam)
        self.camera_position = tuple(new_camera)
        
    def on_draw(self):
        self.update_camera_position()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(self.camera_position[0] - self.VIEWPORT_HALF_SIDE,
                self.camera_position[0] + self.VIEWPORT_HALF_SIDE,
                self.camera_position[1] - self.VIEWPORT_HALF_SIDE,
                self.camera_position[1] + self.VIEWPORT_HALF_SIDE,
                -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW)

        glClearColor(0.3, 0.3, 0.4, 1.0)
        self.clear()
        draw_world(self.sim.world)

    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.UP:
            self.sim.ship.thrust = True
        elif symbol == pyglet.window.key.LEFT:
            self.sim.ship.turn_direction = 1
        elif symbol == pyglet.window.key.RIGHT:
            self.sim.ship.turn_direction = -1

    def on_key_release(self, symbol, modifiers):
        if symbol == pyglet.window.key.UP:
            self.sim.ship.thrust = False
        elif symbol in [pyglet.window.key.LEFT, pyglet.window.key.RIGHT]:
            self.sim.ship.turn_direction = 0
        
def main():
    window = SimWindow()
    pyglet.app.run()

if __name__ == '__main__':
    main()
