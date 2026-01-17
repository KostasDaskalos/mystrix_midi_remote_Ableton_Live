from __future__ import absolute_import, print_function, unicode_literals

from .Mystrix_Pro import Mystrix_Pro

def create_instance(c_instance):
    return Mystrix_Pro(c_instance)
