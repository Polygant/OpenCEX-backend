import environ
import os


env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Take environment variables from .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))
