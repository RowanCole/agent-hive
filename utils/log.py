import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-5s %(process)d --- [%(threadName)s] %(name)-20s : %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S.%f"[:-3]  
)

logging.getLogger().setLevel(logging.WARNING)

def getLogger(name :str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


