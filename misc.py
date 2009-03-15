open_ = open

class Nop(object):
    """ A nop-context manager. It does nothing. """
    def __init__(self):
        pass
    def __enter__(self):
        return None
    def __exit__(self, *exc_info):
        pass

def open(*args):
    """ An open function that handles None as input. """
    if not args[0]:
        return Nop()
    else:
        return open_(*args)

