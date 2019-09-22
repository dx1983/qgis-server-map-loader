# qgis-server-map-loader
QGIS server plugin for loading map files in a specific directory or postgresql .

## Installation
- Copy repo contents to `%QGIS_PLUGINSPATH%\qgis-server-map-loader`.
- Use projects in directory: 
    - Set enviroment `QGIS_PROJECT_REPO` to directory which contains your `*.gps`-files
- Use projects in PostgreSQL: 
    - Set enviroment `QGIS_PROJECT_REPO` to PostgreSQL syntax like `postgres://[user[:pass]@]host[:port]/?dbname=X&schema=Y[&project=Z][&authcfg=A]`
    - Set enviorment `QGIS_AUTH_DB_DIR_PATH` to directory whick contains `qgis-auth.db` file
    - Set enviroment `QGIS_AUTH_MASTER_PASSWORD` to the master password or put the password file named `master` with the same directory
- Reload QGIS server.