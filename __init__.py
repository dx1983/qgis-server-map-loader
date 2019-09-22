# -*- coding: utf-8 -*-

def serverClassFactory(serverIface):
    from .MapLoader import MapLoaderServer
    return MapLoaderServer(serverIface)
