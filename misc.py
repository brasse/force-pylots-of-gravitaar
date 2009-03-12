open_ = open

class Nop(object):
    def __init__(self):
        pass
    def __enter__(self):
        return None
    def __exit__(self, *exc_info):
        pass

def open(*args):
    if not args[0]:
        return Nop()
    else:
        return open_(*args)

