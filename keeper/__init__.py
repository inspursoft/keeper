import os

from flask import Flask, current_app

def create_app(test_config=None):
  #create and configure the app
  app = Flask(__name__, instance_relative_config=True)
  app.logger.debug("Instance path: %s" % (app.instance_path))
  app.config.from_mapping(
    DATABASE=os.path.join(app.instance_path, 'keeper.sqlite'),
  )
  app.config.from_json(os.path.join(app.instance_path, 'config.json'), silent=True)
  #ensure the instance folder exists
  try:
    os.makedirs(app.instance_path)
  except OSError:
    pass
    
  from . import db
  db.init_app(app)

  from . import vm
  app.register_blueprint(vm.bp)

  from . import handler
  app.register_blueprint(handler.bp)

  return app

def get_info(key):
  return current_app.config['SETUP'][key]