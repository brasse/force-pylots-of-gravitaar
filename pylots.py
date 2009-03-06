import math

from Box2D import *
import pyglet
from pyglet.gl import *

class ContactListener(b2ContactListener):
    def __init__(self):
        super(ContactListener, self).__init__()
        self.ship = None
        self.ship_collision = False

    def ship_in_collision(self, point):
        return self.ship in [point.shape1.GetBody(), point.shape2.GetBody()]

    def Add(self, point):
        if self.ship_in_collision(point):
            self.ship.GetUserData()['color'] = (1.0, 0.5, 0.5)

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
    def __init__(self):
        self.body = None
        self.thrust = False
        self.turn_direction = 0

    def apply_controls():
        pass

class Sim(object):
    def __init__(self):
        self.time_step = 1.0 / 60.0
        self.time = 0.0
        self.thrust = False
        self.turn_direction = 0

        worldAABB = b2AABB()
        worldAABB.lowerBound.Set(-100, -100)
        worldAABB.upperBound.Set(100, 100)
        gravity = b2Vec2(0, -5)
        doSleep = True
        self.world = b2World(worldAABB, gravity, doSleep)
        self.contact_listener = ContactListener()
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
        ship.SetUserData(dict(color=(0.0, 0.0, 0.0)))
        self.ship = ship
        self.contact_listener.ship = ship

    def apply_thrust(self):
        if self.ship and self.thrust:
            self.ship.ApplyForce(self.ship.GetWorldVector((0, 15)),
                                 self.ship.GetPosition())

    def apply_turn(self):
        if self.ship:
            self.ship.SetAngularVelocity(2 * self.turn_direction)

    def add_box(self, position, angle=0, extents=(1, 1),
                density=0.0, friction=0.3, color=(1.0, 1.0, 1.0)):
        bodyDef = b2BodyDef()
        bodyDef.position.Set(*position)
        bodyDef.angle = angle
        body = self.world.CreateBody(bodyDef)
        shapeDef = b2PolygonDef()
        shapeDef.friction = friction
        shapeDef.SetAsBox(*extents)
        shapeDef.density = density 
        body.CreateShape(shapeDef)
        body.SetMassFromShapes()
        body.SetUserData(dict(color=color))

    def add_circle(self, position, angle=0, radius=1,
                   density=0.0, friction=0.3, color=(1.0, 1.0, 1.0)):
        bodyDef = b2BodyDef()
        bodyDef.position.Set(*position)
        bodyDef.angle = angle
        body = self.world.CreateBody(bodyDef)
        shapeDef = b2CircleDef()
        shapeDef.friction = friction
        shapeDef.radius = radius
        shapeDef.density = density 
        body.CreateShape(shapeDef)
        body.SetMassFromShapes()
        body.SetUserData(dict(color=color))

    def add_edge(self, position, color):
        bodyDef = b2BodyDef()
        bodyDef.position.Set(*position)
        body = self.world.CreateBody(bodyDef)
        shapeDef = b2EdgeChainDef()
        vertices = [(1, 0.2), (0, 0), (-1, 0.2)]
        shapeDef.setVertices(vertices)
        shapeDef.friction = 0.3
        shapeDef.isALoop = False
        body.CreateShape(shapeDef)
        body.SetUserData(dict(color=color))

    def step(self, dt):
        self.time += dt
        while self.time > self.time_step:
            self.time -= self.time_step
            vel_iters, pos_iters = 10, 8
            self.apply_thrust()
            self.apply_turn()
            self.world.Step(self.time_step, vel_iters, pos_iters)
            if self.contact_listener.ship_collision:
                self.world.DestroyBody(self.ship[0])
                self.ship = None
                self.contact_listener.ship_collision = False

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
    SIDE = 400
    
    def __init__(self):
        pyglet.window.Window.__init__(self,
                                      width=self.SIDE,
                                      height=self.SIDE,
                                      caption='sim')
        self.sim = Sim()
        self.sim.add_box((0, 1), -0.1, (50, 1), color=(0.0, 0.0, 1.0))
        self.sim.add_box((1.8, 9), extents=(.1, .1), color=(0.0, 1.0, 0.0))
        self.sim.add_box((2, 16), 0.5, (1, 1), 1)
        self.sim.add_box((2, 4), 0.5, (1, 1), 1, color=(1.0, 0.0, 0.0))
        self.sim.add_circle((13, 7), density=1, color=(1.0, 1.0, 0.0))
        self.sim.add_edge((13, 5), (0.0, 1.0, 0.0))
        self.sim.init_ship((7,7))
        pyglet.clock.schedule_interval(self.update, 1 / 60.0)
        
    def on_resize(self, width, height):
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0.0, 15.0, 0.0, 15.0, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW)
        
    def update(self, dt):
        self.sim.step(dt)

    def on_draw(self):
        glClearColor(0.3, 0.3, 0.4, 1.0)
        self.clear()
        draw_world(self.sim.world)
        
    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.UP:
            self.sim.thrust = True
        elif symbol == pyglet.window.key.LEFT:
            self.sim.turn_direction = 1
        elif symbol == pyglet.window.key.RIGHT:
            self.sim.turn_direction = -1

    def on_key_release(self, symbol, modifiers):
        if symbol == pyglet.window.key.UP:
            self.sim.thrust = False
        elif symbol in [pyglet.window.key.LEFT, pyglet.window.key.RIGHT]:
            self.sim.turn_direction = 0
        
def main():
    window = SimWindow()
    pyglet.app.run()

if __name__ == '__main__':
    main()
