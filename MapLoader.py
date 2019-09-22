from qgis.server import *
from qgis.core import *

from PyQt5.QtCore import *

import psycopg2, time

import inspect, os
cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

# Get repository of projects.
qgsRepo = os.environ.get('QGIS_PROJECT_REPO')
#   QGIS_PROJECT_REPO = postgresql://[user[:pass]@]host[:port]/?dbname=X&schema=Y[&project=Z][&authcfg=A]
#       e.g. "postgresql://<user>:<pass>@<host>:<port>?sslmode=disable&dbname=<database>&schema=<schema>"
#       or   "postgresql://<host>:<port>?sslmode=disable&dbname=<database>&schema=<schema>&authcfg=<authcfgid>"

def Bytes(string):
    return bytes(string, 'utf8')

#Convert QGIS URL to PostgreSQL DSN
def URL2DSN(url):
    u = QUrl.fromEncoded(Bytes(url))
    q = QUrlQuery(u.query())
    
    host = u.host()
    port = '' if u.port() == -1 else str(u.port())
    username = u.userName()
    password = u.password()
    sslmode = QgsDataSourceUri.decodeSslMode(q.queryItemValue("sslmode"))
    authcfg = q.queryItemValue("authcfg")
    dbname = q.queryItemValue("dbname")
    schema = q.queryItemValue("schema")
    service = q.queryItemValue("service")
    
    uri = QgsDataSourceUri()
    if service:
        uri.setConnection(service, dbname, username, password, sslmode, authcfg)
    else:
        uri.setConnection(host, port, dbname, username, password, sslmode, authcfg)
    uri.setSchema(schema)
    
    return uri.connectionInfo(True)
    

def PgQueryData(dsn, sql, rows = 0):
    conn = None
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(sql)
        if rows == 1:
            data = cur.fetchone()
        elif rows > 1:
            data = cur.fetchmany(rows)
        else:
            data = cur.fetchall()
        cur.close()
        return data
    finally:
        if conn is not None:
            conn.close()

class MapLoader(QgsServerFilter):
    def __init__(self, serverIface):
        super(MapLoader, self).__init__(serverIface)
        self.pgStatusCache = {}

    def checkModifiedStatus(self, uri):
        cooldown = .2
        name = QUrlQuery(uri).queryItemValue('project')
        cache = self.pgStatusCache.get(name, {})
        if time.time() - cache.get('time', 0) < cooldown: return
        dsn = URL2DSN(uri)
        sql = "SELECT metadata from qgis_projects where name = '{}'".format(name)
        res = PgQueryData(dsn, sql, 1)
        data = res[0] if res else None
        if data and cache.get('data') != data:
            self.pgStatusCache[name] = {'data': data, 'time':time.time()}
            return True if cache else False
        else:
            if cache: self.pgStatusCache.get(name)['time'] = time.time()
    
    def requestReady(self):
        request = self.serverInterface().requestHandler()
        params = request.parameterMap( )

        carto = params.get('MAP', '')
        if os.path.exists(carto): return
        
        if qgsRepo.startswith(r'postgresql://'):
            if '&project=' in qgsRepo.lower():
                qgs_target = qgsRepo
            elif not carto:
                return
            else:
                qgs_target = '{}&project={}'.format(qgsRepo, carto)
            
            if self.checkModifiedStatus(qgs_target):
                self.serverInterface().removeConfigCacheEntry(qgs_target)
                QgsMessageLog.logMessage("Remove cache entry {}".format(qgs_target), 'Plugin', 1)
        else:
            qgs_target = os.path.join(qgsRepo, carto) if carto else qgsRepo
            if not os.path.isfile(qgs_target): return

        self.serverInterface().setConfigFilePath(qgs_target)
        QgsMessageLog.logMessage("Set qgs target to {}".format(qgs_target), 'Plugin', 1)

    # Adds SERVICE=MAPLOADER support for listing qgs projects.
    def responseComplete(self):
        request = self.serverInterface().requestHandler()
        params = request.parameterMap()
        
        if params.get('SERVICE', '').upper() == 'MAPLOADER':
            request.clear()
            request.setResponseHeader('Content-type', 'text/plain; charset=utf-8')
            request.clearBody()
            
            request.appendBody(Bytes('Map projects: \n'))
            if qgsRepo.startswith(r'postgresql://'):
                dsn = URL2DSN(qgsRepo)
                QgsMessageLog.logMessage("Connection DSN: {}".format(dsn), 'Authentication')
                sql = "SELECT name from qgis_projects"
                datas = PgQueryData(dsn, sql)
                request.appendBody(Bytes('\n'.join([d[0] for d in datas])+'\n'))
            else:
                it = QDirIterator(qgsRepo)
                while (it.hasNext()):
                    path = it.next()
                    if path.endswith('.qgz') or path.endswith('.qgs'):
                        request.appendBody(Bytes(it.fileName()+'\n'))
            request.appendBody(Bytes('END\n'))

#Setup authentication system to load authcfg when access projects from postgresql.
def InitAuthenticationManager():
    
    master_password_file = os.path.join(os.environ.get('QGIS_AUTH_DB_DIR_PATH',''), 'master')
    if os.path.isfile(master_password_file):
        with open(master_password_file, 'r') as f:
            master_password = f.readline().strip()
    else:
        #(QGIS_AUTH_MASTER_PASSWORD variable removed from environment after accessing)
        master_password = os.environ.pop('QGIS_AUTH_MASTER_PASSWORD') if 'QGIS_AUTH_MASTER_PASSWORD' in os.environ else 'default master password'
    
    authMgr = QgsApplication.authManager()
    if authMgr.authenticationDatabasePath():
        if authMgr.masterPasswordIsSet():
            msg = 'Authentication master password not recognized, variable QGIS_AUTH_MASTER_PASSWORD and QGIS_AUTH_PASSWORD_FILE is inconsistent'
            assert authMgr.masterPasswordSame(master_password), msg
        else:
            msg = 'Master password could not be set, update variable QGIS_AUTH_MASTER_PASSWORD to fix it'
            assert authMgr.setMasterPassword(master_password, verify=True), msg
    else:
        auth_folder = 'auth'
        msg = 'Environment variable QGIS_AUTH_DB_DIR_PATH is not set.'
        auth_db_path = os.path.join(cmd_folder, auth_folder, 'qgis-auth.db')
        assert os.path.isfile(auth_db_path), msg
        os.environ['QGIS_AUTH_DB_DIR_PATH'] = os.path.join(cmd_folder, auth_folder)
        auth_master_file = os.path.join(cmd_folder, auth_folder, 'master')
        if os.path.isfile(auth_master_file):
            os.environ['QGIS_AUTH_PASSWORD_FILE'] = auth_master_file
        else:
            msg = 'Master password could not be set'
            assert authMgr.setMasterPassword(master_password, True), msg
        authMgr.init(cmd_folder, auth_db_path)
    
    QgsMessageLog.logMessage("Available Authentication Config: {}".format(list(authMgr.availableAuthMethodConfigs().keys())), 'Authentication', 0)

class MapLoaderServer:
    def __init__(self, serverIface):
        self.serverIface = serverIface
        if not qgsRepo:
            QgsMessageLog.logMessage("Environment variable QGIS_PROJECT_REPO is not set, the map loader filter is ignored.", 'Plugin', 2)
            return
        if qgsRepo.startswith(r'postgresql://') and 'authcfg' in qgsRepo:
            InitAuthenticationManager()
        serverIface.registerFilter(MapLoader(serverIface), 101)
