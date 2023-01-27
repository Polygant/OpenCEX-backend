SERVICE_INSTANCE = None


def get_service_instance():
    return SERVICE_INSTANCE


def set_service_instance(instance):
    global SERVICE_INSTANCE
    SERVICE_INSTANCE = instance
